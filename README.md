# Dendro 年轮

A project's trace: how the work went, recorded as events, and the reports, slides and talks written from it.

An agent trace keeps every step of one task. Dendro keeps every step of one piece of research: the idea, the directions and
corrections, the claims as they changed, each experiment and why it was run, each run with its settings and logs, each result and
how it was read, and the sentence it became in the paper. The paper is one view of that record. The record holds what the page
limit leaves out.

It asks nothing of the researcher. People read and agents write: an agent records things as the work goes, or collects records
that already exist, such as what was typed in a session or the works in a bibliography. Nothing in the interface lets a person
add or remove a node; what a person says or decides is recorded for them.

## Install

macOS and Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/aircoding-inp/dendro/main/install.sh | sh
```

Windows:

```powershell
irm https://raw.githubusercontent.com/aircoding-inp/dendro/main/install.ps1 | iex
```

This connects Claude Code and Codex, whichever you have. It needs Python 3.10 or newer and git, and running it again updates.
Codex asks you to trust a new hook once: `/hooks`, or Settings > Hooks in the app.

Nobody calls the tools. Open your agent in any project and its commits, changed files, releases, references and sessions are
collected by themselves, each at the time it happened. The agent is told which days are unread and writes them up, and what the
records do not show stays unknown. The trace lives under `~/.dendro/`, so nothing is added to the project.

Then ask for what you need: a report, slides, a talk, a weekly update, or to sort out how the thinking went. Each part points back
at the records it rests on.

Any other MCP client runs `python ~/.dendro/app mcp` in the project.

## Use

```bash
python -m dendro --root trace init my-project
python -m dendro --root trace --writer claude-main node put claim:loop --title "Feedback beats independent proposals"
python -m dendro --root trace --writer claude-main say correction "Reproduction is not a contribution" --by human:sims
python -m dendro --root trace --writer claude-main collect claude-session ~/.claude/projects/my-project --by human:sims
python -m dendro --root trace --writer claude-main collect bibtex paper/main.bib
python -m dendro --root trace --writer claude-main collect git .
python -m dendro --root trace --writer claude-main collect latex paper/main.tex
python -m dendro --root trace --writer claude-main collect file run.log --node run:a --field log_file
python -m dendro --root trace state
python -m dendro --root trace check
python -m dendro serve trace        # the read-only site, at http://127.0.0.1:8377/
python -m dendro --root trace --writer claude-main mcp   # the same operations as MCP tools, over stdio
```

`python -m dendro --help` lists every command. [docs/design.md](docs/design.md) has the model and the plan.

## Publish

`serve` only answers on this machine. To put a project online, build static files and upload the folder to any static host:

```bash
python -m dendro serve trace --public             # see first what the public site shows
python -m dendro export site trace --public
```

`--public` leaves out what people said, sources, local paths, machines, and every kept file that is not an image. It does not
leave out readings of what was said, or the paper's text. Read the preview before you publish, and remove `robots.txt` from the
folder when the site should be found by search engines.

## Test

```bash
python -m unittest discover -s tests -t .
```

## License

[MIT](LICENSE)
