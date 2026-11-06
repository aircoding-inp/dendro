"""The event format, the append-only store and the graph it folds to."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from dendro import Trace, schema
from dendro.cli import main

AGENT = "claude-test"
SIMS = {"kind": "human", "name": "sims"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.join(tmp.name, "trace")
        self.trace = Trace.create(self.root, "demo")

    def put(self, node_id, writer=AGENT, **fields):
        return self.trace.append(writer, "node.put", dict({"id": node_id, "title": node_id}, **fields))

    def refused(self, *args, **kwargs):
        with self.assertRaises(ValueError) as caught:
            self.trace.append(*args, **kwargs)
        return " | ".join(caught.exception.args[0])


class Format(Base):
    def test_an_event_names_itself_by_its_content(self):
        e = self.put("claim:a")
        self.assertEqual(e["id"], schema.digest(e))
        self.assertEqual(schema.problems(e), [])
        self.assertIn("id is not the hash", schema.problems(dict(e, body={"id": "claim:a", "title": "other"}))[0])

    def test_people_do_not_edit_the_graph(self):
        self.assertIn("people do not edit the graph", self.refused(AGENT, "node.put", {"id": "claim:a", "title": "a"}, SIMS))
        self.put("claim:a")
        self.assertIn("people do not edit the graph", self.refused(AGENT, "node.retire", {"id": "claim:a", "reason": "x"}, SIMS))

    def test_what_a_person_said_is_recorded_for_them(self):
        e = self.trace.append(AGENT, "correction", {"text": "reproduction is no contribution"}, SIMS)
        self.assertEqual((e["actor"], e["writer"]), (SIMS, AGENT))
        self.assertIn("a person's events are", self.refused(AGENT, "result", {"text": "0/40"}, SIMS))

    def test_unknown_things_are_refused(self):
        self.assertIn("unknown type", self.refused(AGENT, "node.delete", {"id": "claim:a"}))
        self.assertIn("not a node id", self.refused(AGENT, "node.put", {"id": "thing:a", "title": "a"}))
        self.assertIn("unknown body fields", self.refused(AGENT, "node.put", {"id": "claim:a", "title": "a", "colour": "red"}))
        self.assertIn("unknown status", self.refused(AGENT, "node.put", {"id": "experiment:a", "title": "a", "status": "wip"}))
        self.assertIn("has no status", self.refused(AGENT, "node.put", {"id": "claim:a", "title": "a", "status": "done"}))
        self.assertIn("text is required", self.refused(AGENT, "note", {}))
        self.assertIn("writer is", self.refused("Claude Test", "note", {"text": "x"}))

    def test_an_edge_joins_only_the_kinds_its_relation_allows(self):
        self.put("claim:a")
        self.put("method:m")
        self.put("experiment:e")
        self.trace.append(AGENT, "edge.put", {"rel": "realized_by", "src": "claim:a", "dst": "method:m"})
        self.assertIn("does not join", self.refused(AGENT, "edge.put", {"rel": "realized_by", "src": "method:m", "dst": "claim:a"}))
        self.assertIn("unknown relation", self.refused(AGENT, "edge.put", {"rel": "likes", "src": "claim:a", "dst": "method:m"}))
        self.assertIn("reason is required", self.refused(AGENT, "edge.drop", {"rel": "realized_by", "src": "claim:a", "dst": "method:m"}))

    def test_nothing_is_recorded_before_it_happens(self):
        self.assertIn("ts is after rec", self.refused(AGENT, "note", {"text": "x"}, ts="2999-01-01T00:00:00+00:00"))
        self.assertIn("ISO 8601", self.refused(AGENT, "note", {"text": "x"}, ts="yesterday"))


class Log(Base):
    def test_each_writer_has_its_own_file_and_chain(self):
        a, b = self.put("claim:a"), self.put("claim:b")
        c = self.put("claim:c", writer="claude-other")
        self.assertEqual((a["prev"], b["prev"], c["prev"]), (None, a["id"], None))
        self.assertEqual(self.trace.writers(), ["claude-other", AGENT])
        self.assertEqual(self.trace.check(), [])

    def test_a_changed_line_is_found(self):
        self.put("claim:a")
        self.put("claim:b")
        path = self.trace.path(AGENT)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace('"title":"claim:a"', '"title":"edited"'))
        self.assertTrue(any("id is not the hash" in x for x in self.trace.check()))

    def test_a_removed_line_is_found(self):
        self.put("claim:a")
        self.put("claim:b")
        self.put("claim:c")
        path = self.trace.path(AGENT)
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.writelines([lines[0], lines[2]])
        self.assertTrue(any("does not follow the event before it" in x for x in self.trace.check()))

    def test_events_read_in_the_order_things_happened(self):
        late = self.put("claim:late")
        early = self.trace.append("adapter-git", "note", {"text": "first commit"}, ts="2026-11-04T10:00:00+10:30")
        self.assertEqual([e["id"] for e in self.trace.events()], [early["id"], late["id"]])

    def test_an_event_must_fit_what_came_before(self):
        self.assertIn("a new node needs a title", self.refused(AGENT, "node.put", {"id": "claim:a"}))
        self.assertIn("no live node", self.refused(AGENT, "edge.put", {"rel": "gap", "src": "prior:p", "dst": "claim:a"}))
        self.assertIn("about a node that does not exist", self.refused(AGENT, "note", {"text": "x"}, about=["claim:a"]))
        self.assertIn("not yet in the log", self.refused(AGENT, "note", {"text": "x"}, refs=[{"rel": "based_on", "to": "e_" + "0" * 16}]))
        self.assertEqual(self.trace.events(), [])

    def test_a_backdated_event_may_not_break_a_later_one(self):
        self.put("claim:a")
        self.assertIn("a new node needs a title", self.refused(AGENT, "node.put", {"id": "claim:a"}, ts="2026-11-01T00:00:00+00:00"))

    def test_a_reference_reaches_an_earlier_event(self):
        said = self.trace.append(AGENT, "correction", {"text": "align with the claim"}, SIMS)
        self.put("claim:a")
        done = self.trace.append(AGENT, "decision", {"text": "drop the reproduction claim"}, about=["claim:a"],
                                 refs=[{"rel": "responds_to", "to": said["id"]}])
        self.assertEqual(done["refs"][0]["to"], said["id"])
        self.assertEqual(self.trace.check(), [])


class Graph(Base):
    def test_fields_given_change_and_the_rest_stay(self):
        self.put("experiment:a", summary="five proposals", status="approved", data={"gpu_hours": [6, 19], "task": "barrier"})
        self.trace.append(AGENT, "node.put", {"id": "experiment:a", "status": "running", "data": {"task": None, "machine": "gpu-box"}})
        node = self.trace.state().nodes["experiment:a"]
        self.assertEqual((node["title"], node["summary"], node["status"]), ("experiment:a", "five proposals", "running"))
        self.assertEqual(node["data"], {"gpu_hours": [6, 19], "machine": "gpu-box"})

    def test_a_retired_node_stays_in_the_record_and_leaves_the_graph(self):
        self.put("claim:a")
        self.put("method:m")
        self.trace.append(AGENT, "edge.put", {"rel": "realized_by", "src": "claim:a", "dst": "method:m"})
        self.trace.append(AGENT, "node.retire", {"id": "method:m", "reason": "folded into another"})
        state = self.trace.state()
        self.assertIsNotNone(state.nodes["method:m"]["retired"])
        self.assertEqual(state.edges, {})
        self.assertIn("retired", self.refused(AGENT, "node.put", {"id": "method:m", "title": "again"}))
        self.assertEqual(len(self.trace.events()), 4)

    def test_the_graph_as_of_a_moment(self):
        self.trace.append("adapter-old", "node.put", {"id": "claim:a", "title": "first wording"}, ts="2026-11-04T09:00:00+10:30")
        self.trace.append("adapter-old", "node.put", {"id": "claim:a", "title": "second wording"}, ts="2026-11-06T09:00:00+10:30")
        self.assertEqual(self.trace.state("2026-11-05T00:00:00+10:30").nodes["claim:a"]["title"], "first wording")
        self.assertEqual(self.trace.state("2026-11-03T00:00:00+10:30").nodes, {})
        self.assertEqual(self.trace.state().nodes["claim:a"]["title"], "second wording")

    def test_the_same_edge_is_not_put_twice_nor_dropped_twice(self):
        self.put("prior:p")
        self.put("claim:a")
        edge = {"rel": "gap", "src": "prior:p", "dst": "claim:a"}
        self.trace.append(AGENT, "edge.put", edge)
        self.assertIn("already there", self.refused(AGENT, "edge.put", edge))
        self.trace.append(AGENT, "edge.drop", dict(edge, reason="not a gap"))
        self.assertIn("no such edge", self.refused(AGENT, "edge.drop", dict(edge, reason="again")))


class Commands(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.join(tmp.name, "trace")

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", self.root, "--writer", AGENT, *argv])
        return code, [json.loads(line) for line in (out.getvalue() or err.getvalue()).splitlines()]

    def test_a_trace_from_start_to_check(self):
        self.assertEqual(self.call("init", "demo")[0], 0)
        self.call("node", "put", "claim:loop", "--title", "执行证据驱动的自主改进")
        self.call("node", "put", "experiment:barrier-a", "--title", "barrier A", "--status", "approved", "--data", '{"gpu_hours": [6, 19]}')
        self.call("node", "put", "method:revision", "--title", "闭环修订")
        self.call("edge", "put", "realized_by", "claim:loop", "method:revision")
        self.call("edge", "put", "tested_by", "method:revision", "experiment:barrier-a")
        code, (said,) = self.call("say", "direction", "先跑完 barrier A 一个完整单元", "--by", "human:sims", "--about", "experiment:barrier-a")
        self.assertEqual((code, said["actor"]["kind"], said["writer"]), (0, "human", AGENT))
        self.call("say", "decision", "队列改为只跑 barrier A", "--ref", "responds_to:" + said["id"])
        code, (state,) = self.call("state")
        self.assertEqual(([n["id"] for n in state["nodes"]], len(state["edges"])),
                         (["claim:loop", "experiment:barrier-a", "method:revision"], 2))
        code, events = self.call("log", "--about", "experiment:barrier-a")
        self.assertEqual([e["type"] for e in events], ["direction"])
        self.assertEqual(self.call("check")[1][0], {"sound": True, "problems": [], "events": 7})

    def test_a_refused_write_says_why_and_writes_nothing(self):
        self.call("init", "demo")
        code, (out,) = self.call("node", "put", "claim:a", "--title", "a", "--by", "human:sims")
        self.assertEqual(code, 2)
        self.assertIn("people do not edit the graph", out["refused"][0])
        self.assertEqual(self.call("log"), (0, []))

    def test_no_trace_is_said_plainly(self):
        code, (out,) = self.call("state")
        self.assertEqual(code, 2)
        self.assertIn("no trace at", out["refused"][0])


if __name__ == "__main__":
    unittest.main()
