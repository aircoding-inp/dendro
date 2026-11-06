"""What a project builds on, as `reference` events: the packages it declares, the repositories it links to or includes, the works in
its bibliographies. Copied from its manifests and notes as they stand; which of them matter is a reader's to say.
"""
import configparser
import hashlib
import json
import os
import re
import time
from datetime import datetime

from dendro.collect import bibtex, files, git

DEEP = 2  # a manifest counts this many folders down, so a web/ or server/ beside the root is found and a vendored copy is not
NOTES = 40  # at most this many notes are searched for links
REPOSITORY = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)")
PAPER = re.compile(r"https?://arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")
NAME = re.compile(r"^\s*([A-Za-z0-9][\w.-]*)\s*(?:\[[^\]]*\])?\s*([=<>~!^][^;#\s]*)?")
PEP621 = re.compile(r"^(?:dependencies|requires)\s*=\s*\[(.*?)\]", re.S | re.M)
QUOTED = re.compile(r"""["']([^"']+)["']""")
SECTION = re.compile(r"^\[(?:[\w-]+\.)*(?:dependencies|dev-dependencies)\]\s*$(.*?)(?=^\[|\Z)", re.S | re.M)
PAIR = re.compile(r"""^([\w-]+)\s*=\s*(?:"([^"]*)"|\{.*?version\s*=\s*"([^"]*)")?""", re.M)
GO = re.compile(r"^\s*(?:require\s+)?([\w.-]+\.[a-z]+/[\w./-]+)\s+(v[\w.+-]+)", re.M)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""  # listed by git and gone from the disk


def package(line):
    found = NAME.match(line)
    return (found.group(1), found.group(2)) if found else None


def requirements(text):
    return filter(None, (package(row) for row in text.splitlines() if row.strip() and not row.lstrip().startswith(("#", "-"))))


def pyproject(text):
    return filter(None, (package(row) for block in PEP621.findall(text) for row in QUOTED.findall(block)))


def node(text):
    try:
        manifest = json.loads(text)
    except ValueError:
        return []
    return [(name, version) for part in ("dependencies", "devDependencies") for name, version in (manifest.get(part) or {}).items()]


def cargo(text):
    return [(name, a or b or None) for block in SECTION.findall(text) for name, a, b in PAIR.findall(block)]


MANIFESTS = {"requirements.txt": requirements, "pyproject.toml": pyproject, "package.json": node, "Cargo.toml": cargo, "go.mod": GO.findall}


def own(folder):
    """This project's own name on GitHub, in lower case, if it has one."""
    found = REPOSITORY.search(git.remote(folder).replace("git@github.com:", "https://github.com/"))
    return found.group(1).removesuffix(".git").lower() if found else None


def found(folder, paths):
    """(kind, name, version or None, url or None, data, file) of everything these files name."""
    for path in paths:
        full, base = os.path.join(folder, path), os.path.basename(path)
        if base in MANIFESTS and path.count("/") <= DEEP:
            yield from (("dependency", name, version, None, {}, path) for name, version in MANIFESTS[base](read(full)))
        elif base == ".gitmodules":
            parsed = configparser.ConfigParser(strict=False, interpolation=None)
            parsed.read_string(read(full))
            yield from (("repository", s.split('"')[1], None, parsed[s]["url"], {}, path) for s in parsed.sections() if "url" in parsed[s] and '"' in s)
        elif path.lower().endswith(".bib"):
            for _, key, f in bibtex.entries(read(full)):
                if f.get("title"):
                    data = {k: f[k] for k in ("year", "doi") if f.get(k)}
                    data.update({"key": key, **({"venue": f.get("booktitle") or f["journal"]} if f.get("booktitle") or f.get("journal") else {})})
                    yield "paper", f["title"], None, f.get("url"), data, path


def linked(folder, paths):
    """The repositories and papers linked from a project's notes."""
    mine = own(folder)
    notes = sorted((p for p in paths if p.lower().endswith((".md", ".rst")) and p.count("/") <= DEEP), key=lambda p: p.count("/"))
    for path in notes[:NOTES]:
        text = read(os.path.join(folder, path))
        for name in REPOSITORY.findall(text):
            name = name.removesuffix(".git").rstrip(".")
            if name.lower() != mine:
                yield "repository", name, None, "https://github.com/" + name, {}, path
        for paper in PAPER.findall(text):
            yield "paper", "arXiv:" + paper, None, "https://arxiv.org/abs/" + paper, {}, path


def items(folder):
    """One item per thing named. A package at a new version is a new record, so a project's history of them can be read."""
    paths, latest = files.listed(folder), time.time() - 2
    paths += [".gitmodules"] if os.path.isfile(os.path.join(folder, ".gitmodules")) else []
    for kind, name, version, url, data, path in [*found(folder, paths), *linked(folder, paths)]:
        written = datetime.fromtimestamp(min(os.path.getmtime(os.path.join(folder, path)), latest)).astimezone().replace(microsecond=0)
        data = dict(data, kind=kind, file=path, **{k: v for k, v in (("version", version), ("url", url)) if v})
        mark = hashlib.sha256(name.lower().encode("utf-8")).hexdigest()[:12] if kind == "paper" else name.lower()
        yield {"type": "reference", "body": {"text": name, "data": data}, "actor": {"kind": "system", "name": "references"},
               "ts": written.isoformat(), "source": {"kind": "reference", "id": f"{kind}:{mark}:{version or ''}"}}
