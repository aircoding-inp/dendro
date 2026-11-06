"""A repository's issues, pull requests and failed checks on GitHub, through the `gh` its owner is already signed in to. An issue is
a `ticket` when it opens and another when it closes, each at the time it happened; a failed workflow run is a `check`.
"""
import json
import subprocess

from dendro.collect import git

WAIT = 15  # seconds a request may take: nobody is waiting for this, and the next run tries again
LIMIT = 200
ACTOR = {"kind": "system", "name": "github"}


def asked(folder, *args):
    done = subprocess.run(["gh", *args], cwd=folder, capture_output=True, encoding="utf-8", errors="replace", timeout=WAIT, check=True)
    return json.loads(done.stdout or "[]")


def moment(text):
    return text.replace("Z", "+00:00")


def ticket(kind, row, state, when):
    author = (row.get("author") or {}).get("login")
    data = {"kind": kind, "number": row["number"], "state": state, "url": row["url"], **({"author": author} if author else {})}
    return {"type": "ticket", "body": {"text": row["title"], "data": data}, "actor": ACTOR, "ts": moment(when),
            "source": {"kind": "github", "id": f"{kind}:{row['number']}:{state}"}}


def items(folder):
    if "github.com" not in git.remote(folder):
        return
    fields = "number,title,author,url,createdAt,closedAt"
    for row in asked(folder, "issue", "list", "--state", "all", "--limit", str(LIMIT), "--json", fields):
        yield ticket("issue", row, "opened", row["createdAt"])
        if row.get("closedAt"):
            yield ticket("issue", row, "closed", row["closedAt"])
    for row in asked(folder, "pr", "list", "--state", "all", "--limit", str(LIMIT), "--json", fields + ",mergedAt"):
        yield ticket("pull", row, "opened", row["createdAt"])
        if row.get("mergedAt"):
            yield ticket("pull", row, "merged", row["mergedAt"])
        elif row.get("closedAt"):
            yield ticket("pull", row, "closed", row["closedAt"])
    for row in asked(folder, "run", "list", "--status", "failure", "--limit", "30", "--json", "databaseId,displayTitle,workflowName,headBranch,createdAt,url"):
        data = {"workflow": row["workflowName"], "branch": row["headBranch"], "url": row["url"]}
        yield {"type": "check", "body": {"text": row["displayTitle"], "data": data}, "actor": ACTOR, "ts": moment(row["createdAt"]),
               "source": {"kind": "github", "id": f"run:{row['databaseId']}"}}
