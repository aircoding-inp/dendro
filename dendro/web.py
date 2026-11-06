"""The read-only site: its page and the data it shows. Nothing here can change a trace.

    serve   answers on localhost with the page and, on each request, the traces as they are now
    export  writes the same page and data to a folder, to be opened or put on a static host

A trace holds what people said, where things ran and the logs they left. `public` leaves those out of what is shown, without
touching the trace: no said events, no sources, no local paths, no machines, and of the kept files only images.

The page gets every event and, for each day that has any, the graph as it stood when that day ended. Days are the local days of
the machine that builds the data.
"""
import json
import mimetypes
import os
import re
import shutil
import urllib.parse
from datetime import datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dendro import schema
from dendro.state import fold
from dendro.store import Trace, now

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
FILES = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"), "/app.css": ("app.css", "text/css"),
         "/rings.js": ("rings.js", "text/javascript"), "/views.js": ("views.js", "text/javascript"),
         "/plant.js": ("plant.js", "text/javascript"), "/app.js": ("app.js", "text/javascript")}
GUARDS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}
PRIVATE_FIELDS = {"host", "gpu_uuid"}
UNDATED = ("reference", "digest", "profile", "output")  # these say something about days, and make none
PRIVATE_TYPES = ("said", "reply", "change", "digest", "profile", "problem", "resolved", "output", "reference", "ticket", "check")
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf")
LOCAL_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]|(?<![\w.])/(?:home|Users|root|mnt|scratch|data)/)[^\s\"'`,;)\]]*")


def scrubbed(value):
    """This value with what must not leave the machine taken out. None means nothing is left of it."""
    if isinstance(value, dict):
        if "blob" in value and not str(value["blob"]).lower().endswith(PICTURES):
            return None
        kept = {k: scrubbed(v) for k, v in value.items() if k not in PRIVATE_FIELDS}
        return {k: v for k, v in kept.items() if v is not None}
    if isinstance(value, list):
        return [v for v in map(scrubbed, value) if v is not None]
    if isinstance(value, str):
        if LOCAL_PATH.fullmatch(value):
            return None
        return LOCAL_PATH.sub("…", value)
    return value


def public(shown):
    """A project as the page gets it, cut down to what can be published."""
    machine = lambda text: str(text).startswith("resource:")
    rows = [row for row in shown["events"] if row["type"] not in PRIVATE_TYPES and not machine(row["body"].get("id")) and not machine(row["body"].get("dst")) and not machine(row["body"].get("src"))]
    ids, days = {row["id"] for row in rows}, sorted({row["day"] for row in rows})
    events = []
    for row in rows:
        row = {k: v for k, v in row.items() if k not in ("source", "prev")}
        row["refs"] = [ref for ref in row.get("refs", []) if ref["to"] in ids]
        row["body"] = scrubbed(row["body"])
        row["about"] = [id for id in row.get("about", []) if not machine(id)]
        events.append(row)
    states = {}
    for day in days:
        state = scrubbed(shown["states"][day])
        states[day] = dict(state, nodes=[n for n in state["nodes"] if not machine(n["id"])], edges=[e for e in state["edges"] if not machine(e["src"]) and not machine(e["dst"])])
    return {"project": shown["project"], "days": days, "events": events, "states": states}


def pictures(value):
    """The kept files a value points at."""
    if isinstance(value, dict):
        return ({value["blob"]} if "blob" in value else set()).union(*map(pictures, value.values()))
    if isinstance(value, list):
        return set().union(*map(pictures, value))
    return set()


def project(trace, zone=None):
    events, rows = trace.events(), []
    for event in events:
        local = schema.moment(event["ts"]).astimezone(zone)
        rows.append(dict(event, day=local.date().isoformat(), time=local.strftime("%H:%M")))
    days = sorted({row["day"] for row in rows if row["type"] not in UNDATED})
    zone = zone or now().tzinfo
    ends = {day: datetime.combine(datetime.fromisoformat(day), time.max, zone) for day in days}
    return {"project": trace.project, "days": days, "events": rows,
            "states": {day: fold(events, ends[day])[0].to_dict() for day in days}}


def bundle(roots, zone=None, private=True):
    """Everything the page shows, for these traces."""
    shown = [project(Trace(root), zone) for root in roots]
    return {"generated": now().isoformat(), "projects": shown if private else [public(p) for p in shown]}


def export(roots, out, private=True):
    """Build the site beside `out`, then put it in place, so that nothing from an earlier export survives and a failure leaves that
    export as it was. A folder that is not an export is refused rather than replaced."""
    out = os.path.abspath(out)
    if os.path.isdir(out) and os.listdir(out) and not os.path.exists(os.path.join(out, "data.json")):
        raise ValueError(f"{out} has files in it and is not an export")
    work = out + ".building"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    try:
        for name in sorted({name for name, _ in FILES.values()}):
            shutil.copyfile(os.path.join(SITE, name), os.path.join(work, name))
        data = bundle(roots, private=private)
        with open(os.path.join(work, "data.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False)
        if not private:
            with open(os.path.join(work, "robots.txt"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write("User-agent: *\nDisallow: /\n")
        for root, shown in zip(roots, data["projects"]):
            trace = Trace(root)
            wanted = trace.blobs() if private else pictures(shown) & set(trace.blobs())
            for name in wanted:
                os.makedirs(os.path.join(work, "blob", trace.project), exist_ok=True)
                shutil.copyfile(os.path.join(trace.root, "blobs", name), os.path.join(work, "blob", trace.project, name))
        shutil.rmtree(out, ignore_errors=True)
        os.replace(work, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in FILES:
            name, kind = FILES[path]
            with open(os.path.join(SITE, name), "rb") as fh:
                return self.answer(200, kind + "; charset=utf-8", fh.read())
        if path == "/data.json":
            try:
                body = json.dumps(bundle(self.server.roots, private=self.server.private), ensure_ascii=False).encode("utf-8")
            except (OSError, ValueError) as e:
                return self.answer(500, "text/plain; charset=utf-8", str(e).encode("utf-8"))
            return self.answer(200, "application/json; charset=utf-8", body)
        found = self.blob(path)
        if found:
            with open(found, "rb") as fh:
                return self.answer(200, mimetypes.guess_type(found)[0] or "text/plain; charset=utf-8", fh.read(), {"Content-Security-Policy": "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"})
        self.answer(404, "text/plain; charset=utf-8", b"not found")

    def do_HEAD(self):
        self.do_GET()

    def blob(self, path):
        """The file behind /blob/<project>/<name>, or None."""
        parts = [urllib.parse.unquote(p) for p in path.split("/")[1:]]
        if len(parts) != 3 or parts[0] != "blob" or not schema.BLOB.match(parts[2]):
            return None
        if not self.server.private and not parts[2].endswith(PICTURES):
            return None
        for root in self.server.roots:
            trace = Trace(root)
            if trace.project == parts[1] and parts[2] in trace.blobs():
                return os.path.join(trace.root, "blobs", parts[2])
        return None

    def answer(self, status, kind, body, extra=None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in {**GUARDS, **(extra or {})}.items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except ConnectionError:
            self.close_connection = True

    def log_message(self, *_):
        pass


def server(roots, port=8377, private=True):
    for root in roots:
        Trace(root)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.roots, httpd.private = list(roots), private
    return httpd
