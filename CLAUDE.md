# Dendro

A research trace platform: an append-only log of events and read-only views of it. `docs/design.md` is the design; keep it true.

- It asks nothing of the researcher, so people read and agents write. Never add a way for a person to add, change or remove a
  node or an event. What a person says is recorded with `--by human:NAME` by the agent they said it to.
- A collector copies records that exist and does not judge. Reading them (an idea or a correction, a paper's summary) is a
  separate event by an agent that points back at what was collected.
- Events are never edited or deleted, in code or by hand. A fix is a new event.
- State is folded from events and never stored.
- The core has no dependencies outside the standard library. Run it as `python -m dendro` from the repo root.
- The product is the platform. Research projects are its tenants; do not build one project's needs into the core.
  What only one project understands, such as its experiment ledgers, goes in `tenants/<project>/` as an exporter that writes
  items for `collect items`.
- Prefer real records to conversation: runs from job records, code from git, the paper from its source.
- UI text is short: no page that explains itself, each fact shown once.

Tests: `python -m unittest discover -s tests -t .`
