"""The MCP server: the protocol's handshake, and the same refusals as every other way in."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from dendro import Trace, mcp

ME = "claude-test"


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.join(tmp.name, "trace")
        Trace.create(self.root, "demo")
        self.next = 0

    def ask(self, method, **params):
        self.next += 1
        return mcp.answer(self.root, ME, {"jsonrpc": "2.0", "id": self.next, "method": method, "params": params})

    def tool(self, name, **arguments):
        result = self.ask("tools/call", name=name, arguments=arguments)["result"]
        return result["isError"], json.loads(result["content"][0]["text"])


class Protocol(Base):
    def test_the_handshake(self):
        hello = self.ask("initialize", protocolVersion="2025-03-26", capabilities={}, clientInfo={"name": "t", "version": "0"})["result"]
        self.assertEqual((hello["protocolVersion"], hello["serverInfo"]["name"], hello["capabilities"]), ("2025-03-26", "dendro", {"tools": {}, "prompts": {}}))
        self.assertEqual(self.ask("initialize", protocolVersion="1999-01-01")["result"]["protocolVersion"], mcp.PROTOCOLS[0])
        self.assertIsNone(mcp.answer(self.root, ME, {"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.ask("ping")["result"], {})
        self.assertEqual(self.ask("resources/list")["error"]["code"], -32601)

    def test_every_tool_says_what_it_takes(self):
        tools = self.ask("tools/list")["result"]["tools"]
        self.assertEqual(len({t["name"] for t in tools}), len(tools))
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertTrue(set(t["inputSchema"]["required"]) <= set(t["inputSchema"]["properties"]), t["name"])
            self.assertTrue(t["description"])

    def test_lines_in_lines_out(self):
        asked = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "dendro_check", "arguments": {}}}]
        out = io.BytesIO()
        mcp.serve(self.root, ME, io.BytesIO(b"".join(json.dumps(m).encode() + b"\n" for m in asked) + b"\nnot json\n"), out)
        lines = [json.loads(line) for line in out.getvalue().decode("utf-8").splitlines()]
        self.assertEqual([m.get("id") for m in lines], [1, 2, None])
        self.assertEqual(lines[2]["error"]["code"], -32700)

    def test_it_runs_as_a_process(self):
        asked = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "dendro_say", "arguments": {"type": "note", "text": "从另一个进程写入"}}}, ensure_ascii=False) + "\n"
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        done = subprocess.run([sys.executable, "-m", "dendro", "--root", self.root, "--writer", ME, "mcp"], input=asked.encode("utf-8"),
                              capture_output=True, cwd=repo, timeout=60)
        event = json.loads(json.loads(done.stdout.decode("utf-8"))["result"]["content"][0]["text"])
        self.assertEqual((event["body"]["text"], event["writer"]), ("从另一个进程写入", ME))
        self.assertEqual(len(Trace(self.root).events()), 1)


class Tools(Base):
    def test_an_agent_builds_and_reads_a_graph(self):
        self.assertEqual(self.tool("dendro_node_put", id="claim:loop", title="Evidence-driven improvement")[0], False)
        self.tool("dendro_node_put", id="experiment:a", title="A", status="approved", data={"question": "does feedback help?"})
        self.tool("dendro_node_put", id="method:m", title="Revision")
        self.tool("dendro_edge_put", rel="realized_by", src="claim:loop", dst="method:m")
        self.tool("dendro_edge_put", rel="tested_by", src="method:m", dst="experiment:a")
        failed, said = self.tool("dendro_say", type="said", text="先跑 A", by="human:sims", about=["experiment:a"])
        self.assertEqual((failed, said["actor"]), (False, {"kind": "human", "name": "sims"}))
        self.tool("dendro_say", type="direction", text="A first", by="human:sims", refs=[{"rel": "based_on", "to": said["id"]}])
        failed, state = self.tool("dendro_state")
        self.assertEqual((len(state["nodes"]), len(state["edges"])), (3, 2))
        failed, log = self.tool("dendro_log", type=["said", "direction"], limit=1)
        self.assertEqual([e["type"] for e in log], ["direction"])
        self.assertEqual(self.tool("dendro_check"), (False, {"sound": True, "problems": [], "events": 7}))

    def test_a_refused_write_is_an_error_with_its_reasons(self):
        failed, out = self.tool("dendro_node_put", id="claim:a", title="a", source={"id": "x"})
        self.assertTrue(failed)
        self.assertIn("source is {kind, id, ...}", out["refused"][0])
        failed, out = self.tool("dendro_edge_put", rel="gap", src="prior:p", dst="claim:a")
        self.assertEqual((failed, out["refused"]), (True, ["no live node: prior:p", "no live node: claim:a"]))
        self.assertEqual(self.tool("dendro_node_retire", id="claim:a", reason="x")[0], True)
        self.assertEqual(self.tool("dendro_nothing")[1], {"refused": ["no tool named dendro_nothing"]})
        self.assertEqual(Trace(self.root).events(), [])

    def test_no_tool_lets_a_person_edit_the_graph(self):
        names = {t["name"]: t for t in self.ask("tools/list")["result"]["tools"]}
        for name in ("dendro_node_put", "dendro_node_retire", "dendro_edge_put", "dendro_edge_drop"):
            self.assertNotIn("by", names[name]["inputSchema"]["properties"])
        failed, out = self.tool("dendro_say", type="result", text="0/40", by="human:sims")
        self.assertTrue(failed and "a person's events are" in out["refused"][0])

    def test_collecting_through_a_tool(self):
        path = os.path.join(os.path.dirname(self.root), "main.bib")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("@article{a2026, title = {A}, year = {2026}}\n")
        self.assertEqual(self.tool("dendro_collect", collector="bibtex", options={"path": path}), (False, {"added": 1}))
        self.assertEqual(self.tool("dendro_collect", collector="bibtex", options={"path": path}), (False, {"added": 0}))


if __name__ == "__main__":
    unittest.main()
