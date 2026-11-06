"""The argument graph at a moment: every structural event up to then, applied in order. Never stored, always recomputed."""
from dendro.schema import STRUCTURAL, kind_of, moment


class State:
    def __init__(self):
        self.nodes, self.edges, self.seen = {}, {}, set()

    def live(self, node_id):
        node = self.nodes.get(node_id)
        return bool(node) and node["retired"] is None

    def refuses(self, event):
        """Why this event does not fit what came before it, as a list; empty if it fits."""
        body, out = event["body"], []
        for ref in event.get("refs", []):
            if ref["to"] not in self.seen:
                out.append(f"refers to an event not yet in the log, or dated after this one: {ref['to']}")
        out += [f"about a node that does not exist: {x}" for x in event.get("about", []) if x not in self.nodes]
        if event["type"] == "node.put":
            node = self.nodes.get(body["id"])
            if node is None and "title" not in body:
                out.append(f"a new node needs a title: {body['id']}")
            if node and node["retired"]:
                out.append(f"retired: {body['id']}")
        elif event["type"] == "node.retire":
            if not self.live(body["id"]):
                out.append(f"no live node: {body['id']}")
        elif event["type"] == "edge.put":
            out += [f"no live node: {body[k]}" for k in ("src", "dst") if not self.live(body[k])]
            if (body["rel"], body["src"], body["dst"]) in self.edges:
                out.append("the edge is already there")
        elif event["type"] == "edge.drop":
            if (body["rel"], body["src"], body["dst"]) not in self.edges:
                out.append("no such edge")
        return out

    def apply(self, event):
        body, when = event["body"], event["ts"]
        self.seen.add(event["id"])
        if event["type"] == "node.put":
            node = self.nodes.setdefault(body["id"], {"id": body["id"], "kind": kind_of(body["id"]), "title": None, "summary": None,
                                                      "status": None, "data": {}, "since": when, "changed": when, "retired": None})
            node.update({k: body[k] for k in ("title", "summary", "status") if k in body}, changed=when)
            for key, value in body.get("data", {}).items():
                if value is None:
                    node["data"].pop(key, None)
                else:
                    node["data"][key] = value
        elif event["type"] == "node.retire":
            self.nodes[body["id"]].update(retired=when, changed=when)
            for edge in [e for e in self.edges if body["id"] in e[1:]]:
                del self.edges[edge]
        elif event["type"] == "edge.put":
            self.edges[body["rel"], body["src"], body["dst"]] = when
        elif event["type"] == "edge.drop":
            del self.edges[body["rel"], body["src"], body["dst"]]

    def to_dict(self):
        return {"nodes": [self.nodes[k] for k in sorted(self.nodes)],
                "edges": [{"rel": rel, "src": src, "dst": dst, "since": when} for (rel, src, dst), when in sorted(self.edges.items())]}


def fold(events, at=None):
    """(state, problems) from events already in order. at keeps only what had happened by then."""
    state, found, limit = State(), [], moment(at) if isinstance(at, str) else at
    for event in events:
        if limit and moment(event["ts"]) > limit:
            continue
        refused = state.refuses(event)
        found += [f"{event['id']} {event['type']}: {reason}" for reason in refused]
        if not refused or event["type"] not in STRUCTURAL:
            state.apply(event)
    return state, found
