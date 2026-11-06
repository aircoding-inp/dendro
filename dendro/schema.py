"""What an event is. Everything a research project does is recorded as one, and the rest of Dendro only reads them.

Two families share one log. Structural events change the argument graph: nodes and the edges between them. Trace events say what
happened: an idea, a direction, a correction, a decision, a run, a result, a reading of it. People read the graph and never edit
it, so a structural event is always an agent's or a system's, and what a person said or decided is recorded for them by an agent.
"""
import hashlib
import json
import re
from datetime import datetime

VERSION = 1
ACTOR_KINDS = ("human", "agent", "system")
NODE_KINDS = ("claim", "prior", "paper", "method", "experiment", "run", "resource", "section")
STATUSES = ("proposed", "approved", "queued", "running", "done", "failed", "stopped", "deferred", "dropped")
HAS_STATUS = ("experiment", "run")
RELATIONS = {  # relation: (kinds it starts at, kinds it ends at), read the way the argument runs
    "gap": (("prior", "paper"), ("claim",)),  # this work leaves the gap the claim fills
    "covers": (("prior",), ("paper",)),  # a line of prior work, and one publication in it
    "realized_by": (("claim",), ("method",)),
    "tested_by": (("claim", "method"), ("experiment",)),
    "of": (("run",), ("experiment",)),
    "on": (("run", "experiment"), ("resource",)),
    "states": (("section",), ("claim",)),
    "cites": (("section",), ("paper",)),
}
STRUCTURAL = ("node.put", "node.retire", "edge.put", "edge.drop")
TRACE = ("said", "idea", "direction", "correction", "decision", "design", "survey", "run.start", "run.end", "result", "reading",
         "commit", "change", "reply", "release", "reference", "ticket", "check", "digest", "profile", "problem", "resolved", "output",
         "text", "note")
HUMAN_TYPES = ("said", "idea", "direction", "correction", "decision", "problem", "resolved")  # said is the words as typed; the rest read them
COLLECTED = ("commit", "change", "reply", "release", "ticket", "check")  # only ever copied from a record
OUTCOMES = ("solved", "dropped")  # what became of a problem
FAMILIES = ("research", "software", "work", "other")  # what a project is, which decides the words it is shown in
OUTPUTS = ("report", "slides", "speech", "weekly", "thread")
REF_RELATIONS = ("responds_to", "based_on", "supersedes")
BASES = ("record", "inferred", "unknown")  # a fact in a profile is on the record, read from it, or not known
FIELDS = ("v", "id", "ts", "rec", "type", "actor", "writer", "body", "about", "refs", "source", "prev")
REQUIRED = ("v", "id", "ts", "rec", "type", "actor", "writer", "body", "prev")
NODE_ID = re.compile(r"^([a-z]+):[a-z0-9][a-z0-9._-]*$")
EVENT_ID = re.compile(r"^e_[0-9a-f]{16}$")
WRITER = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BLOB = re.compile(r"^[0-9a-f]{64}(\.[a-z0-9]{1,8})?$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(event):
    """An event's id: a hash of everything else in it, so a changed event no longer has its id."""
    body = {k: v for k, v in event.items() if k != "id"}
    return "e_" + hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()[:16]


def moment(text):
    """An ISO 8601 time with its offset, or None."""
    try:
        when = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else None


def source_key(source):
    """What names the record an event was collected from, or None. Two events with one key are the same record taken twice.
    The first session events were recorded by hand with the message under "message"."""
    ident = (source or {}).get("id", (source or {}).get("message"))
    return f"{source['kind']}:{ident}" if ident else None


def kind_of(node_id):
    """The kind a node id names, or None if it is no node id."""
    found = NODE_ID.match(node_id) if isinstance(node_id, str) else None
    return found.group(1) if found and found.group(1) in NODE_KINDS else None


def _text(body, key, required=False):
    value = body.get(key)
    if value is None:
        return [f"{key} is required"] if required else []
    return [] if isinstance(value, str) and value.strip() else [f"{key} is not text"]


def _only(body, allowed):
    extra = sorted(set(body) - set(allowed))
    return [f"unknown body fields: {extra}"] if extra else []


def _node_put(body):
    kind = kind_of(body.get("id"))
    if not kind:
        return [f"not a node id: {body.get('id')!r}"]
    out = _only(body, ("id", "title", "summary", "status", "data")) + _text(body, "title") + _text(body, "summary")
    if "status" in body:
        if kind not in HAS_STATUS:
            out.append(f"a {kind} has no status")
        elif body["status"] not in STATUSES:
            out.append(f"unknown status: {body['status']!r}")
    if not isinstance(body.get("data", {}), dict):
        out.append("data is not an object")
    return out


def _node_retire(body):
    out = _only(body, ("id", "reason")) + _text(body, "reason", True)
    return out if kind_of(body.get("id")) else out + [f"not a node id: {body.get('id')!r}"]


def _edge(body, reason):
    out = _only(body, ("rel", "src", "dst", "reason")) + _text(body, "reason", reason)
    rel, kinds = body.get("rel"), [kind_of(body.get(k)) for k in ("src", "dst")]
    if rel not in RELATIONS:
        return out + [f"unknown relation: {rel!r}"]
    if None in kinds:
        return out + ["src and dst must be node ids"]
    starts, ends = RELATIONS[rel]
    return out if kinds[0] in starts and kinds[1] in ends else out + [f"{rel} does not join a {kinds[0]} to a {kinds[1]}"]


def _said(body):
    out = _only(body, ("text", "data")) + _text(body, "text", True)
    return out if isinstance(body.get("data", {}), dict) else out + ["data is not an object"]


def _digest(body):
    out = _said(body)
    day = (body.get("data") or {}).get("day")
    return out if isinstance(day, str) and DAY.match(day) else out + ["a digest says which day it reads, as data.day = YYYY-MM-DD"]


def _fact(fact):
    if not isinstance(fact, dict) or _text(fact, "field", True) or set(fact) - {"field", "value", "basis", "refs", "files"}:
        return ["a fact is {field, value, basis, refs, files}"]
    name, basis = fact["field"], fact.get("basis")
    if basis not in BASES:
        return [f"{name}: basis is one of {', '.join(BASES)}"]
    if basis == "unknown":
        return [f"{name}: what is unknown has no value"] if fact.get("value") else []
    out = [f"{name}: has no value"] if _text(fact, "value", True) else []
    return out if fact.get("refs") or fact.get("files") else out + [f"{name}: no evidence: say what it rests on, or call it unknown"]


def _profile(body):
    out, facts = _said(body), (body.get("data") or {}).get("facts")
    if (body.get("data") or {}).get("family", FAMILIES[0]) not in FAMILIES:
        out.append(f"family is one of {', '.join(FAMILIES)}")
    if not isinstance(facts, list) or not facts:
        return out + ["a profile lists its facts, as data.facts"]
    return out + [reason for fact in facts for reason in _fact(fact)]


def _resolved(body):
    outcome = (body.get("data") or {}).get("outcome")
    return _said(body) + ([] if outcome in OUTCOMES else [f"data.outcome is one of {', '.join(OUTCOMES)}"])


def _section(section):
    if not isinstance(section, dict) or _text(section, "heading", True) or _text(section, "text", True) or set(section) - {"heading", "text", "evidence", "files"}:
        return ["a section is {heading, text, evidence, files}"]
    evidence = section.get("evidence", [])
    good = isinstance(evidence, list) and all(isinstance(x, str) and EVENT_ID.match(x) for x in evidence)
    return [] if good and (evidence or section.get("files")) else [f"{section['heading']}: no evidence: every section points at the events or files it rests on"]


def _output(body):
    out, data = _said(body), body.get("data") or {}
    if data.get("kind") not in OUTPUTS:
        out.append(f"data.kind is one of {', '.join(OUTPUTS)}")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        return out + ["an output lists its sections, as data.sections"]
    return out + [reason for section in sections for reason in _section(section)]


def grounded(event):
    """A reading stands on what it read: it points at events, and what its parts point at is among the event's own refs."""
    kind, data = event["type"], event["body"].get("data") or {}
    pointed = {r["to"] for r in event.get("refs", [])}
    if kind in ("digest", "problem"):
        return [] if pointed else [f"a {kind} points back at the events it reads"]
    if kind == "resolved":
        return [] if any(r["rel"] == "responds_to" for r in event.get("refs", [])) else ["resolved responds_to the problem it ends"]
    if kind == "output":
        return [f"{s['heading']}: its evidence is not among the event's refs" for s in data["sections"] if set(s.get("evidence", ())) - pointed]
    return [f"{fact['field']}: its refs are not among the event's refs" for fact in data["facts"] if set(fact.get("refs") or ()) - pointed]


BODIES = {"node.put": _node_put, "node.retire": _node_retire, "edge.put": lambda b: _edge(b, False),
          "edge.drop": lambda b: _edge(b, True), **{t: _said for t in TRACE}, "digest": _digest, "profile": _profile,
          "resolved": _resolved, "output": _output}


def problems(event):
    """Everything wrong with one event taken alone. Whether it fits the log so far is the state's to say."""
    if not isinstance(event, dict):
        return ["not an object"]
    out = [f"missing {k}" for k in REQUIRED if k not in event]
    extra = sorted(set(event) - set(FIELDS))
    if extra:
        out.append(f"unknown fields: {extra}")
    if out:
        return out
    if event["v"] != VERSION:
        out.append(f"schema version {event['v']!r}, not {VERSION}")
    happened, recorded = moment(event["ts"]), moment(event["rec"])
    if not happened or not recorded:
        out.append("ts and rec are ISO 8601 times with an offset")
    elif happened > recorded:
        out.append("ts is after rec: nothing is recorded before it happens")
    actor = event["actor"]
    if not isinstance(actor, dict) or actor.get("kind") not in ACTOR_KINDS or _text(actor, "name", True) or set(actor) - {"kind", "name"}:
        out.append("actor is {kind: human | agent | system, name}")
        actor = {}
    if not isinstance(event["writer"], str) or not WRITER.match(event["writer"]):
        out.append("writer is lower-case letters, digits and hyphens")
    check = BODIES.get(event["type"])
    if not check:
        out.append(f"unknown type: {event['type']!r}")
    elif not isinstance(event["body"], dict):
        out.append("body is not an object")
    else:
        out += check(event["body"])
    if actor.get("kind") == "human":
        if event["type"] in STRUCTURAL:
            out.append("people do not edit the graph: a structural event is an agent's or a system's")
        elif event["type"] not in HUMAN_TYPES:
            out.append(f"a person's events are {', '.join(HUMAN_TYPES)}")
    about = event.get("about", [])
    if not isinstance(about, list) or not all(kind_of(x) for x in about):
        out.append("about is a list of node ids")
    refs = event.get("refs", [])
    good = isinstance(refs, list) and all(isinstance(r, dict) and set(r) == {"rel", "to"} and r["rel"] in REF_RELATIONS
                                         and isinstance(r["to"], str) and EVENT_ID.match(r["to"]) for r in refs)
    if not good:
        out.append(f"refs is a list of {{rel: {' | '.join(REF_RELATIONS)}, to: an event id}}")
    source = event.get("source", {"kind": "none"})
    if not isinstance(source, dict) or not isinstance(source.get("kind"), str) or not isinstance(source.get("id", ""), str):
        out.append("source is {kind, id, ...}: the kind of record it came from and what names that record")
    if good and not out and event["type"] in ("digest", "profile", "problem", "resolved", "output"):
        out += grounded(event)
    if event["prev"] is not None and not (isinstance(event["prev"], str) and EVENT_ID.match(event["prev"])):
        out.append("prev is an event id or null")
    if not out and event["id"] != digest(event):
        out.append("id is not the hash of the event")
    return out
