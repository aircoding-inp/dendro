"""A trace on disk: append-only event files, one per writer, so that two writers never touch the same file.

    <root>/dendro.json            the project and the schema version
    <root>/events/<writer>.jsonl  that writer's events in the order it recorded them, each naming the one before
    <root>/blobs/<hash>.<ext>     files events point at, such as figures and logs, named by their content

An event is never changed or removed. A correction is a new event. check() says whether the files still are what was written.
"""
import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime

from dendro import schema
from dendro.state import fold

META = "dendro.json"
ITEM = ("type", "body", "actor", "about", "refs", "ts", "source")


def now():
    return datetime.now().astimezone().replace(microsecond=0)


def in_order(rows):
    """Events as things happened; ties go to the order of recording, then to the writer and its own order."""
    return [row[-1] for row in sorted(rows, key=lambda row: row[:4])]


class Trace:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        if not os.path.exists(os.path.join(self.root, META)):
            raise FileNotFoundError(f"no trace at {self.root}")

    @classmethod
    def create(cls, root, project):
        os.makedirs(os.path.join(root, "events"), exist_ok=True)
        path = os.path.join(root, META)
        if os.path.exists(path):
            raise FileExistsError(f"a trace is already at {root}")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"project": project, "schema": schema.VERSION}, fh, ensure_ascii=False, indent=1)
        return cls(root)

    @property
    def project(self):
        with open(os.path.join(self.root, META), encoding="utf-8") as fh:
            return json.load(fh)["project"]

    def path(self, writer):
        return os.path.join(self.root, "events", writer + ".jsonl")

    def writers(self):
        return sorted(f[:-6] for f in os.listdir(os.path.join(self.root, "events")) if f.endswith(".jsonl"))

    def written(self, writer):
        """One writer's events as it recorded them."""
        if not os.path.exists(self.path(writer)):
            return []
        with open(self.path(writer), encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def rows(self):
        return [(schema.moment(e["ts"]), schema.moment(e["rec"]), w, i, e) for w in self.writers() for i, e in enumerate(self.written(w))]

    def events(self):
        return in_order(self.rows())

    def missing(self, items):
        """The items whose record is not in the log yet, each record once. An item with no source key is always kept."""
        have, out = {schema.source_key(e.get("source")) for e in self.events()} - {None}, []
        for item in items:
            key = schema.source_key(item.get("source"))
            if key not in have:
                out.append(item)
                have.add(key)
            have.discard(None)
        return out

    @contextmanager
    def held(self, name, wait=10):
        """One process at a time, across every session of a project. A lock left by a process that died is taken after a minute."""
        path, end = os.path.join(self.root, "events", name + ".lock"), time.monotonic() + wait
        while True:
            try:
                handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except (FileExistsError, PermissionError):
                try:
                    if time.time() - os.path.getmtime(path) > 60:
                        os.unlink(path)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= end:
                    raise ValueError([f"busy: {name}"]) from None
                time.sleep(.05)
        try:
            yield
        finally:
            os.close(handle)
            os.unlink(path)

    def extend(self, writer, items):
        """Record several events as one write and return them. All are written, or none, with every reason."""
        if not schema.WRITER.match(writer or ""):
            raise ValueError(["writer is lower-case letters, digits and hyphens"])
        with self.held(writer):
            return self.written_out(writer, items)

    def written_out(self, writer, items):
        mine, recorded = self.written(writer), now()
        if mine and schema.moment(mine[-1]["rec"]) > recorded:
            raise ValueError(["the clock is behind this writer's last event"])
        new, wrong, prev = [], [], mine[-1]["id"] if mine else None
        where = (lambda i: f"item {i}: ") if len(items) > 1 else (lambda i: "")
        for i, item in enumerate(items):
            extra = sorted(set(item) - set(ITEM))
            event = {"v": schema.VERSION, "ts": item.get("ts") or recorded.isoformat(), "rec": recorded.isoformat(),
                     "type": item.get("type"), "actor": item.get("actor") or {"kind": "agent", "name": writer}, "writer": writer,
                     "body": item.get("body"), "prev": prev}
            event.update({k: item[k] for k in ("about", "refs", "source") if item.get(k)})
            event["id"] = prev = schema.digest(event)
            wrong += [where(i) + reason for reason in ([f"unknown item fields: {extra}"] if extra else []) + schema.problems(event)]
            new.append(event)
        if not wrong:
            rows = self.rows() + [(schema.moment(e["ts"]), recorded, writer, len(mine) + i, e) for i, e in enumerate(new)]
            index = {e["id"]: i for i, e in enumerate(new)}
            found = [x.split(" ", 1) for x in fold(in_order(rows))[1]]
            wrong = [where(index[i]) + reason.split(": ", 1)[1] for i, reason in found if i in index] or [" ".join(x) for x in found]
        if wrong:
            raise ValueError(wrong)
        with open(self.path(writer), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(schema.canonical(event) + "\n" for event in new))
        return new

    def append(self, writer, type_, body, actor=None, *, about=(), refs=(), ts=None, source=None):
        """Record one event and return it. Refused, with every reason, if it is malformed or does not fit the log."""
        item = {"type": type_, "body": body, "actor": actor, "about": list(about), "refs": list(refs), "ts": ts, "source": source}
        return self.extend(writer, [item])[0]

    def state(self, at=None):
        return fold(self.events(), at)[0]

    def keep(self, path):
        """Copy a file into the trace and return what an event says about it. Its name is its content, so it cannot change."""
        with open(path, "rb") as fh:
            content = fh.read()
        extension = os.path.splitext(path)[1].lower()
        digest = hashlib.sha256(content).hexdigest()
        name = digest + extension if schema.BLOB.match(digest + extension) else digest
        os.makedirs(os.path.join(self.root, "blobs"), exist_ok=True)
        target = os.path.join(self.root, "blobs", name)
        if not os.path.exists(target):
            with open(target, "wb") as fh:
                fh.write(content)
        return {"blob": name, "name": os.path.basename(path), "bytes": len(content)}

    def blobs(self):
        folder = os.path.join(self.root, "blobs")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def check(self):
        """Everything wrong with the trace as it stands on disk; empty if it is sound."""
        out = []
        for writer in self.writers():
            prev, last = None, None
            for i, event in enumerate(self.written(writer)):
                where = f"{writer}.jsonl line {i + 1}"
                out += [f"{where}: {reason}" for reason in schema.problems(event)]
                if event.get("writer") != writer:
                    out.append(f"{where}: written by {event.get('writer')!r}")
                if event.get("prev") != prev:
                    out.append(f"{where}: does not follow the event before it")
                recorded = schema.moment(event.get("rec"))
                if last and recorded and recorded < last:
                    out.append(f"{where}: recorded before the event above it")
                prev, last = event.get("id"), recorded or last
        for name in self.blobs():
            with open(os.path.join(self.root, "blobs", name), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != name.split(".")[0]:
                    out.append(f"blobs/{name}: is not what its name says")
        return out or fold(self.events())[1]
