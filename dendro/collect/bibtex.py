"""The works in a BibTeX file, each as a paper node. An entry that changes is collected again and updates its node."""
import hashlib
import os
import re
import unicodedata

from dendro import schema

ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s{}]+)\s*,")
FIELD = re.compile(r"\s*([A-Za-z][\w-]*)\s*=\s*")
ARXIV = re.compile(r"arXiv[:\s]*(\d{4}\.\d{4,5})", re.I)
SKIPPED = ("comment", "string", "preamble")
MARKS = {"'": "́", "`": "̀", "^": "̂", "~": "̃", '"': "̈", "=": "̄", ".": "̇", "c": "̧",
         "v": "̌", "u": "̆", "H": "̋", "k": "̨", "r": "̊"}
ACCENT = re.compile(r"""\\(['`^~"=.]|[cvuHkr](?=[\s{]))\s*\{?\\?([a-zA-Z])\}?""")


def balanced(text, start):
    """The index just past the brace group that opens at start."""
    depth = 0
    for i in range(start, len(text)):
        depth += (text[i] == "{") - (text[i] == "}")
        if depth == 0:
            return i + 1
    return len(text)


def plain(value):
    value = ACCENT.sub(lambda m: unicodedata.normalize("NFC", m.group(2) + MARKS[m.group(1)]), value)
    return re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()


def fields(body):
    """{name: value} of one entry's body."""
    out, at = {}, 0
    while (found := FIELD.match(body, at)):
        at = found.end()
        if body[at:at + 1] == "{":
            end = balanced(body, at)
            value = body[at + 1:end - 1]
        elif body[at:at + 1] == '"':
            end = body.find('"', at + 1) + 1 or len(body)
            value = body[at + 1:end - 1]
        else:
            end = body.find(",", at) if "," in body[at:] else len(body)
            value = body[at:end]
        out[found.group(1).lower()] = plain(value)
        at = body.find(",", end) + 1 or len(body)
    return out


def entries(text):
    """(type, key, fields) of every work in the file."""
    for found in ENTRY.finditer(text):
        if found.group(1).lower() not in SKIPPED:
            end = balanced(text, text.index("{", found.start()))
            yield found.group(1).lower(), found.group(2), fields(text[found.end():end - 1])


def items(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for kind, key, f in entries(text):
        slug = re.sub(r"[^a-z0-9._-]+", "-", key.lower()).strip("-.")
        if not slug or not f.get("title"):
            continue
        arxiv = ARXIV.search(" ".join(f.get(k, "") for k in ("journal", "eprint", "note", "url")))
        data = {"authors": [a.strip() for a in f["author"].split(" and ")] if f.get("author") else None, "year": f.get("year"),
                "venue": f.get("booktitle") or f.get("journal"), "arxiv": arxiv.group(1) if arxiv else f.get("eprint"),
                "doi": f.get("doi"), "url": f.get("url"), "entry": kind, "key": key}
        mark = hashlib.sha256(schema.canonical(f).encode("utf-8")).hexdigest()[:8]
        yield {"type": "node.put", "body": {"id": "paper:" + slug, "title": f["title"], "data": {k: v for k, v in data.items() if v}},
               "actor": {"kind": "system", "name": "bibtex"}, "source": {"kind": "bibtex", "id": f"{key}:{mark}", "file": os.path.basename(path)}}
