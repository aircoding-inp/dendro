"""What a person typed in Codex sessions, word for word, as `said` events, and what the agent concluded each turn, as `reply`.

Codex keeps each session as a JSONL rollout. Its first row says where the session ran and who started it; only sessions a person
sat at are read, since `codex exec`, Codex running as a server and its subagents get their prompts from programs, and a `said` says
a person said it. A person's message is a completed UserMessage item, without the context Codex adds around it; a turn's conclusion
is the last message its task_complete names. That row comes after the end-of-turn hook has run, so the hook passes on what it was
told, under the same turn id.

OpenAI does not promise this format, so what cannot be understood is passed over and the session it came from goes on undisturbed.
"""
import json
import re

from dendro import schema
from dendro.collect.claude_session import REPLY, inside, transcripts
from dendro.store import now

NOT_TYPED = ("exec", "mcp")
ATTACHED = re.compile(r"^\s*# Files (mentioned|pasted) by the user:")
REQUEST = re.compile(r"^## My request[^\n]*:\n", re.M)


def opening(path):
    """The first row of a rollout, which says what session it is, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            row = json.loads(fh.readline())
    except (OSError, ValueError):
        return None
    meta = row.get("payload") if isinstance(row, dict) and row.get("type") == "session_meta" else None
    return meta if isinstance(meta, dict) else None


def started_in(path, folder):
    meta = opening(path)
    return bool(meta and meta.get("cwd") and inside(meta, folder))


def typed(item):
    """The text and whether it came with pasted files, from a completed item, or None if a person did not write it."""
    if not isinstance(item, dict) or item.get("type") != "UserMessage" or not isinstance(item.get("content"), list):
        return None
    text = "\n".join(p.get("text", "") for p in item["content"] if isinstance(p, dict) and p.get("type") == "text")
    attached = ATTACHED.match(text)
    text = REQUEST.split(text)[-1].strip() if attached else text.strip()
    return (text, bool(attached) and attached[1] == "pasted") if text else None


def items(paths, by, since=None, until=None, agent=None, folder=None, ending=None):
    """One `said` item per message typed in these rollouts or folders of them, oldest first. by is the person, as an actor; with an
    agent, also one `reply` for each turn it finished; with a folder, only what happened in it. ending is what a Stop hook was told
    about the turn ending in these rollouts."""
    since, until, found = schema.moment(since) if since else None, schema.moment(until) if until else None, {}

    def keep(entry, key, type_, body, actor, session):
        when = schema.moment(str(entry.get("timestamp", "")).replace("Z", "+00:00"))
        if key and when and key not in found and not (since and when < since) and not (until and when > until):
            found[key] = (when, {"type": type_, "body": body, "actor": actor, "ts": when.isoformat(),
                                 "source": {"kind": "codex-session", "id": key, "session": session}})

    def concluded(entry, turn, text, session):
        if agent and isinstance(text, str) and text.strip():
            cut = {"data": {"cut": len(text) - REPLY}} if len(text) > REPLY else {}
            keep(entry, turn, "reply", {"text": text[:REPLY], **cut}, agent, session)

    for path in transcripts(paths):
        meta = opening(path)
        if not meta or isinstance(meta.get("source"), dict) or meta.get("source") in NOT_TYPED:
            continue
        session, here = meta.get("id"), meta.get("cwd")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                payload = entry.get("payload") if isinstance(entry, dict) else None
                if not isinstance(payload, dict):
                    continue
                if entry.get("type") == "turn_context":
                    here = payload.get("cwd") or here
                if entry.get("type") != "event_msg" or not inside({"cwd": here}, folder):
                    continue
                if payload.get("type") == "item_completed" and (said := typed(payload.get("item"))):
                    text, pasted = said
                    keep(entry, payload["item"].get("id"), "said", {"text": text, **({"data": {"pasted": True}} if pasted else {})}, by, session)
                elif payload.get("type") == "task_complete":
                    concluded(entry, payload.get("turn_id"), payload.get("last_agent_message"), session)
        if ending and inside({"cwd": here}, folder):
            concluded({"timestamp": now().isoformat()}, ending.get("turn_id"), ending.get("last_assistant_message"), session)
    return [item for _, item in sorted(found.values(), key=lambda pair: pair[0])]
