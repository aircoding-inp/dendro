"""Dendro as an MCP server over stdio, so that any agent can read a trace and write to it with tools.

    python -m dendro mcp                               the project in this folder, with its trace kept for it
    python -m dendro --root TRACE --writer NAME mcp    one trace, and nothing collected unasked

It speaks JSON-RPC 2.0, one message per line. The tools are the same operations as the command line; a refused write comes back
as an error result with every reason. Nobody calls these tools by hand. The model does, and what it should do when it connects is
worked out from the trace and sent as the server's instructions. Standard library only.
"""
import json
import os
import sys
from datetime import timedelta

from dendro import companion, schema
from dendro.collect import COLLECTORS, collect
from dendro.store import Trace, now

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
TEXT, LIST, OBJECT = {"type": "string"}, {"type": "array", "items": {"type": "string"}}, {"type": "object"}
REFS = {"type": "array", "items": {"type": "object", "properties": {"rel": {"enum": list(schema.REF_RELATIONS)}, "to": TEXT},
                                  "required": ["rel", "to"]}}
WRITE = {"about": dict(LIST, description="Node ids this concerns."), "refs": dict(REFS, description="Earlier events this points at."),
         "ts": dict(TEXT, description="When it happened, ISO 8601 with offset, if not now."),
         "source": dict(OBJECT, description="{kind, id, ...} of the record this was taken from, if any.")}
VOCABULARY = (f"Node ids are kind:name with kind one of {', '.join(schema.NODE_KINDS)}. Statuses, for experiment and run: "
              f"{', '.join(schema.STATUSES)}. Relations: " + "; ".join(
                  f"{rel} joins {' or '.join(a)} to {' or '.join(b)}" for rel, (a, b) in schema.RELATIONS.items()) + ".")


ABOUT = ("A project's trace: an append-only record of how the work went. People read it; you write it, unasked and without "
         "comment. Commits, file changes and what people typed are collected by themselves. Yours is what only "
         "a reader can add: when a decision, a correction, a problem or a result happens, record it with dendro_say, with by = human:NAME "
         "if a person made it and a ref to what it rests on. Never guess: what the records do not show stays unknown. A `pasted` record "
         "is something a person pasted, often another agent's words, and not what they said themselves. Asked for a report, slides, a "
         "talk or to sort out the thinking, start from dendro_material.")
HONEST = ("Write in the language the project's people write in, plainly, conclusions first. Say only what the records show: no praise, "
          "no plans nobody stated, no filling a gap with what is likely. Call people by name and do not guess their pronouns.")


PROMPTS = {"report": "Write a report on this project.", "slides": "Make a slide deck on this project.", "speech": "Write a talk on this project.",
           "weekly": "Write this week's update.", "thread": "Sort out how the thinking on this project went."}


def tool(name, description, properties, required=(), reads=False):
    out = {"name": name, "description": description,
           "inputSchema": {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}}
    return dict(out, annotations={"readOnlyHint": True}) if reads else out


ITEM = {"type": "object", "required": ["text", "evidence"], "additionalProperties": False, "properties": {
    "text": TEXT, "evidence": dict(LIST, description="Ids of the events of that day it rests on.")}}
TOOLS = [
    tool("dendro_state", "The argument graph as of a moment: every node and edge. " + VOCABULARY,
         {"at": dict(TEXT, description="ISO 8601 time with offset; now if left out.")}, reads=True),
    tool("dendro_overview", "What the records say about this project, counted and not read: when it ran, how active it is, who works "
         "on it, which areas change most, its file types and telling files, its first and latest events with their ids, its profile, "
         "and what is waiting to be read. Start here to understand a project.", {}, reads=True),
    tool("dendro_day", "The records of one day with their ids, times local: what people said and decided, commits, files changed. "
         "`cut` is how much of a long text is left out; dendro_log with its id gives all of it. A busy day comes in parts: while there is "
         "a `next`, the day is not finished, so call again with start = next before writing about it.",
         {"day": dict(TEXT, description="YYYY-MM-DD"), "start": {"type": "integer", "description": "The `next` of the last reply."}}, ["day"], reads=True),
    tool("dendro_digest", "Write what happened on one day, after reading it with dendro_day: three to six sentences on what moved, "
         "what was decided and what is left open, leaving out what did not matter. Commit subjects can claim more than was done; read the "
         "diff when it matters. " + HONEST,
         {"day": dict(TEXT, description="YYYY-MM-DD"), "text": TEXT,
          "evidence": dict(LIST, description="Ids of the events of that day this rests on. At least one."),
          "problems": {"type": "array", "description": "What went wrong or stands in the way that day and is not among open_problems yet: "
                       "a bug, a failed attempt, a question nobody can answer, a contradiction.", "items": ITEM},
          "results": {"type": "array", "description": "What was measured or found that day, with its numbers, and not recorded yet. Point at "
                      "the record that holds the number; a `reply` reporting it is weaker than a log or a file.", "items": ITEM},
          "decisions": {"type": "array", "description": "Choices made that day and not recorded yet, with by = human:NAME if a person made "
                        "them: what was chosen, and why if the records say.", "items": dict(ITEM, properties=dict(ITEM["properties"], by=TEXT))},
          "resolved": {"type": "array", "description": "Open problems that day ended.", "items": {
              "type": "object", "required": ["problem", "text", "outcome", "evidence"], "additionalProperties": False, "properties": {
                  "problem": dict(TEXT, description="Its id, from open_problems."), "text": dict(TEXT, description="How it ended."),
                  "outcome": {"enum": list(schema.OUTCOMES)}, "evidence": LIST}}}}, ["day", "text", "evidence"]),
    tool("dendro_profile", "Write the project's profile, after dendro_overview and reading its telling_files, and others only as far "
         "as you need: what it is, what it is for, where it stands. A project can be a paper, research, a web app, a library, daily work, or anything else; say what the "
         "records show rather than fitting it to a kind. A new profile replaces the last. " + HONEST,
         {"intro": dict(TEXT, description="One sentence: what this project is."),
          "family": {"enum": list(schema.FAMILIES), "description": "Decides the words the project is shown in: research (papers, "
                     "experiments), software (a product or library), work (daily or client work, documents), other."},
          "facts": {"type": "array", "description": "Cover at least: type, goal, stage, recent focus, outputs, audience, and language "
                    "(the one its people write in). outputs are what the project has made so far. basis record: stated outright in a "
                    "record; inferred: your own reading of records, for anything that needed judgment; unknown: the records do not say, with no value. Use unknown freely, it is the right answer when evidence is thin.",
                    "items": {"type": "object", "required": ["field", "basis"], "additionalProperties": False, "properties": {
                        "field": TEXT, "value": TEXT, "basis": {"enum": list(schema.BASES)},
                        "refs": dict(LIST, description="Ids of the events it rests on."),
                        "files": dict(LIST, description="Paths in the project it rests on; each is kept in the trace as it is now.")}}},
          "missing": dict(LIST, description="What record would answer the unknowns, in a few words each.")}, ["intro", "facts"]),
    tool("dendro_log", "Events in the order things happened, newest last, 200 at most unless limit says otherwise.",
         {"id": dict(TEXT, description="Just this event, in full."),
          "type": dict(LIST, description=f"Keep only these types: {', '.join(schema.STRUCTURAL + schema.TRACE)}."),
          "about": dict(TEXT, description="Keep only events about this node."), "since": TEXT, "until": TEXT,
          "limit": {"type": "integer", "description": "Keep only the last N."}}, reads=True),
    tool("dendro_say", "Record what happened. A person's words or decision are recorded for them with by = human:NAME and one of "
         f"{', '.join(schema.HUMAN_TYPES)}; `said` is their words as typed, the others are a reading of them and should point back "
         "with a based_on ref. A problem needs that ref; `resolved` responds_to the problem and has data.outcome, "
         f"{' or '.join(schema.OUTCOMES)}.",
         dict({"type": {"enum": [t for t in schema.TRACE if t not in schema.COLLECTED + ("digest", "profile", "output")]}, "text": TEXT, "by": dict(TEXT, description="KIND:NAME of who did it, if not you."),
               "data": OBJECT}, **WRITE), ["type", "text"]),
    tool("dendro_node_put", "Add a node, or change the fields given on one that exists. A new node needs a title. Nodes map a research "
         "argument; a project with no argument to map has no need of them. " + VOCABULARY,
         dict({"id": TEXT, "title": TEXT, "summary": TEXT, "status": {"enum": list(schema.STATUSES)},
               "data": dict(OBJECT, description="Further fields; a null value removes that field.")}, **WRITE), ["id"]),
    tool("dendro_node_retire", "Take a node out of the graph. It stays in the record; nothing is deleted.",
         dict({"id": TEXT, "reason": TEXT}, **WRITE), ["id", "reason"]),
    tool("dendro_edge_put", "Join two nodes. " + VOCABULARY, dict({"rel": {"enum": list(schema.RELATIONS)}, "src": TEXT, "dst": TEXT}, **WRITE),
         ["rel", "src", "dst"]),
    tool("dendro_edge_drop", "Remove an edge, saying why.",
         dict({"rel": {"enum": list(schema.RELATIONS)}, "src": TEXT, "dst": TEXT, "reason": TEXT}, **WRITE), ["rel", "src", "dst", "reason"]),
    tool("dendro_material", "Start here for anything written from the trace: a report, slides, a talk, a weekly update, or the thread of "
         "the work, which sorts out how the thinking went. Returns a guide for that kind and the project's records for the span.",
         {"kind": {"enum": list(schema.OUTPUTS)}, "audience": dict(TEXT, description="Who it is for."), "purpose": dict(TEXT, description="What it should achieve."),
          "since": dict(TEXT, description="YYYY-MM-DD"), "until": dict(TEXT, description="YYYY-MM-DD")}, ["kind"]),
    tool("dendro_output", "Keep what was written from the trace, so that a reader can follow each section back to its records.",
         {"kind": {"enum": list(schema.OUTPUTS)}, "title": TEXT, "audience": TEXT,
          "sections": {"type": "array", "items": {"type": "object", "required": ["heading", "text"], "additionalProperties": False, "properties": {
              "heading": TEXT, "text": TEXT, "evidence": dict(LIST, description="Ids of the events it rests on."),
              "files": dict(LIST, description="Paths in the project it rests on; each is kept in the trace as it is now. A section needs evidence, files or both.")}}},
          "file": dict(TEXT, description="Path of a file made from it, such as a .pptx; it is kept in the trace."),
          "replaces": dict(TEXT, description="Id of an earlier output this one takes the place of.")}, ["kind", "title", "sections"]),
    tool("dendro_collect", "Copy records that already exist into the trace; a second run adds only what is new. claude-session and codex-session take "
         "{paths, by, since?, until?, agent?}; bibtex {path}; git {repo}; latex {path, prefix?}; items {path}; file {path, node, field}; "
         "files {folder}; releases {repo}; references {folder}; github {folder}.",
         {"collector": {"enum": list(COLLECTORS)}, "options": OBJECT}, ["collector", "options"]),
    tool("dendro_check", "Whether the trace on disk is sound, with every problem found.", {}, reads=True),
]


def actor(text):
    kind, _, name = text.partition(":")
    return {"kind": kind, "name": name}


def instructions(trace):
    """What an agent should know as it connects, worked out from the trace, since no one will ask it to do any of this."""
    waiting, out = companion.due(trace.events()), [ABOUT]
    if waiting["profile"]:
        out.append("This project's profile is missing or out of date: call dendro_overview, read its telling_files, then dendro_profile.")
    if waiting["days"]:
        out.append(f"Days not read yet: {', '.join(waiting['days'])}. For each, oldest first, call dendro_day and then dendro_digest.")
    if len(out) > 1:
        out.append("This comes after what you are asked, never before it: answer first, then do this before you end the turn, in a "
                   "subagent if you have one. Nobody needs to hear about it.")
    return " ".join(out)


def based(ids):
    return [{"rel": "based_on", "to": x} for x in ids]


def digest(trace, writer, a):
    """A day's reading, and with it the problems, decisions and endings it found, all written or none. Each of those is dated just
    after the last record it rests on, so it falls on the day it happened and not the day it was read."""
    events = trace.events()
    on_that_day = {e["id"]: e for e in events if companion.day_of(e) == a["day"]}
    open_now = {p["id"] for p in companion.issues(events) if p["status"] == "open"}
    found = a.get("problems", []) + a.get("results", []) + a.get("decisions", []) + a.get("resolved", [])
    strays = [x for x in a["evidence"] + [y for f in found for y in f["evidence"]] if x not in on_that_day]
    wrong = [f"not an event of {a['day']}: {x}" for x in strays] + [f"no evidence: {f['text']}" for f in found if not f["evidence"]]
    wrong += [f"not an open problem: {r['problem']}" for r in a.get("resolved", []) if r["problem"] not in open_now]
    if wrong:
        raise ValueError(wrong)
    ids = {e["id"]: e for e in events}
    after = lambda f: max(schema.moment(ids[x]["ts"]) for x in f["evidence"] + [f.get("problem")] if x) + timedelta(seconds=1)
    when = lambda f: after(f).isoformat() if after(f) < now() else None
    items = [{"type": "problem", "body": {"text": p["text"]}, "refs": based(p["evidence"]), "ts": when(p)} for p in a.get("problems", [])]
    items += [{"type": "result", "body": {"text": r["text"]}, "refs": based(r["evidence"]), "ts": when(r)} for r in a.get("results", [])]
    items += [{"type": "decision", "body": {"text": d["text"]}, "actor": actor(d["by"]) if d.get("by") else None, "refs": based(d["evidence"]), "ts": when(d)} for d in a.get("decisions", [])]
    items += [{"type": "resolved", "body": {"text": r["text"], "data": {"outcome": r["outcome"]}}, "ts": when(r),
               "refs": [{"rel": "responds_to", "to": r["problem"]}] + based(r["evidence"])} for r in a.get("resolved", [])]
    written = trace.extend(writer, items + [{"type": "digest", "body": {"text": a["text"], "data": {"day": a["day"]}}, "refs": based(a["evidence"])}])
    return dict(written[-1], also=[{"type": e["type"], "id": e["id"]} for e in written[:-1]]) if items else written[-1]


def output(trace, writer, folder, a):
    events = trace.events()
    known, outputs = {e["id"] for e in events}, {e["id"] for e in events if e["type"] == "output"}
    wrong = [f"{s['heading']}: no such event: {x}" for s in a["sections"] for x in s.get("evidence", ()) if x not in known]
    if a.get("replaces") and a["replaces"] not in outputs:
        wrong.append(f"not an output: {a['replaces']}")
    path = os.path.join(folder or "", a["file"]) if a.get("file") else None
    if path and not os.path.isfile(path):
        wrong.append(f"no such file: {a['file']}")
    if wrong:
        raise ValueError(wrong)
    sections = [{k: v for k, v in s.items() if k != "field"} for s in companion.evidence(trace, folder, [dict(s, field=s["heading"]) for s in a["sections"]])]
    data = {"kind": a["kind"], "sections": sections, **({"audience": a["audience"]} if a.get("audience") else {}), **({"file": trace.keep(path)} if path else {})}
    return trace.append(writer, "output", {"text": a["title"], "data": data}, refs=based(sorted({x for s in sections for x in s.get("evidence", ())})) + ([{"rel": "supersedes", "to": a["replaces"]}] if a.get("replaces") else []))


def profile(trace, writer, folder, a):
    facts = companion.evidence(trace, folder, a["facts"])
    data = {"facts": facts, **{k: a[k] for k in ("family", "missing") if a.get(k)}}
    return trace.append(writer, "profile", {"text": a["intro"], "data": data}, refs=based(sorted({x for fact in facts for x in fact.get("refs") or ()})))


def call(trace, writer, name, a, folder=None):
    """One tool call. Raises ValueError with the reasons when a write is refused."""
    written = {"about": a.get("about", ()), "refs": a.get("refs", ()), "ts": a.get("ts"), "source": a.get("source")}
    fields = lambda *keys: {k: a[k] for k in keys if a.get(k) is not None}
    if name == "dendro_state":
        return trace.state(a.get("at")).to_dict()
    if name == "dendro_overview":
        return companion.overview(trace, folder)
    if name == "dendro_day":
        return companion.day(trace, a["day"], a.get("start", 0))
    if name == "dendro_digest":
        return digest(trace, writer, a)
    if name == "dendro_profile":
        return profile(trace, writer, folder, a)
    if name == "dendro_material":
        if folder:
            companion.fetch(trace, writer, folder)
        return companion.material(trace, a["kind"], a.get("audience"), a.get("purpose"), a.get("since"), a.get("until"))
    if name == "dendro_output":
        return output(trace, writer, folder, a)
    if name == "dendro_log":
        since, until = (schema.moment(a[k]) if a.get(k) else None for k in ("since", "until"))
        rows = [e for e in trace.events() if (not a.get("id") or e["id"] == a["id"]) and (not a.get("type") or e["type"] in a["type"])
                and (not a.get("about") or a["about"] in e.get("about", []))
                and (not since or schema.moment(e["ts"]) >= since) and (not until or schema.moment(e["ts"]) <= until)]
        return rows[-a.get("limit", 200):]
    if name == "dendro_check":
        found = trace.check()
        return {"sound": not found, "problems": found, "events": len(trace.events())}
    if name == "dendro_collect":
        options = dict(a["options"])
        if "by" in options:
            options["by"] = actor(options["by"])
        return {"added": len(collect(trace, writer, a["collector"], **options))}
    if name == "dendro_say":
        raised = {e["id"] for e in trace.events() if e["type"] == "problem"}
        if a["type"] == "resolved" and not any(r["rel"] == "responds_to" and r["to"] in raised for r in a.get("refs", ())):
            raise ValueError(["resolved responds_to the problem it ends"])
        return trace.append(writer, a["type"], fields("text", "data"), actor(a["by"]) if a.get("by") else None, **written)
    bodies = {"dendro_node_put": ("node.put", ("id", "title", "summary", "status", "data")), "dendro_node_retire": ("node.retire", ("id", "reason")),
              "dendro_edge_put": ("edge.put", ("rel", "src", "dst")), "dendro_edge_drop": ("edge.drop", ("rel", "src", "dst", "reason"))}
    if name not in bodies:
        raise ValueError([f"no tool named {name}"])
    type_, keys = bodies[name]
    return trace.append(writer, type_, fields(*keys), **written)


def answer(root, writer, message, folder=None):
    """The reply to one JSON-RPC message, or None for a notification. folder is the project, when the trace keeps itself."""
    method, ident = message.get("method"), message.get("id")
    reply = lambda result: {"jsonrpc": "2.0", "id": ident, "result": result}
    if ident is None:
        return None
    if method == "initialize":
        asked, trace = (message.get("params") or {}).get("protocolVersion"), Trace(root)
        if folder:
            companion.catch_up(trace, writer, folder)
        return reply({"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {}, "prompts": {}},
                      "serverInfo": {"name": "dendro", "version": "0.1.0"},
                      "instructions": instructions(trace)})
    if method == "ping":
        return reply({})
    if method == "tools/list":
        return reply({"tools": TOOLS})
    if method == "prompts/list":
        return reply({"prompts": [{"name": k, "description": v, "arguments": [{"name": "audience", "description": "Who it is for"}]} for k, v in PROMPTS.items()]})
    if method == "prompts/get":
        params = message.get("params") or {}
        kind, audience = params.get("name"), (params.get("arguments") or {}).get("audience")
        if kind not in PROMPTS:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": f"no prompt {kind}"}}
        text = f"{PROMPTS[kind]} Call dendro_material with kind {kind}" + (f" for {audience}" if audience else "") + ", follow its guide, and keep the result with dendro_output."
        return reply({"description": PROMPTS[kind], "messages": [{"role": "user", "content": {"type": "text", "text": text}}]})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            out, failed = call(Trace(root), writer, params.get("name"), params.get("arguments") or {}, folder), False
        except ValueError as e:
            out, failed = {"refused": e.args[0] if e.args and isinstance(e.args[0], list) else [str(e)]}, True
        except (OSError, KeyError, TypeError) as e:
            out, failed = {"refused": [f"{type(e).__name__}: {e}"]}, True
        return reply({"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "isError": failed})
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"no method {method}"}}


def serve(root, writer, stdin=None, stdout=None, folder=None):
    stdin, stdout = stdin or sys.stdin.buffer, stdout or sys.stdout.buffer
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except ValueError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        else:
            out = answer(root, writer, message, folder)
        if out is not None:
            stdout.write(json.dumps(out, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()
