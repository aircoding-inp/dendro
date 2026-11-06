"""Files that changed, as `change` events at the time each was last written. Names, sizes and times only, never what is in them.

In a git repository this is the work not committed yet, since commits already say the rest. In any other folder it is every file,
so a second run adds what changed since the first. What happened to a file between two runs leaves no record, and neither does a
file removed before the first.
"""
import os
import subprocess
import time
from datetime import datetime

SKIP = {"node_modules", "__pycache__", "venv", "env", "dist", "build", "target", "out", "trace", "traces"}
SECRET = (".pem", ".key", ".p12", ".pfx")
NEWEST = 500  # a run takes at most this many files
SEEN = 50000  # and stops looking after this many


def private(path):
    return any(part.startswith(".") for part in path.split("/")) or path.lower().endswith(SECRET)


def tracked(folder):
    """The paths git knows in this folder, or None if it is no repository."""
    done = subprocess.run(["git", "-C", folder, "ls-files", "-z"], capture_output=True)
    return [p for p in done.stdout.decode("utf-8", "replace").split("\0") if p] if done.returncode == 0 else None


def walked(folder):
    """Every path under this folder that is work, not machinery."""
    seen = 0
    for top, folders, names in os.walk(folder):
        folders[:] = [f for f in folders if f not in SKIP and not f.startswith(".")]
        for name in names:
            seen += 1
            if seen > SEEN:
                return
            yield os.path.relpath(os.path.join(top, name), folder).replace(os.sep, "/")


def listed(folder):
    """The project's files, as paths relative to it."""
    return [p for p in (tracked(folder) if tracked(folder) is not None else walked(folder)) if not private(p)]


def uncommitted(folder):
    """The paths changed since the last commit, or None if this is no repository."""
    done = subprocess.run(["git", "-C", folder, "status", "--porcelain", "-z", "--untracked-files=all"], capture_output=True)
    if done.returncode:
        return None
    entries, out = done.stdout.decode("utf-8", "replace").split("\0"), []
    while entries:
        entry = entries.pop(0)
        if entry:
            out.append(entry[3:])
            if "R" in entry[:2] or "C" in entry[:2]:
                entries.pop(0)  # a rename also names where it came from
    return out


def items(folder):
    paths, rows = uncommitted(folder), []
    for path in walked(folder) if paths is None else paths:
        try:
            info = os.stat(os.path.join(folder, path))
        except OSError:
            continue
        if not private(path) and os.path.isfile(os.path.join(folder, path)):
            rows.append((info.st_mtime, path, info))
    rows = sorted(rows, key=lambda row: row[0])[-NEWEST:]
    latest = time.time() - 2  # a clock can run ahead of a file system, and nothing is recorded before it happens
    for written, path, info in rows:
        when = datetime.fromtimestamp(min(written, latest)).astimezone().replace(microsecond=0)
        yield {"type": "change", "body": {"text": path, "data": {"bytes": info.st_size}}, "actor": {"kind": "system", "name": "files"},
               "ts": when.isoformat(), "source": {"kind": "change", "id": f"{path}:{info.st_mtime_ns}"}}
