"""Collectors over real records: a repository, a paper's source, and items another program prepared."""
import json
import os
import subprocess
import tempfile
import unittest

from dendro import Trace
from dendro.collect import collect

ME = "claude-test"

MAIN = r"""
\documentclass{article}
\begin{document}
\begin{abstract}
A frozen model meets a request only through inference \todo{result}.
% tags: L[a] M[numbers.json] H[claim]
\end{abstract}
\input{sec/intro}
\section{Method}
\label{sec:method}
The program has six slots.
% tags: M[design.md] M[again]
\subsection{Closed-loop revision}
\label{sec:loop}
The agent revises \cite{liu2026rgdno,ge2026vtos}.
% \section{Not a section}
\bibliography{main}
\end{document}
"""
INTRO = r"""
\section{Introduction}
\label{sec:intro}
Prior work is designed by hand \cite{liu2026rgdno} and \citep[see][]{Missing2020}.
"""
BIB = """
@inproceedings{liu2026rgdno, title = {RG-DNO}, year = {2026}}
@inproceedings{ge2026vtos, title = {VTOS}, year = {2026}}
"""


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.join(tmp.name, "work")
        os.makedirs(os.path.join(self.dir, "sec"))
        self.trace = Trace.create(os.path.join(tmp.name, "trace"), "demo")

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return path


class Paper(Base):
    def setUp(self):
        Base.setUp(self)
        self.write("sec/intro.tex", INTRO)
        self.main = self.write("main.tex", MAIN)
        collect(self.trace, ME, "bibtex", path=self.write("main.bib", BIB))

    def test_sections_hold_their_text_and_say_where_they_are(self):
        collect(self.trace, ME, "latex", path=self.main)
        nodes = {k: v for k, v in self.trace.state().nodes.items() if v["kind"] == "section"}
        self.assertEqual(sorted(nodes), ["section:abstract", "section:intro", "section:loop", "section:method"])
        got = {k: (v["title"], v["data"]["level"], v["data"]["order"], v["data"].get("parent"), v["data"]["file"]) for k, v in nodes.items()}
        self.assertEqual(got, {"section:abstract": ("Abstract", 1, 0, None, "main.tex"),
                               "section:intro": ("Introduction", 1, 1, None, "intro.tex"),
                               "section:method": ("Method", 1, 2, None, "main.tex"),
                               "section:loop": ("Closed-loop revision", 2, 3, "section:method", "main.tex")})
        abstract = nodes["section:abstract"]["data"]
        self.assertEqual((abstract["todos"], abstract["backing"]), (1, {"H": 1, "L": 1, "M": 1}))
        self.assertNotIn("tags:", abstract["text"])
        self.assertEqual(nodes["section:method"]["data"]["backing"], {"M": 2})
        self.assertEqual(nodes["section:loop"]["data"]["text"], r"The agent revises \cite{liu2026rgdno,ge2026vtos}.")

    def test_a_citation_is_an_edge_once_the_work_is_known(self):
        collect(self.trace, ME, "latex", path=self.main)
        edges = sorted((s, d) for (rel, s, d) in self.trace.state().edges if rel == "cites")
        self.assertEqual(edges, [("section:intro", "paper:liu2026rgdno"), ("section:loop", "paper:ge2026vtos"),
                                 ("section:loop", "paper:liu2026rgdno")])
        self.write("main.bib", BIB + "@article{Missing2020, title = {Found}, year = {2020}}\n")
        collect(self.trace, ME, "bibtex", path=os.path.join(self.dir, "main.bib"))
        added = collect(self.trace, ME, "latex", path=self.main)
        self.assertEqual([e["body"] for e in added], [{"rel": "cites", "src": "section:intro", "dst": "paper:missing2020"}])
        self.assertEqual(collect(self.trace, ME, "latex", path=self.main), [])
        self.assertEqual(self.trace.check(), [])

    def test_a_section_that_changes_is_taken_again(self):
        collect(self.trace, ME, "latex", path=self.main)
        self.write("main.tex", MAIN.replace("six slots", "six slots and one hook"))
        added = collect(self.trace, ME, "latex", path=self.main)
        self.assertEqual([e["body"]["id"] for e in added], ["section:method"])
        self.assertIn("one hook", self.trace.state().nodes["section:method"]["data"]["text"])

    def test_a_supplement_keeps_its_own_names(self):
        collect(self.trace, ME, "latex", path=self.main, prefix="supp")
        self.assertIn("section:supp-method", self.trace.state().nodes)

    def test_a_note_is_kept_with_the_place_it_follows(self):
        collect(self.trace, ME, "latex", path=self.main)
        data = self.trace.state().nodes["section:abstract"]["data"]
        (note,) = data["notes"]
        self.assertEqual(note["tags"], [{"k": "L", "t": "a"}, {"k": "M", "t": "numbers.json"}, {"k": "H", "t": "claim"}])
        self.assertEqual(data["text"][:note["at"]].rstrip()[-1], ".")

    def test_a_macro_without_arguments_is_written_out(self):
        self.write("main.tex", MAIN.replace(r"\begin{document}", "\\newcommand{\\ours}{\\textsc{Arbor}\\xspace}\n\\newcommand{\\red}[1]{#1}\n\\begin{document}")
                   .replace("The program has", r"\ours{} has \red{x} and \ours's"))
        collect(self.trace, ME, "latex", path=self.main)
        self.assertIn(r"\textsc{Arbor} has \red{x} and \textsc{Arbor}'s", self.trace.state().nodes["section:method"]["data"]["text"])

    def test_a_figure_is_kept_as_a_twin_the_browser_can_draw(self):
        os.makedirs(os.path.join(self.dir, "fig"))
        self.write("fig/plan.pdf", "pdf")
        self.write("fig/plan.svg", "<svg/>")
        self.write("main.tex", MAIN.replace("The program has six slots.", "\\begin{figure}\\includegraphics[width=1cm]{fig/plan.pdf}\\caption{The plan}\\end{figure}"))
        collect(self.trace, ME, "latex", path=self.main)
        (figure,) = self.trace.state().nodes["section:method"]["data"]["figures"]
        self.assertEqual((figure["name"], figure["caption"]), ("plan.svg", "The plan"))
        self.assertIn(figure["blob"], self.trace.blobs())
        self.assertEqual(self.trace.check(), [])

    def test_an_accent_in_a_name_is_the_letter(self):
        self.write("main.bib", "@article{a, title = {T}, author = {St\\\"olzle, M and Assump{\\c{c}}{\\~a}o, H}}\n")
        collect(self.trace, ME, "bibtex", path=os.path.join(self.dir, "main.bib"))
        self.assertEqual(self.trace.state().nodes["paper:a"]["data"]["authors"], ["Stölzle, M", "Assumpção, H"])


class Attached(Base):
    def test_a_file_is_kept_and_named_by_its_node_once(self):
        self.trace.append(ME, "node.put", {"id": "run:a", "title": "A"})
        path = self.write("run.log", "step 1\n")
        got = collect(self.trace, ME, "file", path=path, node="run:a", field="log_file")
        kept = self.trace.state().nodes["run:a"]["data"]["log_file"]
        self.assertEqual((len(got), kept["name"], kept["bytes"]), (1, "run.log", 7))
        self.assertEqual(collect(self.trace, ME, "file", path=path, node="run:a", field="log_file"), [])

    def test_a_changed_kept_file_is_found_by_check(self):
        self.trace.append(ME, "node.put", {"id": "run:a", "title": "A"})
        collect(self.trace, ME, "file", path=self.write("run.log", "step 1\n"), node="run:a", field="log_file")
        (name,) = self.trace.blobs()
        with open(os.path.join(self.trace.root, "blobs", name), "a", encoding="utf-8") as fh:
            fh.write("edited")
        self.assertTrue(self.trace.check())


class Repository(Base):
    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="Sims", GIT_AUTHOR_EMAIL="s@example.org", GIT_COMMITTER_NAME="Sims",
                   GIT_COMMITTER_EMAIL="s@example.org", GIT_AUTHOR_DATE="2026-11-04T09:00:00+10:30")
        subprocess.run(["git", "-C", self.dir, *args], check=True, capture_output=True, env=env)

    def test_each_commit_is_an_event_at_the_time_it_was_made(self):
        self.git("init", "-q")
        self.write("a.py", "one\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Add the first file")
        self.write("a.py", "one\ntwo\n")
        self.write("b.py", "x\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Grow it")
        got = collect(self.trace, ME, "git", repo=self.dir)
        self.assertEqual([(e["type"], e["body"]["text"], e["ts"]) for e in got],
                         [("commit", "Add the first file", "2026-11-04T09:00:00+10:30"), ("commit", "Grow it", "2026-11-04T09:00:00+10:30")])
        data = got[1]["body"]["data"]
        self.assertEqual((data["author"], data["files"], data["insertions"], sorted(data["paths"])), ("Sims", 2, 2, ["a.py", "b.py"]))
        self.assertEqual(collect(self.trace, ME, "git", repo=self.dir), [])


class Prepared(Base):
    def test_items_from_another_program_are_taken_like_any_other(self):
        self.trace.append(ME, "node.put", {"id": "experiment:seeds", "title": "Seed evaluation", "status": "running"},
                          ts="2026-11-06T15:00:00+10:30")
        rows = [
            {"type": "node.put", "body": {"id": "resource:gpu0", "title": "GPU 0"}, "ts": "2026-11-06T15:40:00+10:30",
             "source": {"kind": "demo-store", "id": "resource:gpu0"}},
            {"type": "node.put", "body": {"id": "run:abc", "title": "barrier seed", "status": "done", "data": {"batch_size": 4}},
             "ts": "2026-11-06T15:40:00+10:30", "source": {"kind": "demo-store", "id": "run:abc:done"}},
            {"type": "edge.put", "body": {"rel": "of", "src": "run:abc", "dst": "experiment:seeds"}, "ts": "2026-11-06T15:40:00+10:30",
             "source": {"kind": "demo-store", "id": "run:abc>of"}},
            {"type": "edge.put", "body": {"rel": "on", "src": "run:abc", "dst": "resource:gpu0"}, "ts": "2026-11-06T15:40:00+10:30",
             "source": {"kind": "demo-store", "id": "run:abc>on"}},
            {"type": "edge.put", "body": {"rel": "of", "src": "run:abc", "dst": "experiment:unknown"}, "ts": "2026-11-06T15:40:00+10:30",
             "source": {"kind": "demo-store", "id": "run:abc>unknown"}},
            {"type": "result", "body": {"text": "0/40 qualify", "data": {"qualified": 0}}, "actor": {"kind": "system", "name": "demo"},
             "about": ["run:abc"], "ts": "2026-11-06T17:15:00+10:30", "source": {"kind": "demo-store", "id": "bundle:abc"}},
        ]
        path = self.write("items.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(len(collect(self.trace, ME, "items", path=path)), 5)
        state = self.trace.state()
        self.assertEqual(sorted(state.edges), [("of", "run:abc", "experiment:seeds"), ("on", "run:abc", "resource:gpu0")])
        self.assertEqual(state.nodes["run:abc"]["data"], {"batch_size": 4})
        self.assertEqual(collect(self.trace, ME, "items", path=path), [])
        self.assertEqual(self.trace.check(), [])


if __name__ == "__main__":
    unittest.main()
