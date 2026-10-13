from __future__ import annotations

from collections import deque
from .store import GraphStore

EDGE_RISK={
    "CALLS":4,"IMPORTS":2,"CONTAINS":1,"HTTP_CALL":5,"EVENT_PUBLISH":5,"EVENT_CONSUME":5,"DB_SHARED":4,
    "DEPENDS_ON_MODULE":7,"MODULE_CONTAINS":2,"PARENT_OF":1,
}
OUTBOUND_EXPANSION={"CONTAINS","MODULE_CONTAINS","PARENT_OF"}


def impact(store: GraphStore, target: str, depth: int=4, max_nodes: int=250) -> dict:
    roots=store.resolve(target)
    if not roots:
        return {"target":target,"resolved":[],"affected":[],"risk":"UNKNOWN","score":0,"reason":"Target not found"}
    root_ids={r["id"] for r in roots}
    q=deque((rid,0) for rid in root_ids)
    seen=set(root_ids); affected=[]; score=0
    while q and len(affected)<max_nodes:
        nid,d=q.popleft()
        if d>=depth: continue
        # Dependencies flow to inbound dependents (A DEPENDS_ON B means changing
        # B can affect A). Containment also expands outward so starting from a
        # module includes its files/classes in the blast radius.
        # A child-module change does not make sibling modules consumers merely
        # because they share an aggregator, so PARENT_OF only expands outward
        # when the parent itself is the impact root/path.
        neighbors=[n for n in store.neighbors(nid,"in") if n["edge_kind"]!="PARENT_OF"]
        neighbors.extend(n for n in store.neighbors(nid,"out") if n["edge_kind"] in OUTBOUND_EXPANSION)
        neighbors.sort(key=lambda n:(n["node_kind"]!="maven_module", n["path"], n["line"]))
        for n in neighbors:
            other=n["id"]
            if other in seen: continue
            seen.add(other)
            ek=n["edge_kind"]
            w=EDGE_RISK.get(ek,2)
            score += max(1,w*(depth-d))
            affected.append({"id":other,"repo":n["repo"],"name":n["name"],"kind":n["node_kind"],"path":n["path"],"line":n["line"],"via":ek,"depth":d+1})
            q.append((other,d+1))
    if score>=120: risk="CRITICAL"
    elif score>=60: risk="HIGH"
    elif score>=25: risk="MEDIUM"
    else: risk="LOW"
    return {"target":target,"resolved":roots,"affected":affected,"score":score,"risk":risk,"depth":depth}
