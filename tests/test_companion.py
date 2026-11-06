"""A trace that keeps itself: nobody calls anything, and nothing is guessed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from unittest import mock

from dendro import Trace, companion, mcp
from dendro.collect import files
from dendro.store import now

ME = "agent"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(folder, *args):
    subprocess.run(["git", "-C", folder, *args], check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)  # as git reports it, where the temporary folder has a short name
        self.folder = os.path.join(self.tmp, "My Project")
        os.makedirs(self.folder)
        env = mock.patch.dict(os.environ, {"DENDRO_HOME": os.path.join(tmp.name, "home"), "CLAUDE_CONFIG_DIR": os.path.join(tmp.name, "claude")})
        env.start()
        self.addCleanup(env.stop)

    def write(self, name, text="x"):
        path = os.path.join(self.folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def repo(self):
        run(self.folder, "init", "-q")
        run(self.folder, "config", "user.name", "Ada Lovelace")
        run(self.folder, "config", "user.email", "ada@example.com")
        self.write("README.md", "# Demo\n")
        run(self.folder, "add", ".")
        run(self.folder, "commit", "-qm", "First commit")

    def trace(self):
        return Trace(companion.place(self.folder))

    def tool(self, trace, name, **arguments):
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        result = mcp.answer(trace.root, ME, message, self.folder)["result"]
        return result["isError"], json.loads(result["content"][0]["text"])

    def yesterday(self, trace, text="昨天的提交"):
        ts = (now() - timedelta(days=1)).isoformat()
        return trace.append("git", "commit", {"text": text, "data": {"hash": "abc"}}, {"kind": "system", "name": "git"}, ts=ts), ts[:10]


class Place(Base):
    def test_a_project_gets_a_trace_outside_itself(self):
        self.repo()
        trace = self.trace()
        self.assertEqual(trace.project, "My Project")
        self.assertEqual(companion.place(self.folder), trace.root)
        self.assertFalse(trace.root.startswith(self.folder))
        self.assertEqual(sorted(os.listdir(self.folder)), [".git", "README.md"])

    def test_a_trace_the_project_keeps_is_used(self):
        Trace.create(os.path.join(self.folder, "trace"), "own")
        self.assertEqual(self.trace().project, "own")

    def test_a_subfolder_and_a_worktree_are_the_same_project(self):
        self.repo()
        self.write("src/a.py")
        self.assertEqual(os.path.normcase(os.path.realpath(companion.home(os.path.join(self.folder, "src")))), os.path.normcase(os.path.realpath(self.folder)))
        other = os.path.join(self.tmp, "wt")
        run(self.folder, "worktree", "add", "-q", other)
        self.assertEqual(os.path.normcase(os.path.realpath(companion.home(other))), os.path.normcase(os.path.realpath(self.folder)))

    def test_the_person_comes_from_git(self):
        self.repo()
        self.assertEqual(companion.person(self.folder), {"kind": "human", "name": "ada-lovelace"})


class CatchUp(Base):
    def test_commits_and_uncommitted_work_arrive_once(self):
        self.repo()
        self.write("notes.txt")
        self.write(".env", "SECRET=1")
        trace = self.trace()
        self.assertEqual(companion.catch_up(trace, ME, self.folder), {"git": 1, "releases": 0, "files": 1, "references": 0})
        self.assertEqual(companion.catch_up(trace, ME, self.folder), {"git": 0, "releases": 0, "files": 0, "references": 0})
        self.assertEqual([e["body"]["text"] for e in trace.events() if e["type"] == "change"], ["notes.txt"])
        self.assertEqual(trace.check(), [])

    def test_a_folder_without_git_is_read_by_its_files(self):
        self.write("a/plan.docx")
        self.write("node_modules/x.js")
        self.write("key.pem")
        trace = self.trace()
        self.assertEqual(companion.catch_up(trace, ME, self.folder), {"files": 1, "references": 0})
        path = self.write("a/plan.docx", "changed")
        os.utime(path, (1_900_000_000, 1_900_000_000))
        self.assertEqual(companion.catch_up(trace, ME, self.folder), {"files": 1, "references": 0})
        self.assertEqual(trace.check(), [], "a time ahead of the clock is held back")

    def test_only_names_are_kept(self):
        self.write("diary.txt", "very private")
        trace = self.trace()
        companion.catch_up(trace, ME, self.folder)
        self.assertNotIn("very private", json.dumps(trace.events()))

    def test_sessions_are_found_by_the_project(self):
        self.repo()
        slug = "".join(c if c.isalnum() else "-" for c in self.folder)
        folder = os.path.join(self.tmp, "claude", "projects", slug)
        os.makedirs(folder)
        entry = {"type": "user", "uuid": "u1", "sessionId": "s", "timestamp": "2026-01-01T00:00:00Z", "origin": {"kind": "human"}, "message": {"content": "做这个"}}
        with open(os.path.join(folder, "s.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        trace = self.trace()
        self.assertEqual(companion.catch_up(trace, ME, self.folder)["claude-session"], 1)
        said = [e for e in trace.events() if e["type"] == "said"]
        self.assertEqual(said[0]["actor"], {"kind": "human", "name": "ada-lovelace"})

    def test_a_failing_source_stops_nothing(self):
        self.repo()
        with mock.patch.dict("dendro.collect.COLLECTORS", {"git": mock.Mock(side_effect=OSError("gone"))}):
            found = companion.catch_up(self.trace(), ME, self.folder)
        self.assertIn("skipped", found["git"])
        self.assertEqual(found["files"], 0)

    def test_two_sessions_do_not_collect_at_once(self):
        self.repo()
        trace = self.trace()
        with trace.held("catch-up"):
            self.assertEqual(companion.catch_up(trace, ME, self.folder), {})
        self.assertEqual(companion.catch_up(trace, ME, self.folder)["git"], 1)

    def test_a_lock_left_behind_is_taken(self):
        trace = self.trace()
        path = os.path.join(trace.root, "events", ME + ".lock")
        open(path, "w").close()
        os.utime(path, (1_000_000, 1_000_000))
        trace.append(ME, "note", {"text": "还能写"})
        self.assertFalse(os.path.exists(path))

    def test_files_named_oddly_are_read(self):
        self.repo()
        self.write("中文 文件.txt")
        self.write("README.md", "changed")
        run(self.folder, "mv", "README.md", "READ.md")
        self.assertEqual({i["body"]["text"] for i in files.items(self.folder)}, {"中文 文件.txt", "READ.md"})


class Waiting(Base):
    def test_a_day_of_work_waits_for_a_reader(self):
        trace = self.trace()
        event, day = self.yesterday(trace)
        self.assertEqual(companion.due(trace.events()), {"days": [day], "profile": True})
        self.assertIn(day, mcp.instructions(trace))
        failed, out = self.tool(trace, "dendro_digest", day=day, text="做了第一次提交。", evidence=[event["id"]])
        self.assertFalse(failed, out)
        self.assertEqual(companion.due(trace.events())["days"], [])
        self.assertNotIn(day, mcp.instructions(trace))

    def test_today_is_not_over(self):
        trace = self.trace()
        trace.append(ME, "note", {"text": "x"})
        trace.append("git", "commit", {"text": "今天", "data": {}}, {"kind": "system", "name": "git"})
        self.assertEqual(companion.due(trace.events())["days"], [])

    def test_an_empty_project_asks_for_nothing(self):
        self.assertEqual(mcp.instructions(self.trace()), mcp.ABOUT)

    def test_only_the_last_week_is_asked_for(self):
        trace = self.trace()
        for back in range(12, 0, -1):
            trace.append("git", "commit", {"text": "x", "data": {}}, {"kind": "system", "name": "git"}, ts=(now() - timedelta(days=back)).isoformat())
        days = companion.due(trace.events())["days"]
        self.assertEqual(days[0], (now() - timedelta(days=companion.RECENT)).date().isoformat())
        self.assertEqual(len(days), companion.UNREAD)

    def test_connecting_collects_and_says_what_waits(self):
        self.repo()
        run(self.folder, "commit", "-q", "--allow-empty", "--date", (now() - timedelta(days=1)).isoformat(), "-m", "Older")
        hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": mcp.PROTOCOLS[0]}}
        trace = self.trace()
        text = mcp.answer(trace.root, ME, hello, self.folder)["result"]["instructions"]
        self.assertEqual(len(trace.events()), 2)
        self.assertIn("Days not read yet", text)
        self.assertIn("dendro_profile", text)
        self.assertLess(len(text), 2000)


class Reading(Base):
    def test_a_digest_needs_events_of_its_day(self):
        trace = self.trace()
        event, day = self.yesterday(trace)
        today = trace.append(ME, "note", {"text": "今天"})
        self.assertIn("points back", self.tool(trace, "dendro_digest", day=day, text="x", evidence=[])[1]["refused"][0])
        self.assertIn("not an event of", self.tool(trace, "dendro_digest", day=day, text="x", evidence=[today["id"]])[1]["refused"][0])
        self.assertTrue(self.tool(trace, "dendro_digest", day="昨天", text="x", evidence=[event["id"]])[0])

    def test_a_fact_rests_on_something_or_is_unknown(self):
        self.write("README.md", "# 一个网站\n")
        trace = self.trace()
        event, _ = self.yesterday(trace)
        facts = lambda *f: self.tool(trace, "dendro_profile", intro="一个网站。", facts=list(f))
        failed, out = facts({"field": "goal", "value": "赚钱", "basis": "inferred"})
        self.assertTrue(failed and "no evidence" in out["refused"][0])
        failed, out = facts({"field": "goal", "value": "赚钱", "basis": "unknown"})
        self.assertTrue(failed and "no value" in out["refused"][0])
        failed, out = facts({"field": "type", "value": "网站", "basis": "record", "files": ["no-such.md"]})
        self.assertTrue(failed and "no such file" in out["refused"][0])
        failed, out = facts({"field": "type", "value": "网站", "basis": "record", "files": ["../outside.md"]})
        self.assertTrue(failed and "no such file" in out["refused"][0])
        failed, out = facts({"field": "type", "value": "网站", "basis": "record", "refs": ["e_0000000000000000"]})
        self.assertTrue(failed)
        failed, out = facts({"field": "type", "value": "网站", "basis": "record", "files": ["README.md"]},
                            {"field": "stage", "value": "刚开始", "basis": "inferred", "refs": [event["id"]]},
                            {"field": "audience", "basis": "unknown"})
        self.assertFalse(failed, out)
        kept = out["body"]["data"]["facts"][0]["files"][0]
        self.assertEqual(kept["path"], "README.md")
        self.assertIn(kept["blob"], trace.blobs())
        self.assertEqual(out["refs"], [{"rel": "based_on", "to": event["id"]}])
        self.assertEqual(trace.check(), [])
        self.assertFalse(companion.due(trace.events())["profile"])

    def test_the_overview_counts_and_does_not_read(self):
        self.repo()
        self.write("src/app.py")
        trace = self.trace()
        companion.catch_up(trace, ME, self.folder)
        seen = self.tool(trace, "dendro_overview")[1]
        self.assertEqual((seen["records"]["commit"], seen["active_days"], seen["telling_files"], seen["people"]), (1, 1, ["README.md"], {"ada lovelace": 1}))
        self.assertEqual(seen["file_types"], {".md": 1})
        self.assertEqual({row["type"] for row in seen["latest"]}, {"commit", "change"})

    def test_a_day_puts_words_before_files(self):
        trace = self.trace()
        ts = (now() - timedelta(days=1)).replace(hour=12).isoformat()
        for i in range(companion.DAY_ROWS + 5):
            trace.append("files", "change", {"text": f"f{i}"}, {"kind": "system", "name": "files"}, ts=ts)
        trace.append(ME, "said", {"text": "这很重要"}, {"kind": "human", "name": "ada"}, ts=ts)
        seen = companion.day(trace, ts[:10])
        self.assertEqual((seen["records"], len(seen["events"]), seen["events"][0]["text"]), (companion.DAY_ROWS + 6, companion.DAY_ROWS, "这很重要"))


    def test_what_is_cut_says_so_and_what_is_pasted_too(self):
        trace = self.trace()
        said = trace.append(ME, "said", {"text": "字" * 500, "data": {"pasted": True}}, {"kind": "human", "name": "ada"})
        row = companion.line(said)
        self.assertEqual((len(row["text"]), row["cut"], row["pasted"]), (companion.CLIP, 500 - companion.CLIP, True))
        self.assertEqual(self.tool(trace, "dendro_log", id=said["id"])[1][0]["body"]["text"], "字" * 500)

    def test_times_are_on_one_clock(self):
        trace = self.trace()
        ts = now() - timedelta(hours=2)
        a = trace.append(ME, "said", {"text": "a"}, {"kind": "human", "name": "ada"}, ts=ts.astimezone(timezone.utc).isoformat())
        b = trace.append("git", "commit", {"text": "b", "data": {}}, {"kind": "system", "name": "git"}, ts=ts.isoformat())
        self.assertEqual(companion.line(a)["at"], companion.line(b)["at"])


class Process(Base):
    def test_the_whole_thing_runs_from_a_bare_project(self):
        self.repo()
        asked = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": mcp.PROTOCOLS[0]}}
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.folder)
        env.pop("DENDRO_ROOT", None)
        done = subprocess.run([sys.executable, REPO, "mcp"], input=json.dumps(asked).encode(), capture_output=True, cwd=self.tmp, env=env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("project's trace", json.loads(done.stdout)["result"]["instructions"])
        self.assertEqual(len(self.trace().events()), 1)

    def test_a_hook_never_stops_a_session(self):
        self.repo()
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.folder)
        env.pop("DENDRO_ROOT", None)
        for payload in (b"not json", b'{"transcript_path": "no/such/file"}'):
            done = subprocess.run([sys.executable, REPO, "hook"], input=payload, capture_output=True, cwd=self.tmp, env=env, timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
