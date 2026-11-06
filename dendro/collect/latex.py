"""A paper's LaTeX source as section nodes that hold their text, and an edge to each work a section cites.

A section that changes is collected again and updates its node, so the trace keeps how each part of the paper read on each day.
The abstract is a section. A macro that takes no arguments is written out. Some sources keep a `% tags:` comment under a paragraph to say what backs it, with a letter before each
bracket, such as L for literature, M for measured and H for hypothesis. They are copied as the section's notes, each with the place
in the text it follows. A figure the section includes is kept in the trace, as its SVG or PNG twin when the source has one.
"""
import hashlib
import os
import re

INPUT = re.compile(r"\\(?:input|include)\{([^}]+)\}")
HEADING = re.compile(r"^[^%\n]*?\\(section|subsection|subsubsection)\*?\{", re.M)
ABSTRACT = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.S)
LABEL = re.compile(r"\\label\{([^}]+)\}")
CITE = re.compile(r"\\[cC]ite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]+)\}")
TAG = re.compile(r"\b([A-Z])\[")
MACRO = re.compile(r"^\s*\\(?:re)?newcommand\{\\([a-zA-Z]+)\}\{(.*)\}\s*$")
GRAPHIC = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
MARK = "\0"
END = re.compile(r"\\(?:bibliography\b|end\{document\}|appendix\b)")
LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3}


def is_tags(line):
    return line.lstrip().startswith("%") and "tags:" in line


def source(path, seen=()):
    """(file, line) for the file with everything it inputs put in place. Comments go, except the tags comments."""
    if path in seen or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    out, here = [], os.path.dirname(path)
    for line in lines:
        if line.lstrip().startswith("%"):
            out += [(os.path.basename(path), line)] if is_tags(line) else []
            continue
        found = INPUT.search(line)
        if found:
            name = found.group(1) if found.group(1).endswith(".tex") else found.group(1) + ".tex"
            out += source(os.path.join(here, name), (*seen, path))
        else:
            out.append((os.path.basename(path), line))
    return out


def expanded(lines):
    """The lines with each macro that takes no arguments written out, so that a section's text keeps the word it stands for."""
    macros = [found.groups() for found in map(MACRO.match, (line for _, line in lines)) if found]
    for name, value in macros:
        value = value.replace("\\xspace", "")
        pattern = re.compile(r"\\" + name + r"(?![a-zA-Z])(?:\{\})?")
        lines = [(file, line if MACRO.match(line) else pattern.sub(lambda _: value, line)) for file, line in lines]
    return lines


def braced(text, start):
    """(what the brace group opening at start holds, the index after it)."""
    depth = 0
    for i in range(start, len(text)):
        depth += (text[i] == "{") - (text[i] == "}")
        if depth == 0:
            return text[start + 1:i], i + 1
    return text[start + 1:], len(text)


def plain(text):
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"\\[a-zA-Z]+|[{}~]", " ", text)).strip()


def slug(text):
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")


def words(text):
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|[\u4e00-\u9fff]", plain(text)))


def noted(line):
    """What a tags comment says, as [{"k": letter, "t": text}]. A bracket may hold brackets."""
    text, out, at = line.split("tags:", 1)[1], [], 0
    while True:
        found = TAG.search(text, at)
        if not found:
            return out
        depth, i = 0, found.end() - 1
        while i < len(text):
            depth += (text[i] == "[") - (text[i] == "]")
            if depth == 0:
                break
            i += 1
        out.append({"k": found.group(1), "t": text[found.end():i].strip()})
        at = i + 1


def caption(body, at):
    found = body.find("\\caption", at)
    return plain(braced(body, body.index("{", found))[0]) if found >= 0 and "{" in body[found:] else None


def figures(body, folder, keep):
    """Each figure a section includes, kept. A twin a browser can draw is taken over a PDF."""
    out = []
    for found in GRAPHIC.finditer(body):
        stem = os.path.splitext(os.path.join(folder, found.group(1)))[0]
        for path in (stem + ".svg", stem + ".png", stem + ".jpg", os.path.join(folder, found.group(1)), stem + ".pdf"):
            if os.path.isfile(path):
                out.append(dict(keep(path), caption=caption(body, found.end())))
                break
    return out


def parts(lines):
    """Sections in order, each {title, level, label, body, file}; body still has its tags comments."""
    text = "\n".join(line for _, line in lines)
    file_at = lambda index: lines[text.count("\n", 0, index)][0]
    abstract = ABSTRACT.search(text)
    if abstract:
        yield {"title": "Abstract", "level": 1, "label": "abstract", "body": abstract.group(1), "file": file_at(abstract.start())}
    heads = [(m.end(), m.group(1)) + braced(text, m.end() - 1) for m in HEADING.finditer(text)]
    starts = [m.start() for m in HEADING.finditer(text)]
    for i, (at, kind, title, end) in enumerate(heads):
        body = END.split(text[end:starts[i + 1] if i + 1 < len(heads) else len(text)])[0]
        label = LABEL.search(body[:200])
        yield {"title": plain(title), "level": LEVEL[kind], "label": label.group(1) if label else None, "body": body, "file": file_at(at)}


def items(path, prefix="", keep=None):
    order, trail, used, folder = 0, {}, set(), os.path.dirname(os.path.abspath(path))
    origin, actor = {"kind": "latex", "file": os.path.basename(path)}, {"kind": "system", "name": "latex"}
    for part in parts(expanded(source(os.path.abspath(path)))):
        name = slug((part["label"] or part["title"]).split(":")[-1]) or f"part-{order}"
        node = "section:" + slug(f"{prefix}-{name}" if prefix else name)
        while node in used:
            node += "-x"
        used.add(node)
        trail[part["level"]] = node
        lines = part["body"].split("\n")
        said = [noted(line) for line in lines if is_tags(line)]
        marked = LABEL.sub("", "\n".join(MARK if is_tags(line) else line for line in lines)).strip()
        pieces = marked.split(MARK)
        body = "".join(pieces).strip()
        notes, at = [], 0
        for piece, note in zip(pieces, said):
            at += len(piece)
            notes.append({"at": at, "tags": note})
        letters = [tag["k"] for note in said for tag in note]
        keys = sorted({k.strip() for group in CITE.findall(body) for k in group.split(",") if k.strip()})
        data = {"level": part["level"], "order": order, "parent": trail.get(part["level"] - 1), "file": part["file"],
                "words": words(body), "todos": len(re.findall(r"\\todo\b", body)), "cites": len(keys), "text": body,
                "backing": {t: letters.count(t) for t in sorted(set(letters))} or None, "notes": notes or None,
                "figures": (figures(body, folder, keep) if keep else None) or None}
        mark = hashlib.sha256((part["title"] + "\0" + marked).encode("utf-8")).hexdigest()[:8]
        yield {"type": "node.put", "body": {"id": node, "title": part["title"], "data": {k: v for k, v in data.items() if v is not None}},
               "actor": actor, "source": dict(origin, id=f"{node}:{mark}")}
        for key in keys:
            paper = "paper:" + slug(key)
            yield {"type": "edge.put", "body": {"rel": "cites", "src": node, "dst": paper}, "actor": actor,
                   "source": dict(origin, id=f"{node}>{paper}")}
        order += 1
