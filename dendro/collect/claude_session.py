"""What a person typed in Claude Code sessions, word for word, as `said` events, and what the agent concluded each turn, as `reply`.

Claude Code keeps each session as a JSONL transcript and marks what the person typed with origin.kind = "human": either a user
entry, or a message queued while a turn was running. Everything else in a transcript (tool results, reminders, summaries, messages
from other sessions) is left out. A forked session repeats its parent's history under the same message ids, so one message read
from several transcripts is one record.

A turn's reply is its last text, where an agent says what it found and did. It is what was said and not proof of it, and the steps
on the way there are left out, as are subagents.
"""
import glob
import json
import os
import re

from dendro import schema

REMINDER = re.compile(r"<system-reminder.*?</system-reminder>", re.S)
REPLY = 6000  # characters of a reply that are kept


def typed(entry):
    """The text a person typed in this transcript entry, or None."""
    if (entry.get("origin") or {}).get("kind") == "human" and entry.get("type") == "user":
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, list):
            content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    else:
        queued = entry.get("attachment") or {}
        human = entry.get("type") == "attachment" and queued.get("type") == "queued_command" and (queued.get("origin") or {}).get("kind") == "human"
        content = queued.get("prompt") if human else None
    if not isinstance(content, str) or entry.get("isMeta") or entry.get("isCompactSummary"):
        return None
    return REMINDER.sub("", content).strip() or None


def written(entry):
    """The text an agent wrote in this transcript entry, or None."""
    message = entry.get("message") or {}
    if entry.get("type") != "assistant" or entry.get("isSidechain") or entry.get("isApiErrorMessage") or message.get("model") == "<synthetic>":
        return None
    content = message.get("content")
    if isinstance(content, list):
        content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return content.strip() or None if isinstance(content, str) else None


def transcripts(paths):
    for path in paths:
        yield from sorted(glob.glob(os.path.join(path, "*.jsonl"))) if os.path.isdir(path) else [path]


def inside(entry, folder):
    """Whether this entry was written while working in this folder. One session can move between projects."""
    here = entry.get("cwd")
    if not folder or not here:
        return True
    top, here = os.path.normcase(os.path.abspath(folder)), os.path.normcase(os.path.abspath(here))
    return here == top or here.startswith(top + os.sep)


def items(paths, by, since=None, until=None, agent=None, folder=None):
    """One `said` item per message typed in these transcripts or folders of them, oldest first. by is the person, as an actor; with
    an agent, also one `reply` for each turn it finished; with a folder, only what happened in it."""
    since, until, found = schema.moment(since) if since else None, schema.moment(until) if until else None, {}

    def keep(entry, type_, body, actor):
        when = schema.moment(str(entry.get("timestamp", "")).replace("Z", "+00:00"))
        if when and entry.get("uuid") not in found and not (since and when < since) and not (until and when > until):
            found[entry["uuid"]] = (when, {"type": type_, "body": body, "actor": actor, "ts": when.isoformat(), "source": {
                "kind": "claude-session", "id": entry["uuid"], "session": entry.get("sessionId")}})

    def finish(last):
        if last and agent:
            entry, text = last
            keep(entry, "reply", {"text": text[:REPLY], **({"data": {"cut": len(text) - REPLY}} if len(text) > REPLY else {})}, agent)

    for path in transcripts(paths):
        last = None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or not inside(entry, folder):
                    continue
                text, answer = typed(entry), written(entry)
                if text:
                    finish(last)
                    last = None
                    keep(entry, "said", {"text": text, "data": {"pasted": True}} if "<pasted_content" in text else {"text": text}, by)
                elif answer:
                    last = (entry, answer)
        finish(last)
    return [item for _, item in sorted(found.values(), key=lambda pair: pair[0])]
