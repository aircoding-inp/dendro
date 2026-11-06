"""Collectors turn records that already exist into events, so that keeping the trace costs nobody any effort.

A collector yields items for Trace.extend. Each has a source {kind, id} naming the record it came from, so running a collector
again adds only what is new. A collector reads and copies; it does not judge. Reading what was collected, such as telling an idea
from a correction, is an agent's work and is recorded as further events that point back at these.

`items` is the open door: a project's own exporter writes one item per line for records only it understands, such as its
experiment ledgers, and they are taken in the same way.
"""
import json

from dendro.collect import bibtex, claude_session, codex_session, files, git, github, latex, references


def prepared(path):
    """Items already made by another program: a JSON lines file, one item per line."""
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def attached(path, node, field, keep):
    """A file that belongs to a node, such as a method's figure or a run's log, kept in the trace and named in the node's data."""
    kept = keep(path)
    yield {"type": "node.put", "body": {"id": node, "data": {field: kept}}, "actor": {"kind": "system", "name": "file"},
           "source": {"kind": "file", "id": f"{node}:{field}:{kept['blob'][:16]}", "file": kept["name"]}}


COLLECTORS = {"claude-session": claude_session.items, "codex-session": codex_session.items, "bibtex": bibtex.items, "git": git.items, "latex": latex.items, "items": prepared,
              "file": attached, "files": files.items, "releases": git.tags, "references": references.items, "github": github.items}
KEEPS_FILES = ("latex", "file")


def ready(trace, items):
    """The items that can be written now. An edge waits for a later run while one of its ends is not in the graph, and is left out
    for good once it is there."""
    state = trace.state()
    live = {k for k, n in state.nodes.items() if not n["retired"]} | {i["body"]["id"] for i in items if i["type"] == "node.put"}
    out, edges = [], set(state.edges)
    for item in items:
        if item["type"] == "edge.put":
            edge = tuple(item["body"].get(k) for k in ("rel", "src", "dst"))
            if edge in edges or not {edge[1], edge[2]} <= live:
                continue
            edges.add(edge)
        out.append(item)
    return out


def collect(trace, writer, name, **options):
    """Run one collector into a trace and return the events it added."""
    if name in KEEPS_FILES:
        options = dict(options, keep=trace.keep)
    items = ready(trace, trace.missing(list(COLLECTORS[name](**options))))
    return trace.extend(writer, items) if items else []
