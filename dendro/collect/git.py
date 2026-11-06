"""A repository's commits, each as a `commit` event at the time it was authored, and its tags, each as a `release`."""
import os
import subprocess

RECORD, UNIT = "\x1e", "\x1f"
FORMAT = f"{RECORD}%H{UNIT}%aI{UNIT}%an{UNIT}%s"
PATHS = 12  # a commit names at most this many of the files it touched


def items(repo):
    out = subprocess.run(["git", "-C", repo, "log", "--reverse", "--numstat", f"--pretty=format:{FORMAT}"], capture_output=True,
                         encoding="utf-8", errors="replace", check=True).stdout
    name = os.path.basename(os.path.abspath(repo))
    for record in out.split(RECORD)[1:]:
        head, *stats = record.strip("\n").split("\n")
        commit, when, author, subject = head.split(UNIT)
        files = [line.split("\t") for line in stats if line.count("\t") == 2]
        count = lambda column: sum(int(f[column]) for f in files if f[column].isdigit())
        data = {"hash": commit, "author": author, "files": len(files), "insertions": count(0), "deletions": count(1),
                "paths": [f[2] for f in files[:PATHS]]}
        yield {"type": "commit", "body": {"text": subject or "(no subject)", "data": data}, "actor": {"kind": "system", "name": "git"},
               "ts": when, "source": {"kind": "git", "id": commit, "repo": name}}


def remote(repo):
    """Where this repository is published, or nothing."""
    return subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"], capture_output=True, encoding="utf-8", errors="replace").stdout.strip()


def tags(repo):
    out = subprocess.run(["git", "-C", repo, "for-each-ref", "refs/tags", f"--format=%(refname:short){UNIT}%(creatordate:iso-strict){UNIT}%(subject)"],
                         capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    for row in out.splitlines():
        tag, when, subject = row.split(UNIT, 2)
        yield {"type": "release", "body": {"text": tag, "data": {"note": subject} if subject else {}}, "actor": {"kind": "system", "name": "git"},
               "ts": when, "source": {"kind": "release", "id": tag, "repo": os.path.basename(os.path.abspath(repo))}}
