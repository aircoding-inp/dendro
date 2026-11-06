"""The data the site shows, the exported folder and the local server."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import timedelta, timezone

from dendro import Trace, web

ME = "claude-test"
ZONE = timezone(timedelta(hours=10, minutes=30))


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.root = os.path.join(self.dir, "trace")
        trace = Trace.create(self.root, "demo")
        trace.append(ME, "node.put", {"id": "experiment:a", "title": "A", "status": "approved"}, ts="2026-11-04T23:50:00+10:30")
        trace.append(ME, "said", {"text": "开始"}, {"kind": "human", "name": "sims"}, ts="2026-11-05T14:10:00+00:00")
        trace.append(ME, "node.put", {"id": "experiment:a", "status": "running"}, ts="2026-11-06T09:00:00+10:30")


class Data(Base):
    def test_days_are_local_and_each_has_the_graph_at_its_end(self):
        (p,) = web.bundle([self.root], ZONE)["projects"]
        self.assertEqual((p["project"], p["days"]), ("demo", ["2026-11-04", "2026-11-06"]))
        self.assertEqual([(e["day"], e["time"]) for e in p["events"]],
                         [("2026-11-04", "23:50"), ("2026-11-06", "00:40"), ("2026-11-06", "09:00")])
        self.assertEqual([p["states"][d]["nodes"][0]["status"] for d in p["days"]], ["approved", "running"])

    def test_several_traces_are_several_projects(self):
        Trace.create(os.path.join(self.dir, "other"), "other")
        data = web.bundle([self.root, os.path.join(self.dir, "other")], ZONE)
        self.assertEqual([(p["project"], p["days"]) for p in data["projects"]], [("demo", ["2026-11-04", "2026-11-06"]), ("other", [])])


class Public(Base):
    def setUp(self):
        super().setUp()
        trace = Trace(self.root)
        said = trace.append("w", "said", {"text": "my teacher thinks this is weak"}, {"kind": "human", "name": "sims"}, source={"kind": "claude-session", "id": "a", "session": "s"})
        trace.append("w", "decision", {"text": "logs live in /home/sims/out/job.log now"}, {"kind": "agent", "name": "w"}, refs=[{"rel": "based_on", "to": said["id"]}])
        log, picture = os.path.join(self.dir, "run.log"), os.path.join(self.dir, "fig.png")
        for path in (log, picture):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(path)
        self.log, self.picture = trace.keep(log), trace.keep(picture)
        trace.append("w", "node.put", {"id": "resource:gpu", "title": "GPU", "data": {"host": "box", "gpu_uuid": "GPU-1", "role": "main"}}, {"kind": "agent", "name": "w"})
        trace.append("w", "node.put", {"id": "run:a", "title": "a", "data": {"job_dir": "/home/sims/out/a", "log_file": self.log, "figure": self.picture, "seeds": 3}}, {"kind": "agent", "name": "w"})

    def published(self):
        out = web.export([self.root], os.path.join(self.dir, "public"), private=False)
        with open(os.path.join(out, "data.json"), encoding="utf-8") as fh:
            return out, fh.read()

    def test_it_leaves_out_what_people_said_and_where_things_ran(self):
        _, text = self.published()
        for secret in ("my teacher", "/home/sims", "claude-session", "gpu_uuid", '"host"', "log_file", "resource:gpu"):
            self.assertNotIn(secret, text)

    def test_it_keeps_the_record_readable(self):
        _, text = self.published()
        project = json.loads(text)["projects"][0]
        ids = {e["id"] for e in project["events"]}
        decision = next(e for e in project["events"] if e["type"] == "decision")
        self.assertEqual(decision["body"]["text"], "logs live in … now")
        self.assertTrue(all(r["to"] in ids for e in project["events"] for r in e.get("refs", [])))
        run = next(n for day in project["states"].values() for n in day["nodes"] if n["id"] == "run:a")
        self.assertEqual(run["data"]["seeds"], 3)

    def test_it_carries_images_and_no_other_kept_file(self):
        out, _ = self.published()
        self.assertEqual(os.listdir(os.path.join(out, "blob", "demo")), [self.picture["blob"]])

    def test_it_asks_not_to_be_indexed(self):
        out, _ = self.published()
        self.assertTrue(os.path.exists(os.path.join(out, "robots.txt")))

    def test_a_public_export_replaces_a_full_one_completely(self):
        out = web.export([self.root], os.path.join(self.dir, "public"))
        self.assertTrue(os.path.exists(os.path.join(out, "blob", "demo", self.log["blob"])))
        self.published()
        self.assertFalse(os.path.exists(os.path.join(out, "blob", "demo", self.log["blob"])))


class Site(Base):
    def test_an_export_will_not_replace_a_folder_that_is_not_one(self):
        folder = os.path.join(self.dir, "thesis")
        os.makedirs(folder)
        with open(os.path.join(folder, "draft.tex"), "w", encoding="utf-8") as fh:
            fh.write("x")
        with self.assertRaises(ValueError):
            web.export([self.root], folder)
        self.assertEqual(os.listdir(folder), ["draft.tex"])

    def test_an_export_is_the_page_and_its_data(self):
        out = web.export([self.root], os.path.join(self.dir, "site"))
        self.assertEqual(sorted(os.listdir(out)), ["app.css", "app.js", "data.json", "index.html", "plant.js", "rings.js", "views.js"])
        with open(os.path.join(out, "data.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["projects"][0]["project"], "demo")

    def kept(self):
        path = os.path.join(self.dir, "run.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("step 1\n")
        return Trace(self.root).keep(path)

    def test_an_export_carries_what_the_trace_keeps(self):
        kept = self.kept()
        out = web.export([self.root], os.path.join(self.dir, "site"))
        self.assertEqual(os.listdir(os.path.join(out, "blob", "demo")), [kept["blob"]])

    def test_the_server_gives_a_kept_file_and_nothing_beside_it(self):
        kept = self.kept()
        httpd = web.server([self.root], 0)
        self.addCleanup(httpd.server_close)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with urllib.request.urlopen(f"{base}/blob/demo/{kept['blob']}") as answer:
            self.assertEqual(answer.read().replace(b"\r\n", b"\n"), b"step 1\n")
        for path in ("/blob/demo/dendro.json", "/blob/demo/..%2Fdendro.json", "/blob/other/" + kept["blob"]):
            with self.assertRaises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(base + path)
            self.assertEqual(missing.exception.code, 404)
            missing.exception.close()

    def test_the_server_reads_and_never_writes(self):
        httpd = web.server([self.root], 0)
        self.addCleanup(httpd.server_close)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with urllib.request.urlopen(base + "/") as answer:
            self.assertIn("<title>Dendro</title>", answer.read().decode("utf-8"))
        for name, kind in (("/app.css", "text/css"), ("/app.js", "text/javascript")):
            with urllib.request.urlopen(base + name) as answer:
                self.assertTrue(answer.headers["Content-Type"].startswith(kind) and answer.read())
        with urllib.request.urlopen(base + "/data.json") as answer:
            self.assertEqual(len(json.load(answer)["projects"][0]["events"]), 3)
        Trace(self.root).append(ME, "note", {"text": "written meanwhile"})
        with urllib.request.urlopen(base + "/data.json") as answer:
            self.assertEqual(len(json.load(answer)["projects"][0]["events"]), 4)
        request = urllib.request.Request(base + "/data.json", data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request)
        self.assertEqual(refused.exception.code, 501)
        refused.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(base + "/events/claude-test.jsonl")
        self.assertEqual(missing.exception.code, 404)
        missing.exception.close()

    def test_a_folder_that_is_no_trace_is_refused(self):
        with self.assertRaises(FileNotFoundError):
            web.server([os.path.join(self.dir, "nothing")], 0)


if __name__ == "__main__":
    unittest.main()
