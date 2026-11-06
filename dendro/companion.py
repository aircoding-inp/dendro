"""A trace that keeps itself: where it lives, what is collected without being asked, and what is still waiting for a reader.

Nothing here needs a person or a model. An MCP server cannot wake an agent, so collecting does not wait for one: it runs when the
server starts and when a turn ends, and everything keeps the time it happened, so a day nobody opened a session is still recorded
on its own date. Reading is an agent's work. `due` says which days have no digest, and the server tells each agent that connects.
`material` gathers what the readings add up to, for whatever is written from them.
"""
import getpass
import glob
import hashlib
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import timedelta

from dendro import schema
from dendro.collect import codex_session, collect, files
from dendro.store import Trace, now

WORK = ("said", "commit", "change", "run.start", "run.end", "result", "idea", "direction", "correction", "decision")
SIGNS = ("README.md", "README.rst", "README.txt", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "setup.py", "requirements.txt",
         "package.json", "Cargo.toml", "go.mod", "pom.xml", "Dockerfile", "main.tex", "paper.tex", "references.bib")
RECENT = 7  # days back an agent is asked to read; older ones stay in the log
UNREAD = 3  # days it is asked to read in one session, so the backlog never outweighs the work
STALE = 7  # days of new work after which a profile is due again
DAY_ROWS = 150
DAY_TEXT = 18000  # characters of a day's records in one reply, under what a client takes from a tool
CLIP = 400
PACE = 3600  # seconds between asks of a service on the network
AGENT = {"kind": "agent", "name": "claude"}
AGENTS = {"claude-session": AGENT, "codex-session": {"kind": "agent", "name": "codex"}}
MATERIAL = {"digests": 9000, "decisions": 5000, "problems": 4000, "results": 3000, "unread_commits": 4000}  # characters of each kept in one reply
GUIDES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guides")


def git(folder, *args):
    done = subprocess.run(["git", "-C", folder, *args], capture_output=True, encoding="utf-8", errors="replace")
    return done.stdout.strip() if done.returncode == 0 else ""


def home(path):
    """The project this folder belongs to: the top of its repository, the same for all its worktrees, or the folder itself."""
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if os.path.basename(common) == ".git":
        return os.path.abspath(os.path.dirname(common))
    return os.path.abspath(git(path, "rev-parse", "--show-toplevel") or path)


def place(folder):
    """Where this project's trace is, made if it is not there. A project may keep its own at ./trace; otherwise nothing is added
    to the project."""
    own = os.path.join(folder, "trace")
    if os.path.exists(os.path.join(own, "dendro.json")):
        return own
    name = os.path.basename(folder.rstrip("\\/")) or "root"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    base = os.environ.get("DENDRO_HOME") or os.path.join(os.path.expanduser("~"), ".dendro")
    root = os.path.join(base, f"{slug}-{hashlib.sha256(os.path.normcase(folder).encode('utf-8')).hexdigest()[:8]}")
    if not os.path.exists(os.path.join(root, "dendro.json")):
        try:
            Trace.create(root, name)
        except FileExistsError:
            pass  # another session of this project got there first
    return root


def traces(root):
    """What to show when no trace is named: this one if it is here, or every project kept under the home."""
    if os.path.exists(os.path.join(root, "dendro.json")):
        return [root]
    base = os.environ.get("DENDRO_HOME") or os.path.join(os.path.expanduser("~"), ".dendro")
    found = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(base, "*", "dendro.json")))
    if not found:
        raise ValueError(["no traces yet: connect an agent and work in a project"])
    return found


def person(folder):
    name = git(folder, "config", "user.name") or getpass.getuser()
    return {"kind": "human", "name": re.sub(r"\s+", "-", name.strip().lower())}


def sessions(folder, trace):
    """Claude Code's transcripts for this project that may hold something new."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return fresh(glob.glob(os.path.join(base, "projects", re.sub(r"[^A-Za-z0-9]", "-", folder), "*.jsonl")), trace, "claude-session")


def rollouts(folder, trace):
    """Codex's rollouts of sessions in this project that may hold something new. Codex files them by date, not by project."""
    base = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    paths = glob.glob(os.path.join(base, "sessions", "**", "*.jsonl"), recursive=True) + glob.glob(os.path.join(base, "archived_sessions", "*.jsonl"))
    return [p for p in fresh(paths, trace, "codex-session") if codex_session.started_in(p, folder)]


def fresh(paths, trace, kind):
    """The session files written to since this kind of session was last collected."""
    seen = [schema.moment(e["rec"]) for e in trace.events() if (e.get("source") or {}).get("kind") == kind]
    if not seen:
        return paths
    since = (max(seen) - timedelta(hours=1)).timestamp()
    return [p for p in paths if os.path.getmtime(p) >= since]


def catch_up(trace, writer, folder, transcripts=None, session="claude-session", **options):
    """Collect what is new, from every record this project has, and with transcripts, from those sessions of this kind. A source
    that fails is passed over: this runs where nobody is waiting for it, and the next run tries again."""
    added = {}
    if os.path.normcase(folder) == os.path.normcase(os.path.expanduser("~")):
        return added
    try:
        with trace.held("catch-up", wait=0 if transcripts is None else 5):
            sources = [("files", {"folder": folder}), ("references", {"folder": folder})]
            if git(folder, "rev-parse", "--verify", "HEAD"):
                sources[:0] = [("git", {"repo": folder}), ("releases", {"repo": folder})]
            found = {"claude-session": sessions(folder, trace), "codex-session": rollouts(folder, trace)} if transcripts is None else {session: transcripts}
            sources += [(name, {"paths": paths, "by": person(folder), "agent": AGENTS[name], "folder": folder, **options}) for name, paths in found.items() if paths]
            for name, options in sources:
                added[name] = taken(trace, writer, name, options)
    except ValueError:
        pass  # another session is collecting the same records
    if transcripts is not None:
        added.update(fetch(trace, writer, folder))
    return added


def taken(trace, writer, name, options):
    try:
        return len(collect(trace, writer, name, **options))
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError, KeyError, TypeError) as e:
        return f"skipped: {e}"


def fetch(trace, writer, folder):
    """Collect from the network, at most once in a while and never where someone is waiting for a session to start."""
    mark = os.path.join(tempfile.gettempdir(), "dendro-" + hashlib.sha256(os.path.normcase(trace.root).encode("utf-8")).hexdigest()[:16])
    if os.path.exists(mark) and time.time() - os.path.getmtime(mark) < PACE:
        return {}
    with open(mark, "w", encoding="utf-8"):
        pass
    return {"github": taken(trace, writer, "github", {"folder": folder})}


def day_of(event):
    return schema.moment(event["ts"]).astimezone().date().isoformat()


def due(events):
    """What is waiting for a reader: the last days of work with no digest, oldest first, and whether a profile is needed."""
    today = now().date().isoformat()
    worked = {day_of(e) for e in events if e["type"] in WORK}
    read = {e["body"]["data"]["day"] for e in events if e["type"] == "digest"}
    profiles = [day_of(e) for e in events if e["type"] == "profile"]
    newer = sum(1 for d in worked if profiles and d > max(profiles))
    return {"days": sorted(d for d in worked - read if d < today)[-RECENT:][:UNREAD], "profile": bool(worked) and (not profiles or newer >= STALE)}


def line(event):
    """One event as an agent needs it to read and to point back at it."""
    body, data = event["body"], event["body"].get("data") or {}
    text, at = body.get("text") or "", schema.moment(event["ts"]).astimezone()
    out = {"id": event["id"], "at": at.strftime("%Y-%m-%d %H:%M"), "type": event["type"], "who": event["actor"]["name"], "text": text[:CLIP]}
    if len(text) > CLIP:
        out["cut"] = len(text) - CLIP
    if data.get("pasted"):
        out["pasted"] = True
    if event["type"] == "commit":
        out.update(paths=data.get("paths", [])[:6], changed=f"+{data.get('insertions', 0)} -{data.get('deletions', 0)}")
    return out


def day(trace, when, start=0):
    """The records of one day from `start`, what people said and decided before the files that changed. What does not fit in one
    reply is reached with `next`."""
    events = trace.events()
    rows = [e for e in events if e["type"] in schema.TRACE and e["type"] not in ("digest", "profile", "output", "reference") and day_of(e) == when]
    shown, used = [], 0
    ordered = sorted(rows, key=lambda e: {"reply": 1, "change": 2}.get(e["type"], 0))
    for event in ordered[start:start + DAY_ROWS]:
        row = line(event)
        used += len(row["text"]) + 80
        if used > DAY_TEXT:
            break
        shown.append(row)
    out = {"day": when, "records": len(rows), "events": shown, "open_problems": [{k: p[k] for k in ("id", "text")} for p in issues(events) if p["status"] == "open"][:20]}
    return dict(out, next=start + len(shown)) if start + len(shown) < len(rows) else out


def issues(events):
    """Every problem raised and what became of it, folded from the events."""
    out = {e["id"]: {"id": e["id"], "day": day_of(e), "who": e["actor"]["name"], "text": e["body"]["text"], "status": "open"} for e in events if e["type"] == "problem"}
    for event in events:
        if event["type"] == "resolved":
            for ref in event.get("refs", []):
                if ref["rel"] == "responds_to" and ref["to"] in out:
                    out[ref["to"]].update(status=event["body"]["data"]["outcome"], how=event["body"]["text"], ended=day_of(event), by=event["id"])
    return list(out.values())


def outputs(events):
    """What was written from the trace, and how many records came after each, so that a stale one can be told."""
    out, newer = [], 0
    replaced = {r["to"] for e in events if e["type"] == "output" for r in e.get("refs", []) if r["rel"] == "supersedes"}
    for event in reversed(events):
        newer += event["type"] in WORK
        if event["type"] == "output" and event["id"] not in replaced:
            data = event["body"]["data"]
            out.insert(0, {"id": event["id"], "kind": data["kind"], "title": event["body"]["text"], "day": day_of(event), "newer_records": newer})
    return out


def fit(rows, budget):
    """The newest rows that fit, in order, and how many did not."""
    kept, used = [], 0
    for row in reversed(rows):
        used += len(str(row.get("text"))) + len(str(row.get("how", ""))) + 60
        if used > budget:
            break
        kept.append(row)
    return kept[::-1], len(rows) - len(kept)


def guide(kind):
    with open(os.path.join(GUIDES, "common.md"), encoding="utf-8") as common, open(os.path.join(GUIDES, kind + ".md"), encoding="utf-8") as own:
        return own.read() + "\n" + common.read()


def material(trace, kind, audience=None, purpose=None, since=None, until=None):
    """What a report, a deck or a talk is written from: the readings and results of a span, each with its id."""
    events = trace.events()
    inside = lambda day: (not since or day >= since) and (not until or day <= until)
    of = lambda *types: [line(e) for e in events if e["type"] in types and inside(day_of(e))]
    read = {e["body"]["data"]["day"]: e for e in events if e["type"] == "digest" and inside(e["body"]["data"]["day"])}
    digests = [{"id": read[d]["id"], "day": d, "text": read[d]["body"]["text"]} for d in sorted(read)]
    worked = sorted({day_of(e) for e in events if e["type"] in WORK and inside(day_of(e))})
    profiles = [e for e in events if e["type"] == "profile"]
    problems = [p for p in issues(events) if p["status"] == "open" or inside(p["day"])]
    unread = [d for d in worked if d not in read][-14:]
    state = trace.state().to_dict()
    papers = Counter(e["body"]["data"]["kind"] for e in events if e["type"] == "reference")
    named = [{"id": e["id"], "kind": e["body"]["data"]["kind"], "name": e["body"]["text"]} for e in events if e["type"] == "reference" and e["body"]["data"]["kind"] != "dependency"]
    out = {"guide": guide(kind), "kind": kind, "project": trace.project, "audience": audience, "purpose": purpose, "since": since or (worked[0] if worked else None),
           "until": until or (worked[-1] if worked else None), "active_days": len(worked), "profile": profiles[-1]["body"] if profiles else None,
           "unread_days": unread,
           "commits": sum(1 for e in events if e["type"] == "commit" and inside(day_of(e))),
           "argument": [{k: n.get(k) for k in ("id", "title", "status") if n.get(k)} for n in state["nodes"] if n["id"].split(":")[0] in ("claim", "method", "experiment")][:40],
           "releases": of("release")[-12:], "tickets": of("ticket", "check")[-20:], "references": {"counts": dict(papers), "named": named[:40]},
           "earlier": [o for o in outputs(events) if o["kind"] == kind][-5:]}
    left = {}
    for name, rows in (("digests", digests), ("decisions", of("decision", "direction", "correction")), ("problems", problems), ("results", of("result", "run.end")),
                       ("unread_commits", [line(e) for e in events if e["type"] == "commit" and day_of(e) in unread])):
        out[name], gone = fit(rows, MATERIAL[name])
        if gone:
            left[name] = gone
    return dict(out, left_out=left) if left else out


def overview(trace, folder):
    """What the records say about a project, counted and not read."""
    events = trace.events()
    work = [e for e in events if e["type"] in WORK]
    days = sorted({day_of(e) for e in work})
    month = (now().date() - timedelta(days=30)).isoformat()
    paths = [p for e in work if e["type"] == "commit" for p in e["body"]["data"].get("paths", [])] + [e["body"]["text"] for e in work if e["type"] == "change"]
    authors = Counter(str(e["body"]["data"].get("author") if e["type"] == "commit" else e["actor"]["name"]).lower() for e in work if e["actor"]["kind"] != "system" or e["type"] == "commit")
    profiles = [e for e in events if e["type"] == "profile"]
    out = {"project": trace.project, "first": days[0] if days else None, "last": days[-1] if days else None, "active_days": len(days),
           "active_days_last_30": sum(d >= month for d in days), "records": dict(Counter(e["type"] for e in events if e["type"] in schema.TRACE)),
           "people": dict(authors.most_common(8)), "busiest_areas": dict(Counter(p.split("/")[0] for p in paths).most_common(8)),
           "earliest": [line(e) for e in work[:8]], "latest": [line(e) for e in work[-12:]], "waiting": due(events),
           "profile": profiles[-1]["body"] if profiles else None,
           "open_problems": [p for p in issues(events) if p["status"] == "open"][:12], "outputs": outputs(events)[-8:],
           "references": dict(Counter(e["body"]["data"]["kind"] for e in events if e["type"] == "reference"))}
    if folder:
        names = files.listed(folder)
        out["folder"] = folder
        out["file_types"] = dict(Counter(os.path.splitext(p)[1].lower() or "(none)" for p in names).most_common(10))
        out["files"] = len(names)
        out["telling_files"] = [s for s in SIGNS if os.path.exists(os.path.join(folder, s))] + [p for p in names if p.endswith(".md") and p.count("/") == 1 and p.startswith(("doc", "paper"))][:8]
    return out


def evidence(trace, folder, facts):
    """A profile's facts with each file they rest on kept in the trace as it is now, so the proof outlives the file."""
    wrong, kept = [], []
    for fact in facts:
        fact = dict(fact)
        cited, fact["files"] = fact.get("files") or [], []
        for path in cited:
            full = os.path.normpath(os.path.join(folder or "", path))
            if not folder or os.path.commonpath([os.path.abspath(folder), os.path.abspath(full)]) != os.path.abspath(folder) or not os.path.isfile(full):
                wrong.append(f"{fact.get('field')}: no such file in the project: {path}")
            else:
                fact["files"].append({"path": path, "blob": trace.keep(full)["blob"]})
        if not fact["files"]:
            del fact["files"]
        kept.append(fact)
    if wrong:
        raise ValueError(wrong)
    return kept
