"""Collectors: records that already exist, taken into a trace once."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from dendro import Trace, cli
from dendro.collect import collect

ME = "claude-test"
SIMS = {"kind": "human", "name": "sims"}
HUMAN = {"kind": "human"}


def entry(uuid, text, minute, origin=HUMAN, **extra):
    return dict({"type": "user", "uuid": uuid, "sessionId": "s1", "timestamp": f"2026-11-06T08:{minute:02d}:00.000Z", "origin": origin,
                 "message": {"role": "user", "content": text}}, **extra)


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.join(tmp.name, "records")
        os.makedirs(self.dir)
        self.trace = Trace.create(os.path.join(tmp.name, "trace"), "demo")

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return path

    def transcript(self, name, *entries):
        return self.write(name, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))


class Hook(Base):
    def hook(self, stdin):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            code = cli.main(["--root", self.trace.root, "--writer", ME, "hook", "--by", "human:sims"])
        return code, json.loads(out.getvalue())

    def test_a_turn_ending_takes_what_was_typed_in_that_session(self):
        path = self.transcript("a.jsonl", entry("u1", "做成一个网站", 1))
        self.assertEqual(self.hook(json.dumps({"transcript_path": path})), (0, {"collector": "claude-session", "added": 1}))
        self.assertEqual(self.hook(json.dumps({"transcript_path": path}))[1]["added"], 0)

    def test_a_hook_that_cannot_collect_does_not_stop_the_session(self):
        for stdin in ("not json", "{}", json.dumps({"transcript_path": os.path.join(self.dir, "gone.jsonl")})):
            code, out = self.hook(stdin)
            self.assertEqual(code, 0)


class Sessions(Base):
    def test_only_what_a_person_typed_is_taken(self):
        path = self.transcript(
            "a.jsonl",
            entry("u1", "做成一个网站", 1),
            entry("u2", [{"type": "tool_result", "content": "ok"}], 2, origin=None),
            entry("u3", "This session is being continued", 3, isCompactSummary=True),
            entry("u4", "<cross-session-message>do this</cross-session-message>", 4, origin=None, isMeta=True),
            entry("u5", "task done", 5, origin={"kind": "task-notification"}),
            {"type": "attachment", "uuid": "u6", "sessionId": "s1", "timestamp": "2026-11-06T08:06:00.000Z",
             "attachment": {"type": "queued_command", "prompt": "要以做项目为主", "origin": HUMAN}},
            {"type": "attachment", "uuid": "u7", "sessionId": "s1", "timestamp": "2026-11-06T08:07:00.000Z",
             "attachment": {"type": "queued_command", "prompt": "a peer says", "origin": {"kind": "peer"}}},
            entry("u8", [{"type": "text", "text": "<system-reminder>\nforked\n</system-reminder>\n继续"}], 8),
            entry("u9", "<system-reminder>only this</system-reminder>", 9),
            {"type": "assistant", "uuid": "u10", "timestamp": "2026-11-06T08:10:00.000Z", "message": {"content": "hello"}})
        got = collect(self.trace, ME, "claude-session", paths=[path], by=SIMS)
        self.assertEqual([e["body"]["text"] for e in got], ["做成一个网站", "要以做项目为主", "继续"])
        self.assertEqual({(e["type"], e["actor"]["name"], e["writer"]) for e in got}, {("said", "sims", ME)})
        self.assertEqual((got[0]["ts"], got[0]["source"]),
                         ("2026-11-06T08:01:00+00:00", {"kind": "claude-session", "id": "u1", "session": "s1"}))

    def test_a_second_run_adds_only_what_is_new(self):
        path = self.transcript("a.jsonl", entry("u1", "one", 1))
        self.assertEqual(len(collect(self.trace, ME, "claude-session", paths=[path], by=SIMS)), 1)
        self.transcript("a.jsonl", entry("u1", "one", 1), entry("u2", "two", 2))
        self.assertEqual([e["body"]["text"] for e in collect(self.trace, ME, "claude-session", paths=[path], by=SIMS)], ["two"])
        self.assertEqual(collect(self.trace, ME, "claude-session", paths=[path], by=SIMS), [])
        self.assertEqual(self.trace.check(), [])

    def test_a_fork_repeats_its_parent_and_is_read_once(self):
        self.transcript("parent.jsonl", entry("u1", "one", 1), entry("u2", "parent goes on", 3))
        self.transcript("fork.jsonl", entry("u1", "one", 1), entry("u3", "fork goes on", 2))
        got = collect(self.trace, ME, "claude-session", paths=[self.dir], by=SIMS)
        self.assertEqual([e["body"]["text"] for e in got], ["one", "fork goes on", "parent goes on"])

    def test_a_window_of_time_and_a_paste(self):
        path = self.transcript("a.jsonl", entry("u1", "early", 1), entry("u2", '<pasted_content id="1">another agent</pasted_content>', 5),
                               entry("u3", "late", 9))
        got = collect(self.trace, ME, "claude-session", paths=[path], by=SIMS, since="2026-11-06T08:03:00+00:00",
                      until="2026-11-06T08:07:00+00:00")
        self.assertEqual([e["body"].get("data") for e in got], [{"pasted": True}])

    def test_a_message_recorded_by_hand_is_not_taken_again(self):
        self.trace.append(ME, "idea", {"text": "one"}, SIMS, source={"kind": "claude-session", "session": "s1", "message": "u1"})
        path = self.transcript("a.jsonl", entry("u1", "one", 1), entry("u2", "two", 2))
        self.assertEqual([e["body"]["text"] for e in collect(self.trace, ME, "claude-session", paths=[path], by=SIMS)], ["two"])


BIB = """
@comment{not a work}
@inproceedings{ge2026vtos,
  author    = {Jinchao Ge and Lingqiao Liu and Shuwen Zhao and Lei Wang},
  title     = {{VTOS}: Learning to Orchestrate Vision Tools by Co-Searching Solutions and Observers},
  booktitle = {Proceedings of EMNLP},
  pages     = {22551--22569},
  year      = 2026
}

@article{Zhang2026:TTT,
  author  = "Wenbo Zhang and Xiao Ma",
  title   = {{TTT-VLA}: Test-Time Latent Prompt
             Optimization},
  journal = {arXiv preprint arXiv:2606.03127},
  year    = {2026}
}
"""


class Works(Base):
    def test_each_work_is_a_paper_node(self):
        got = collect(self.trace, ME, "bibtex", path=self.write("main.bib", BIB))
        nodes = self.trace.state().nodes
        self.assertEqual(sorted(nodes), ["paper:ge2026vtos", "paper:zhang2026-ttt"])
        vtos = nodes["paper:ge2026vtos"]
        self.assertEqual(vtos["title"], "VTOS: Learning to Orchestrate Vision Tools by Co-Searching Solutions and Observers")
        self.assertEqual((vtos["data"]["authors"][1], vtos["data"]["year"], vtos["data"]["venue"]),
                         ("Lingqiao Liu", "2026", "Proceedings of EMNLP"))
        ttt = nodes["paper:zhang2026-ttt"]
        self.assertEqual((ttt["title"], ttt["data"]["arxiv"], ttt["data"]["key"]),
                         ("TTT-VLA: Test-Time Latent Prompt Optimization", "2606.03127", "Zhang2026:TTT"))
        self.assertEqual({e["actor"]["kind"] for e in got}, {"system"})

    def test_a_changed_entry_updates_its_node_and_an_unchanged_one_is_left(self):
        path = self.write("main.bib", BIB)
        collect(self.trace, ME, "bibtex", path=path)
        self.assertEqual(collect(self.trace, ME, "bibtex", path=path), [])
        self.write("main.bib", BIB.replace("Proceedings of EMNLP", "EMNLP 2026 Main"))
        got = collect(self.trace, ME, "bibtex", path=path)
        self.assertEqual([e["body"]["id"] for e in got], ["paper:ge2026vtos"])
        self.assertEqual(self.trace.state().nodes["paper:ge2026vtos"]["data"]["venue"], "EMNLP 2026 Main")

    def test_a_paper_joins_the_argument(self):
        collect(self.trace, ME, "bibtex", path=self.write("main.bib", BIB))
        self.trace.append(ME, "node.put", {"id": "prior:loops-elsewhere", "title": "Closed loops in other fields"})
        self.trace.append(ME, "node.put", {"id": "claim:loop", "title": "Evidence-driven improvement"})
        self.trace.append(ME, "edge.put", {"rel": "covers", "src": "prior:loops-elsewhere", "dst": "paper:ge2026vtos"})
        self.trace.append(ME, "edge.put", {"rel": "gap", "src": "paper:ge2026vtos", "dst": "claim:loop"})
        self.trace.append(ME, "survey", {"text": "Knowledge base is per task; cross-task is future work."}, about=["paper:ge2026vtos"])
        self.assertEqual(self.trace.check(), [])


class Batches(Base):
    def test_a_batch_is_written_whole_or_not_at_all(self):
        good = {"type": "node.put", "body": {"id": "claim:a", "title": "a"}}
        with self.assertRaises(ValueError) as caught:
            self.trace.extend(ME, [good, {"type": "node.put", "body": {"id": "claim:b"}}, {"type": "nope", "body": {}}])
        self.assertEqual(self.trace.events(), [])
        self.assertTrue(any(x.startswith("item 2: unknown type") for x in caught.exception.args[0]))
        with self.assertRaises(ValueError) as caught:
            self.trace.extend(ME, [good, {"type": "node.put", "body": {"id": "claim:b"}}])
        self.assertEqual(caught.exception.args[0], ["item 1: a new node needs a title: claim:b"])
        self.assertEqual(len(self.trace.extend(ME, [good, {"type": "note", "body": {"text": "x"}, "about": ["claim:a"]}])), 2)
        self.assertEqual(self.trace.check(), [])

    def test_a_source_names_its_record(self):
        with self.assertRaises(ValueError) as caught:
            self.trace.append(ME, "note", {"text": "x"}, source={"id": "1"})
        self.assertIn("source is {kind, id, ...}", caught.exception.args[0][0])


if __name__ == "__main__":
    unittest.main()
