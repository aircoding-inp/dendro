"""The interface agents write through. Every command prints JSON; a refused write prints its reasons and exits 2.

    dendro [--root DIR] [--writer NAME] COMMAND ...

    init PROJECT                         start a trace
    say TYPE TEXT [--by KIND:NAME] ...   record what happened: idea, direction, correction, decision, design, run.start,
                                         run.end, result, reading, text, note
    node put ID [--title ...] ...        add a node, or change the fields given
    node retire ID --reason ...
    edge put REL SRC DST
    edge drop REL SRC DST --reason ...
    collect claude-session PATH... --by human:NAME [--since T] [--until T]
                                         what a person typed in Claude Code sessions, as said events
    collect codex-session PATH... --by human:NAME [--since T] [--until T]
                                         the same from Codex rollouts
    collect bibtex FILE                  the works in a BibTeX file, as paper nodes
    collect git REPO                     a repository's commits
    collect latex MAIN.tex [--prefix P]  a paper's sections with their text, and the works each cites
    collect items FILE.jsonl             items a project's own exporter prepared, one per line
    collect file PATH --node ID --field NAME   a file that belongs to a node, kept in the trace
    collect files FOLDER                 files that changed: uncommitted work in a repository, every file in any other folder
    collect releases REPO                a repository's tags
    collect references FOLDER            what a project declares and links to: packages, repositories, works
    collect github FOLDER                issues, pull requests and failed checks, through gh
    hook [--by human:NAME] [--from codex]   for a client's end-of-turn hook: what was typed in the session it names on stdin; never
                                         stops the session
    connect [claude|codex]               give these clients, or all found, the server, the hook and the skill
    log [--type T] [--about ID] ...      events in the order things happened
    state [--at TIME]                    the graph as of a moment
    check                                whether the trace on disk is sound
    serve [ROOT ...] [--port N] [--public]   the read-only site on localhost, for these traces, ./trace, or all under ~/.dendro
    export OUT [ROOT ...] [--public]     the same site as files in a folder; --public leaves out what people said, sources, local
                                         paths, machines and every kept file that is not an image
    mcp                                  the same operations as tools, for an agent, over stdio (Model Context Protocol)

--root defaults to $DENDRO_ROOT, then ./trace. --writer defaults to $DENDRO_WRITER and names the agent that is recording; --by
names who did the thing when that is someone else, such as the person whose decision this is.

With neither --root nor $DENDRO_ROOT, mcp and hook keep the trace of the project they run in: ./trace if it has one, otherwise a
folder under ~/.dendro, made on first use. They then collect its commits, changed files and sessions by themselves.
"""
import argparse
import json
import os
import sys

from dendro import companion, connect, mcp, schema, web
from dendro.collect import collect
from dendro.store import Trace


def show(value):
    print(json.dumps(value, ensure_ascii=False))


def actor(text):
    kind, _, name = text.partition(":")
    return {"kind": kind, "name": name}


def ref(text):
    rel, _, to = text.partition(":")
    return {"rel": rel, "to": to}


def parser():
    ap = argparse.ArgumentParser(prog="dendro", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("DENDRO_ROOT"))
    ap.add_argument("--writer", default=os.environ.get("DENDRO_WRITER"))
    sub = ap.add_subparsers(dest="command", required=True)

    def write(name, into=sub):
        p = into.add_parser(name)
        p.add_argument("--by", type=actor, help="KIND:NAME of who did it, if not the writer")
        p.add_argument("--about", action="append", default=[], help="a node this concerns; repeatable")
        p.add_argument("--ref", action="append", default=[], type=ref, help="REL:EVENT_ID; repeatable")
        p.add_argument("--ts", help="when it happened, if not now")
        p.add_argument("--source", type=json.loads, help="where the record came from, as JSON")
        return p

    sub.add_parser("init").add_argument("project")
    p = write("say")
    p.add_argument("type", choices=schema.TRACE)
    p.add_argument("text")
    p.add_argument("--data", type=json.loads)

    node = sub.add_parser("node").add_subparsers(dest="action", required=True)
    p = write("put", node)
    p.add_argument("id")
    for name in ("title", "summary", "status"):
        p.add_argument("--" + name)
    p.add_argument("--data", type=json.loads)
    p = write("retire", node)
    p.add_argument("id")
    p.add_argument("--reason", required=True)

    edge = sub.add_parser("edge").add_subparsers(dest="action", required=True)
    for name in ("put", "drop"):
        p = write(name, edge)
        for field in ("rel", "src", "dst"):
            p.add_argument(field)
        p.add_argument("--reason", required=name == "drop")

    source = sub.add_parser("collect").add_subparsers(dest="collector", required=True)
    for name in ("claude-session", "codex-session"):
        p = source.add_parser(name)
        p.add_argument("paths", nargs="+", help="transcripts, or folders of them")
        p.add_argument("--by", type=actor, required=True, help="the person who typed, as human:NAME")
        p.add_argument("--since")
        p.add_argument("--until")
    source.add_parser("bibtex").add_argument("path")
    source.add_parser("git").add_argument("repo")
    p = source.add_parser("latex")
    p.add_argument("path")
    p.add_argument("--prefix", default="")
    source.add_parser("items").add_argument("path")
    p = source.add_parser("file")
    p.add_argument("path")
    p.add_argument("--node", required=True)
    p.add_argument("--field", required=True)

    source.add_parser("files").add_argument("path")
    source.add_parser("releases").add_argument("repo")
    source.add_parser("references").add_argument("path")
    source.add_parser("github").add_argument("path")

    p = sub.add_parser("hook")
    p.add_argument("--by", type=actor, help="the person who typed, as human:NAME")
    p.add_argument("--from", dest="client", choices=["claude", "codex"], default="claude")
    sub.add_parser("connect").add_argument("client", nargs="?", choices=["claude", "codex"])

    p = sub.add_parser("log")
    p.add_argument("--type", action="append", default=[])
    p.add_argument("--about")
    p.add_argument("--since")
    p.add_argument("--until")
    sub.add_parser("state").add_argument("--at")
    sub.add_parser("check")
    p = sub.add_parser("serve")
    p.add_argument("roots", nargs="*")
    p.add_argument("--port", type=int, default=8377)
    p.add_argument("--public", action="store_true")
    sub.add_parser("mcp")
    p = sub.add_parser("export")
    p.add_argument("out")
    p.add_argument("roots", nargs="*")
    p.add_argument("--public", action="store_true")
    return ap


def body_of(a):
    if a.command == "say":
        return a.type, {"text": a.text, "data": a.data}
    fields = ("id", "title", "summary", "status", "data") if (a.command, a.action) == ("node", "put") else \
        ("id", "reason") if a.command == "node" else ("rel", "src", "dst", "reason")
    return f"{a.command}.{a.action}", {k: getattr(a, k) for k in fields}


def hooked(a):
    """A hook must not get in the way of the session it runs in, so what goes wrong is reported and not raised."""
    session = a.client + "-session"
    try:
        told = json.load(sys.stdin)
        path, more = told["transcript_path"], {"ending": told} if a.client == "codex" else {}
        if a.folder:
            done = companion.catch_up(Trace(a.root), a.writer, a.folder, [path], session, **more)
        else:
            done = {"collector": session, "added": len(collect(Trace(a.root), a.writer, session, paths=[path], by=a.by or companion.person(os.getcwd()), agent=companion.AGENTS[session], **more))}
    except (KeyError, TypeError, ValueError, OSError) as e:
        done = {"skipped": str(e)}
    return {} if a.client == "codex" else done  # Codex reads what a Stop hook prints as instructions to itself


def settle(a):
    """Where this command works. mcp and hook find their own project, so that connecting an agent is all anyone has to do."""
    a.folder = None
    if not a.root and a.command in ("mcp", "hook"):
        a.folder = companion.home(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        a.root, a.writer = companion.place(a.folder), a.writer or "agent"
    a.root = a.root or "trace"


def run(a):
    if a.command == "connect":
        return connect.connect(a.client)
    settle(a)
    if a.command == "hook":
        return hooked(a)
    if a.command == "init":
        Trace.create(a.root, a.project)
        return {"project": a.project, "root": os.path.abspath(a.root)}
    if a.command == "mcp":
        Trace(a.root)
        mcp.serve(a.root, a.writer, folder=a.folder)
        return []
    if a.command == "export":
        return {"exported": os.path.abspath(web.export(a.roots or [a.root], a.out, private=not a.public))}
    if a.command == "serve":
        httpd = web.server(a.roots or companion.traces(a.root), a.port, private=not a.public)
        show({"serving": f"http://127.0.0.1:{a.port}/"})
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return {"stopped": True}
    trace = Trace(a.root)
    if a.command == "check":
        return {"sound": not (found := trace.check()), "problems": found, "events": len(trace.events())}
    if a.command == "state":
        return trace.state(a.at).to_dict()
    if a.command == "log":
        since, until = (schema.moment(x) if x else None for x in (a.since, a.until))
        if (a.since and not since) or (a.until and not until):
            raise ValueError(["--since and --until are ISO 8601 times with an offset"])
        return [e for e in trace.events() if (not a.type or e["type"] in a.type) and (not a.about or a.about in e.get("about", []))
                and (not since or schema.moment(e["ts"]) >= since) and (not until or schema.moment(e["ts"]) <= until)]
    if a.command == "collect":
        options = {k: v for k, v in vars(a).items() if k not in ("root", "writer", "command", "collector", "folder")}
        if a.collector in ("files", "references", "github"):
            options = {"folder": a.path}
        return {"collector": a.collector, "added": len(collect(trace, a.writer, a.collector, **options))}
    type_, body = body_of(a)
    return trace.append(a.writer, type_, {k: v for k, v in body.items() if v is not None}, a.by, about=a.about, refs=a.ref,
                        ts=a.ts, source=a.source)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    a = parser().parse_args(argv)
    try:
        out = run(a)
    except ValueError as e:
        reasons = e.args[0] if e.args and isinstance(e.args[0], list) else [str(e)]
        print(json.dumps({"refused": reasons}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError as e:
        print(json.dumps({"refused": [str(e)]}, ensure_ascii=False), file=sys.stderr)
        return 2
    for row in out if isinstance(out, list) else [out]:
        show(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
