"""Codex as a client: what its rollouts give, and connecting it without disturbing what is already there."""
import io
import json
import os
from unittest import mock

from dendro import cli, companion, connect
from dendro.collect import codex_session, collect
from tests.test_companion import Base

SIMS = {"kind": "human", "name": "sims"}
CODEX = companion.AGENTS["codex-session"]


def row(minute, type_, **payload):
    return json.dumps({"timestamp": f"2026-11-06T08:{minute:02d}:00.000Z", "type": type_, "payload": payload})


def meta(cwd, source="vscode"):
    return row(0, "session_meta", id="s1", cwd=cwd, source=source)


def said(minute, id_, text, **fields):
    return row(minute, "event_msg", type="item_completed", item={"type": "UserMessage", "id": id_, "content": [{"type": "text", "text": text}], **fields})


def done(minute, turn, text):
    return row(minute, "event_msg", type="task_complete", turn_id=turn, last_agent_message=text)


class Rollouts(Base):
    def setUp(self):
        super().setUp()
        self.t = self.trace()

    def rollout(self, *rows, name="rollout-a.jsonl"):
        folder = os.path.join(self.tmp, "codex", "sessions", "2026", "11", "06")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
        return path

    def read(self, path, **options):
        return codex_session.items([path], SIMS, agent=CODEX, **options)

    def test_a_person_and_the_turn_they_started(self):
        context = row(1, "response_item", type="message", role="user", content=[{"type": "input_text", "text": "<environment_context>"}])
        found = self.read(self.rollout(meta(self.folder), context, said(1, "m1", "看看结果\n"), done(2, "t1", "结果在这里。")))
        self.assertEqual([(i["type"], i["body"]["text"], i["actor"]["name"]) for i in found], [("said", "看看结果", "sims"), ("reply", "结果在这里。", "codex")])
        self.assertEqual(found[0]["source"], {"kind": "codex-session", "id": "m1", "session": "s1"})

    def test_a_turn_ending_now_is_told_by_the_hook_and_kept_once(self):
        ending = {"turn_id": "t1", "last_assistant_message": "做完了。"}
        path = self.rollout(meta(self.folder), said(1, "m1", "做吧"))
        collect(self.t, "agent", "codex-session", paths=[path], by=SIMS, agent=CODEX, ending=ending)
        self.assertEqual([e["body"]["text"] for e in self.t.events() if e["type"] == "reply"], ["做完了。"])
        path = self.rollout(meta(self.folder), said(1, "m1", "做吧"), done(2, "t1", "做完了。"))
        self.assertEqual(collect(self.t, "agent", "codex-session", paths=[path], by=SIMS, agent=CODEX), [])

    def test_the_hook_of_a_session_nobody_sat_at_adds_nothing(self):
        ending = {"turn_id": "t1", "last_assistant_message": "通过。"}
        self.assertEqual(self.read(self.rollout(meta(self.folder, {"subagent": {"other": "guardian"}})), ending=ending), [])

    def test_the_hook_prints_only_what_codex_can_take(self):
        path = self.rollout(meta(self.folder), said(1, "m1", "做吧"))
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"transcript_path": path, "turn_id": "t1", "last_assistant_message": "好。"}))):
            a = cli.parser().parse_args(["--root", self.t.root, "--writer", "agent", "hook", "--from", "codex"])
            self.assertEqual(cli.run(a), {})
        self.assertEqual(sorted(e["type"] for e in self.t.events() if e["type"] in ("said", "reply")), ["reply", "said"])

    def test_sessions_nobody_sat_at_are_left_out(self):
        for name, source in (("exec", "exec"), ("sub", {"subagent": {"other": "guardian"}})):
            self.assertEqual(self.read(self.rollout(meta(self.folder, source), said(1, "m", "检查"), name=name + ".jsonl")), [])

    def test_the_request_is_kept_without_what_codex_put_around_it(self):
        text = "\n# Files mentioned by the user:\n\n## a.png: C:/a.png\nImage\n\n## My request:\n为什么一直转圈\n\n"
        self.assertEqual(self.read(self.rollout(meta(self.folder), said(1, "m", text)))[0]["body"], {"text": "为什么一直转圈"})

    def test_a_pasted_message_is_marked(self):
        text = "# Files pasted by the user:\n\n## a: C:/a.txt\n\n## My request for Codex:\n看这个"
        self.assertEqual(self.read(self.rollout(meta(self.folder), said(1, "m", text)))[0]["body"], {"text": "看这个", "data": {"pasted": True}})

    def test_what_cannot_be_understood_is_passed_over(self):
        self.assertEqual(self.read(self.rollout("not json", said(1, "m", "没有开头"))), [])
        self.assertEqual([i["body"]["text"] for i in self.read(self.rollout(meta(self.folder), "{broken", '"text"', row(1, "event_msg", type="item_completed", item=3), said(2, "m", "还在")))], ["还在"])

    def test_only_this_project(self):
        path = self.rollout(meta(self.folder), said(1, "m1", "这里"), row(2, "turn_context", cwd=os.path.join(self.tmp, "Other")), said(3, "m2", "别处"))
        self.assertEqual([i["body"]["text"] for i in self.read(path, folder=self.folder)], ["这里"])

    def test_catching_up_finds_the_rollouts_of_this_project(self):
        here = self.rollout(meta(self.folder), said(1, "m1", "这个项目"), done(2, "t1", "好。"))
        self.rollout(meta(os.path.join(self.tmp, "Other")), said(1, "m2", "别的项目"), name="other.jsonl")
        with mock.patch.dict(os.environ, {"CODEX_HOME": os.path.join(self.tmp, "codex")}):
            self.assertEqual(companion.rollouts(self.folder, self.t), [here])
            companion.catch_up(self.t, "agent", self.folder)
            self.assertEqual(sorted(e["body"]["text"] for e in self.t.events() if e["type"] in ("said", "reply")), ["好。", "这个项目"])
            companion.catch_up(self.t, "agent", self.folder)
            self.assertEqual(sum(e["type"] == "said" for e in self.t.events()), 1)

    def test_one_clients_sessions_do_not_hide_the_others(self):
        path = self.rollout(meta(self.folder), said(1, "m1", "旧的"))
        os.utime(path, (1, 1))
        self.t.append("agent", "said", {"text": "Claude 里说的"}, SIMS, source={"kind": "claude-session", "id": "x"})
        self.assertEqual(companion.fresh([path], self.t, "codex-session"), [path])
        self.assertEqual(companion.fresh([path], self.t, "claude-session"), [])


class Connecting(Base):
    def setUp(self):
        super().setUp()
        self.codex = os.path.join(self.tmp, "codex-home")
        self.user = os.path.join(self.tmp, "user")
        os.makedirs(self.codex)
        patch = mock.patch.dict(os.environ, {"CODEX_HOME": self.codex, "USERPROFILE": self.user, "HOME": self.user})
        patch.start()
        self.addCleanup(patch.stop)

    def file(self, name, text=None):
        path = os.path.join(self.codex, name)
        if text is not None:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()

    def test_what_is_there_stays(self):
        theirs = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "theirs"}]}], "Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}
        self.file("hooks.json", json.dumps(theirs))
        self.file("config.toml", 'model = "x"\n\n[mcp_servers.other]\ncommand = "y"\n')
        connect.codex()
        hooks = json.loads(self.file("hooks.json"))["hooks"]
        self.assertEqual(hooks["SessionStart"], theirs["hooks"]["SessionStart"])
        self.assertEqual(hooks["Stop"][0], theirs["hooks"]["Stop"][0])
        self.assertTrue(hooks["Stop"][1]["hooks"][0]["command"].endswith("hook --from codex"))
        self.assertTrue(self.file("config.toml").startswith('model = "x"\n\n[mcp_servers.other]\ncommand = "y"\n\n[mcp_servers.dendro]\n'))

    def test_connecting_again_changes_nothing(self):
        self.file("config.toml", '[mcp_servers.other]\ncommand = "y"\n')
        connect.codex()
        before = self.file("config.toml"), self.file("hooks.json")
        connect.codex()
        self.assertEqual((self.file("config.toml"), self.file("hooks.json")), before)

    def test_a_moved_checkout_replaces_its_own_lines_only(self):
        self.file("config.toml", '[mcp_servers.dendro]\ncommand = "old"\nargs = []\n\n[features]\nhooks = true\n')
        connect.server(os.path.join(self.codex, "config.toml"))
        text = self.file("config.toml")
        self.assertNotIn('"old"', text)
        self.assertTrue(text.endswith("[features]\nhooks = true\n"))
        self.assertEqual(text.count("[mcp_servers.dendro]"), 1)

    def test_it_starts_from_nothing_and_brings_the_skill(self):
        done = connect.codex()
        self.assertIn("[mcp_servers.dendro]", self.file("config.toml"))
        self.assertTrue(os.path.exists(os.path.join(done["skill"], "SKILL.md")))


class ConnectingClaude(Base):
    def setUp(self):
        super().setUp()
        self.base = os.path.join(self.tmp, "claude-home")
        os.makedirs(self.base)
        for patch in (mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.base}), mock.patch("shutil.which", return_value="claude"),
                      mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stderr=""))):
            self.run_ = patch.start()
            self.addCleanup(patch.stop)

    def settings(self):
        with open(os.path.join(self.base, "settings.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_its_hook_and_skill_sit_beside_what_is_there(self):
        with open(os.path.join(self.base, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"model": "x", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}, fh)
        done = connect.claude()
        self.assertEqual(self.settings()["model"], "x")
        stop = self.settings()["hooks"]["Stop"]
        self.assertEqual(stop[0]["hooks"][0]["command"], "mine")
        self.assertTrue(stop[1]["hooks"][0]["command"].endswith("hook --from claude"))
        self.assertNotIn("\\", stop[1]["hooks"][0]["command"])
        self.assertTrue(os.path.exists(os.path.join(done["skill"], "SKILL.md")))

    def test_connecting_again_keeps_one_hook(self):
        connect.claude()
        connect.claude()
        self.assertEqual(len(self.settings()["hooks"]["Stop"]), 1)

    def test_a_refusal_from_claude_is_said(self):
        self.run_.return_value = mock.Mock(returncode=1, stderr="no")
        with self.assertRaises(ValueError):
            connect.claude()


class Finding(Base):
    def test_every_client_found_is_connected(self):
        with mock.patch("shutil.which", side_effect=lambda name: name == "codex"), mock.patch.object(connect, "codex", return_value={"a": 1}), \
                mock.patch.object(connect, "claude") as claude:
            self.assertEqual(connect.connect(), {"codex": {"a": 1}})
        claude.assert_not_called()

    def test_nothing_found_is_said(self):
        with mock.patch("shutil.which", return_value=None), mock.patch.dict(os.environ, {"CODEX_HOME": os.path.join(self.tmp, "none")}):
            with self.assertRaises(ValueError):
                connect.connect()

    def test_with_no_trace_named_every_project_is_shown(self):
        first = companion.place(self.folder)
        self.assertEqual(companion.traces(os.path.join(self.tmp, "none")), [first])
        self.assertEqual(companion.traces(first), [first])
