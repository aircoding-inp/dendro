"""Connect the agent clients on this machine to this checkout of Dendro, so that nobody has to call anything afterwards.

Each client gets the same three parts: the server, a hook that collects at the end of every turn, and the skill. What a person
already has there stays, and connecting again changes nothing. Everything points at the Python running this, which is the one
sure to be there. Codex runs no new hook until a person trusts it, which is theirs to do, so it is left to them and said so.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = [sys.executable, REPO]
SKILL = "dendro-report"


def replaced(path, text):
    """Write a file in one step, so that a client reading it never finds half of it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".dendro", "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(path + ".dendro", path)


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def server(path):
    """Add Dendro to Codex's config.toml. JSON strings and lists are also TOML, so nothing else in the file has to be understood."""
    text = read(path)
    block = "[mcp_servers.dendro]\n" + "".join(f"{k} = {json.dumps(v, ensure_ascii=False)}\n" for k, v in (
        ("command", LAUNCH[0]), ("args", LAUNCH[1:] + ["mcp"]), ("env_vars", ["DENDRO_HOME"]), ("startup_timeout_sec", 60), ("default_tools_approval_mode", "approve")))
    old = re.compile(r"^\[mcp_servers\.dendro\]\r?\n(?:(?!\[|\r?$).*(?:\r?\n|$))*", re.M)
    if old.search(text):
        new = old.sub(lambda _: block, text, 1)
    else:
        new = text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + block
    if new != text:
        replaced(path, new)


def hook(path, line):
    """Add the end-of-turn hook to a client's JSON settings, next to whatever is there. line ends with what marks it as ours."""
    config = json.loads(read(path) or "{}")
    stop = config.setdefault("hooks", {}).setdefault("Stop", [])
    ours = {"type": "command", "command": line, "async": True}
    if any(ours == h for group in stop for h in group.get("hooks", [])):
        return
    mark = line[line.rindex(" hook --from "):]
    for group in stop:
        group["hooks"] = [h for h in group.get("hooks", []) if not str(h.get("command", "")).endswith(mark)]
    stop[:] = [g for g in stop if g["hooks"]] + [{"hooks": [ours]}]
    replaced(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def skill(folder):
    shutil.copytree(os.path.join(REPO, "skills", SKILL), os.path.join(folder, SKILL), dirs_exist_ok=True)
    return os.path.join(folder, SKILL)


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def codex():
    base = codex_home()
    config, hooks = os.path.join(base, "config.toml"), os.path.join(base, "hooks.json")
    server(config)
    hook(hooks, (subprocess.list2cmdline(LAUNCH) if os.name == "nt" else shlex.join(LAUNCH)) + " hook --from codex")
    return {"server": config, "hook": hooks, "skill": skill(os.path.join(os.path.expanduser("~"), ".agents", "skills")),
            "next": "Trust the new hook once: /hooks in Codex, or Settings > Hooks in the app."}


def claude():
    """Claude Code keeps its servers where only its own command should write. Its hooks run in a POSIX shell, on Windows too."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    tool, settings = shutil.which("claude"), os.path.join(base, "settings.json")
    subprocess.run([tool, "mcp", "remove", "--scope", "user", "dendro"], capture_output=True)
    added = subprocess.run([tool, "mcp", "add", "--scope", "user", "dendro", "--", *LAUNCH, "mcp"], capture_output=True, encoding="utf-8", errors="replace")
    if added.returncode:
        raise ValueError([added.stderr.strip() or "claude mcp add failed"])
    hook(settings, " ".join(shlex.quote(p.replace("\\", "/")) for p in LAUNCH) + " hook --from claude")
    return {"server": "user scope", "hook": settings, "skill": skill(os.path.join(base, "skills"))}


def connect(client=None):
    """Connect this client, or every one found on this machine."""
    found = [name for name, there in (("claude", shutil.which("claude")), ("codex", shutil.which("codex") or os.path.isdir(codex_home()))) if there]
    if not client and not found:
        raise ValueError(["Neither Claude Code nor Codex is on this machine"])
    return {name: {"claude": claude, "codex": codex}[name]() for name in ([client] if client else found)}
