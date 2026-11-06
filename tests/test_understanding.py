"""From records to readings to what people read: problems, replies, what a project builds on, and what is written from it all."""
import json
import os
import subprocess
from datetime import timedelta
from unittest import mock

from dendro import companion, mcp, schema, web
from dendro.collect import claude_session, git, github, references
from dendro.store import now
from tests.test_companion import Base, ME, run

SIMS = {"kind": "human", "name": "sims"}


def entry(uuid, minute, **fields):
    return json.dumps({"uuid": uuid, "timestamp": f"2026-11-06T08:{minute:02d}:00.000Z", "sessionId": "s", **fields})


def typed(uuid, minute, text):
    return entry(uuid, minute, type="user", origin={"kind": "human"}, message={"content": text})


def answered(uuid, minute, text, **fields):
    return entry(uuid, minute, type="assistant", message={"model": "m", "content": [{"type": "text", "text": text}]}, **fields)


class Days(Base):
    def day(self, trace):
        event, day = self.yesterday(trace)
        return event["id"], day

    def test_a_digest_brings_what_it_found_on_the_day_it_happened(self):
        trace = self.trace()
        event, day = self.day(trace)
        failed, out = self.tool(trace, "dendro_digest", day=day, text="读过了。", evidence=[event],
                                problems=[{"text": "测试不稳定", "evidence": [event]}],
                                decisions=[{"text": "改用 SQLite", "by": "human:ada", "evidence": [event]}])
        self.assertFalse(failed, out)
        self.assertEqual([x["type"] for x in out["also"]], ["problem", "decision"])
        events = {e["id"]: e for e in trace.events()}
        made = events[out["also"][1]["id"]]
        self.assertEqual((made["actor"]["name"], companion.day_of(made), made["refs"][0]["to"]), ("ada", day, event))
        self.assertEqual([p["status"] for p in companion.issues(trace.events())], ["open"])

    def test_it_is_all_written_or_none(self):
        trace = self.trace()
        event, day = self.day(trace)
        before = len(trace.events())
        failed, out = self.tool(trace, "dendro_digest", day=day, text="读过了。", evidence=[event], problems=[{"text": "无据", "evidence": []}])
        self.assertTrue(failed)
        self.assertIn("no evidence", out["refused"][0])
        self.assertEqual(len(trace.events()), before)

    def test_a_problem_ends_when_a_reader_says_how(self):
        trace = self.trace()
        event, day = self.day(trace)
        raised = trace.append(ME, "problem", {"text": "内存泄漏"}, refs=[{"rel": "based_on", "to": event}])
        self.assertEqual(self.tool(trace, "dendro_day", day=day)[1]["open_problems"], [{"id": raised["id"], "text": "内存泄漏"}])
        failed, out = self.tool(trace, "dendro_digest", day=day, text="修好了。", evidence=[event], resolved=[{"problem": raised["id"], "text": "换了缓存", "outcome": "solved", "evidence": [event]}])
        self.assertFalse(failed, out)
        ended = companion.issues(trace.events())[0]
        self.assertEqual((ended["status"], ended["how"]), ("solved", "换了缓存"))
        self.assertIn("not an open problem", self.tool(trace, "dendro_digest", day=day, text="再来", evidence=[event], resolved=[{"problem": raised["id"], "text": "x", "outcome": "solved", "evidence": [event]}])[1]["refused"][0])

    def test_a_problem_rests_on_something_and_resolved_answers_one(self):
        trace = self.trace()
        event, _ = self.day(trace)
        self.assertIn("points back", self.tool(trace, "dendro_say", type="problem", text="感觉不对")[1]["refused"][0])
        refs = [{"rel": "responds_to", "to": event}]
        self.assertIn("responds_to", self.tool(trace, "dendro_say", type="resolved", text="好了", data={"outcome": "solved"}, refs=refs)[1]["refused"][0])

    def test_replies_are_read_after_words_and_before_files(self):
        trace = self.trace()
        ts = now() - timedelta(days=1)
        day = companion.day_of(trace.append("files", "change", {"text": "a.py"}, {"kind": "system", "name": "files"}, ts=ts.isoformat()))
        trace.append(ME, "reply", {"text": "结论"}, {"kind": "agent", "name": "claude"}, ts=ts.isoformat())
        trace.append(ME, "said", {"text": "问题"}, SIMS, ts=ts.isoformat())
        self.assertEqual([e["type"] for e in companion.day(trace, day)["events"]], ["said", "reply", "change"])

    def test_a_long_day_stays_under_what_a_client_takes(self):
        trace = self.trace()
        ts = (now() - timedelta(days=1)).isoformat()
        for i in range(120):
            trace.append(ME, "said", {"text": "字" * 390}, SIMS, ts=ts)
        seen = companion.day(trace, ts[:10])
        self.assertLess(len(json.dumps(seen, ensure_ascii=False)), 60000)
        self.assertEqual(seen["records"], 120)
        self.assertLess(len(seen["events"]), 120)
        rest = companion.day(trace, ts[:10], seen["next"])
        self.assertEqual(rest["events"][0]["id"] not in {e["id"] for e in seen["events"]}, True)
        ids, start = [], 0
        while start is not None:
            part = companion.day(trace, ts[:10], start)
            ids += [e["id"] for e in part["events"]]
            start = part.get("next")
        self.assertEqual(len(set(ids)), 120)


class Replies(Base):
    def transcript(self, *lines):
        path = self.write("t.jsonl", "\n".join(lines))
        return [path]

    def test_only_the_last_words_of_a_turn_are_kept(self):
        paths = self.transcript(typed("a", 1, "为什么慢"), answered("b", 2, "我先看看"), answered("c", 3, "因为没有索引"),
                                typed("d", 4, "好"), answered("e", 5, "加好了"))
        rows = claude_session.items(paths, SIMS, agent={"kind": "agent", "name": "claude"})
        self.assertEqual([(r["type"], r["body"]["text"]) for r in rows], [("said", "为什么慢"), ("reply", "因为没有索引"), ("said", "好"), ("reply", "加好了")])

    def test_subagents_and_errors_are_not_replies(self):
        paths = self.transcript(typed("a", 1, "x"), answered("b", 2, "内部", isSidechain=True), answered("c", 3, "Error", isApiErrorMessage=True))
        self.assertEqual([r["type"] for r in claude_session.items(paths, SIMS, agent={"kind": "agent", "name": "claude"})], ["said"])

    def test_a_session_that_moved_to_another_project_is_left_out_there(self):
        here, there = self.folder, os.path.join(self.tmp, "Other")
        inside = os.path.join(here, "sub")
        paths = self.transcript(entry("a", 1, type="user", origin={"kind": "human"}, message={"content": "这里"}, cwd=inside),
                                entry("b", 2, type="user", origin={"kind": "human"}, message={"content": "别处"}, cwd=there),
                                typed("c", 3, "不知道在哪"))
        self.assertEqual([r["body"]["text"] for r in claude_session.items(paths, SIMS, folder=here)], ["这里", "不知道在哪"])

    def test_a_reply_is_asked_for(self):
        paths = self.transcript(typed("a", 1, "x"), answered("b", 2, "y"))
        self.assertEqual(len(claude_session.items(paths, SIMS)), 1)

    def test_a_long_reply_says_what_is_left_out(self):
        paths = self.transcript(typed("a", 1, "x"), answered("b", 2, "字" * (claude_session.REPLY + 5)))
        reply = claude_session.items(paths, SIMS, agent={"kind": "agent", "name": "claude"})[1]
        self.assertEqual((len(reply["body"]["text"]), reply["body"]["data"]["cut"]), (claude_session.REPLY, 5))


class Builds(Base):
    def named(self):
        return {(i["body"]["data"]["kind"], i["body"]["text"], i["body"]["data"].get("version")) for i in references.items(self.folder)}

    def test_manifests_name_what_a_project_depends_on(self):
        self.write("requirements.txt", "flask==3.0\n# a note\n-r other.txt\nrequests>=2\n")
        self.write("web/package.json", json.dumps({"dependencies": {"react": "^19"}, "devDependencies": {"vite": "7"}}))
        self.write("pyproject.toml", '[project]\nname = "x"\ndependencies = ["numpy>=2", "torch"]\n')
        self.write("Cargo.toml", '[package]\nname = "x"\n[dependencies]\nserde = "1"\ntokio = { version = "1.4" }\n')
        self.write("go.mod", "module x\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.1\n)\n")
        self.assertEqual({n for n in self.named()}, {
            ("dependency", "flask", "==3.0"), ("dependency", "requests", ">=2"), ("dependency", "react", "^19"), ("dependency", "vite", "7"),
            ("dependency", "numpy", ">=2"), ("dependency", "torch", None), ("dependency", "serde", "1"), ("dependency", "tokio", "1.4"),
            ("dependency", "github.com/gin-gonic/gin", "v1.9.1")})

    def test_notes_and_bibliographies_name_what_it_learned_from(self):
        self.write("README.md", "Built on https://github.com/pallets/flask.git and https://arxiv.org/abs/2401.00001.\n")
        self.write("refs.bib", "@inproceedings{a, title={On {Trees}}, year={2024}, booktitle={CVPR}}\n")
        self.assertEqual(self.named(), {("repository", "pallets/flask", None), ("paper", "arXiv:2401.00001", None), ("paper", "On Trees", None)})

    def test_a_project_does_not_reference_itself(self):
        self.repo()
        run(self.folder, "remote", "add", "origin", "https://github.com/Ada/Demo.git")
        self.write("README.md", "See https://github.com/ada/demo and https://github.com/other/one\n")
        self.assertEqual({n[1] for n in self.named()}, {"other/one"})

    def test_a_broken_manifest_is_passed_over(self):
        self.write("package.json", "{not json")
        self.write("requirements.txt", "flask\n")
        self.assertEqual(self.named(), {("dependency", "flask", None)})

    def test_a_new_version_is_a_new_record_and_the_same_one_is_not(self):
        trace = self.trace()
        self.write("requirements.txt", "flask==3.0\n")
        self.assertEqual(companion.catch_up(trace, ME, self.folder)["references"], 1)
        self.assertEqual(companion.catch_up(trace, ME, self.folder)["references"], 0)
        self.write("requirements.txt", "flask==3.1\n")
        self.assertEqual(companion.catch_up(trace, ME, self.folder)["references"], 1)

    def test_tags_are_releases(self):
        self.repo()
        run(self.folder, "tag", "-a", "v1.0", "-m", "First release")
        run(self.folder, "tag", "plain")
        rows = {i["body"]["text"]: i for i in git.tags(self.folder)}
        self.assertEqual(set(rows), {"v1.0", "plain"})
        self.assertEqual(rows["v1.0"]["body"]["data"]["note"], "First release")
        self.assertTrue(schema.moment(rows["v1.0"]["ts"]))


class GitHub(Base):
    ISSUE = {"number": 7, "title": "It crashes", "author": {"login": "ada"}, "url": "u", "createdAt": "2026-11-01T01:00:00Z", "closedAt": "2026-11-02T01:00:00Z"}
    PULL = {"number": 8, "title": "Fix", "author": None, "url": "u", "createdAt": "2026-11-01T02:00:00Z", "closedAt": "2026-11-02T02:00:00Z", "mergedAt": "2026-11-02T02:00:00Z"}
    RUN = {"databaseId": 9, "displayTitle": "Fix", "workflowName": "CI", "headBranch": "main", "createdAt": "2026-11-01T03:00:00Z", "url": "u"}

    def gh(self, command, **_):
        rows = {"issue": [self.ISSUE], "pr": [self.PULL], "run": [self.RUN]}[command[1]]
        return subprocess.CompletedProcess(command, 0, json.dumps(rows), "")

    def test_each_turn_of_a_ticket_keeps_its_own_time(self):
        with mock.patch.object(github.git, "remote", return_value="https://github.com/a/b.git"), mock.patch.object(github.subprocess, "run", self.gh):
            rows = list(github.items(self.folder))
        self.assertEqual([(r["type"], r["body"]["data"].get("state")) for r in rows],
                         [("ticket", "opened"), ("ticket", "closed"), ("ticket", "opened"), ("ticket", "merged"), ("check", None)])
        self.assertEqual(rows[1]["ts"], "2026-11-02T01:00:00+00:00")
        trace = self.trace()
        trace.extend("github", rows)
        self.assertEqual(trace.check(), [])

    def test_a_project_elsewhere_asks_nothing(self):
        with mock.patch.object(github.git, "remote", return_value="https://gitlab.com/a/b.git"), mock.patch.object(github.subprocess, "run", side_effect=AssertionError):
            self.assertEqual(list(github.items(self.folder)), [])

    def test_the_network_is_asked_now_and_then_and_may_fail(self):
        trace = self.trace()
        with mock.patch.object(github.git, "remote", return_value="https://github.com/a/b.git"), mock.patch.object(github.subprocess, "run", side_effect=FileNotFoundError("gh")):
            self.assertIn("skipped", companion.fetch(trace, ME, self.folder)["github"])
            self.assertEqual(companion.fetch(trace, ME, self.folder), {})

    def test_starting_a_session_does_not_wait_for_the_network(self):
        with mock.patch.object(companion, "fetch", side_effect=AssertionError):
            companion.catch_up(self.trace(), ME, self.folder)


class Outputs(Base):
    def setUp(self):
        super().setUp()
        self.t = self.trace()
        self.event, self.when = self.yesterday(self.t)
        self.section = {"heading": "进展", "text": "完成了第一次提交。", "evidence": [self.event["id"]]}

    def test_every_kind_has_its_guide(self):
        for kind in schema.OUTPUTS:
            self.assertIn("dendro_output", companion.guide(kind))
            self.assertIn(kind, mcp.PROMPTS)

    def test_material_is_what_the_readings_add_up_to(self):
        self.tool(self.t, "dendro_digest", day=self.when, text="一天。", evidence=[self.event["id"]], problems=[{"text": "卡住了", "evidence": [self.event["id"]]}])
        failed, seen = self.tool(self.t, "dendro_material", kind="report", audience="导师")
        self.assertFalse(failed, seen)
        self.assertEqual((seen["digests"][0]["text"], seen["problems"][0]["text"], seen["audience"], seen["commits"]), ("一天。", "卡住了", "导师", 1))
        self.assertEqual(seen["unread_days"], [])

    def test_a_span_narrows_it_and_an_open_problem_stays(self):
        self.tool(self.t, "dendro_digest", day=self.when, text="一天。", evidence=[self.event["id"]], problems=[{"text": "卡住了", "evidence": [self.event["id"]]}])
        seen = companion.material(self.t, "weekly", since="2099-01-01")
        self.assertEqual((seen["digests"], seen["commits"], [p["text"] for p in seen["problems"]]), ([], 0, ["卡住了"]))

    def test_a_day_with_no_digest_is_named(self):
        self.assertEqual(companion.material(self.t, "report")["unread_days"], [self.when])

    def test_what_does_not_fit_is_counted(self):
        for i in range(40):
            self.t.append(ME, "decision", {"text": "字" * 300})
        seen = companion.material(self.t, "report")
        self.assertGreater(seen["left_out"]["decisions"], 0)
        self.assertEqual(len(seen["decisions"]) + seen["left_out"]["decisions"], 40)

    def test_an_output_shows_where_each_section_comes_from(self):
        failed, out = self.tool(self.t, "dendro_output", kind="report", title="周报", audience="导师", sections=[self.section])
        self.assertFalse(failed, out)
        self.assertEqual(out["refs"], [{"rel": "based_on", "to": self.event["id"]}])
        self.assertEqual(self.t.check(), [])

    def test_a_section_with_nothing_behind_it_is_refused(self):
        self.assertIn("no evidence", self.tool(self.t, "dendro_output", kind="report", title="周报", sections=[dict(self.section, evidence=[])])[1]["refused"][0])
        self.assertIn("no such event", self.tool(self.t, "dendro_output", kind="report", title="周报", sections=[dict(self.section, evidence=["e_0000000000000000"])])[1]["refused"][0])

    def test_a_section_can_rest_on_a_file(self):
        self.write("docs/plan.md", "计划")
        section = {"heading": "计划", "text": "见文档。", "files": ["docs/plan.md"]}
        failed, out = self.tool(self.t, "dendro_output", kind="report", title="周报", sections=[section])
        self.assertFalse(failed, out)
        self.assertEqual(out["body"]["data"]["sections"][0]["files"][0]["path"], "docs/plan.md")
        self.assertIn("no such file", self.tool(self.t, "dendro_output", kind="report", title="周报", sections=[dict(section, files=["none.md"])])[1]["refused"][0])

    def test_a_new_version_takes_the_place_of_the_old(self):
        first = self.tool(self.t, "dendro_output", kind="report", title="周报", sections=[self.section])[1]
        second = self.tool(self.t, "dendro_output", kind="report", title="周报二", sections=[self.section], replaces=first["id"])[1]
        self.assertEqual([o["id"] for o in companion.outputs(self.t.events())], [second["id"]])
        self.assertIn("not an output", self.tool(self.t, "dendro_output", kind="report", title="x", sections=[self.section], replaces=self.event["id"])[1]["refused"][0])

    def test_commits_of_days_nobody_read_come_with_the_material(self):
        seen = companion.material(self.t, "report")
        self.assertEqual([c["text"] for c in seen["unread_commits"]], ["昨天的提交"])

    def test_a_file_made_from_it_is_kept(self):
        self.write("deck.pptx", "pptx")
        out = self.tool(self.t, "dendro_output", kind="slides", title="组会", sections=[self.section], file="deck.pptx")[1]
        self.assertEqual(out["body"]["data"]["file"]["name"], "deck.pptx")
        self.assertIn(out["body"]["data"]["file"]["blob"], self.t.blobs())
        self.assertIn("no such file", self.tool(self.t, "dendro_output", kind="slides", title="组会", sections=[self.section], file="none.pptx")[1]["refused"][0])

    def test_an_output_knows_when_records_have_passed_it(self):
        out = self.tool(self.t, "dendro_output", kind="report", title="周报", sections=[self.section])[1]
        self.assertEqual(companion.outputs(self.t.events())[0]["newer_records"], 0)
        self.t.append(ME, "said", {"text": "后来"}, SIMS)
        self.assertEqual(companion.outputs(self.t.events())[0], {"id": out["id"], "kind": "report", "title": "周报", "day": companion.day_of(out), "newer_records": 1})
        self.assertEqual(companion.material(self.t, "report")["earlier"][0]["newer_records"], 1)

    def test_prompts_start_the_same_way(self):
        ask = lambda method, **params: mcp.answer(self.t.root, ME, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        self.assertEqual({p["name"] for p in ask("prompts/list")["result"]["prompts"]}, set(mcp.PROMPTS))
        self.assertIn("dendro_material", ask("prompts/get", name="slides", arguments={"audience": "组会"})["result"]["messages"][0]["content"]["text"])
        self.assertIn("error", ask("prompts/get", name="poem"))

    def test_readings_stay_private_when_published(self):
        self.t.append(ME, "problem", {"text": "内部问题"}, refs=[{"rel": "based_on", "to": self.event["id"]}])
        self.t.append(ME, "reply", {"text": "内部回答"}, {"kind": "agent", "name": "claude"})
        self.tool(self.t, "dendro_output", kind="report", title="内部报告", sections=[self.section])
        shown = json.dumps(web.bundle([self.t.root], private=False), ensure_ascii=False)
        for text in ("内部问题", "内部回答", "内部报告"):
            self.assertNotIn(text, shown)

    def test_a_family_is_one_of_those_the_site_knows(self):
        fact = {"field": "type", "value": "网站", "basis": "record", "refs": [self.event["id"]]}
        self.assertFalse(self.tool(self.t, "dendro_profile", intro="一个网站。", family="software", facts=[fact])[0])
        self.assertEqual([e for e in self.t.events() if e["type"] == "profile"][0]["body"]["data"]["family"], "software")
        self.assertIn("family", self.tool(self.t, "dendro_profile", intro="一个网站。", family="art", facts=[fact])[1]["refused"][0])
