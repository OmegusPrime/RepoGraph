from __future__ import annotations

from collections import deque
from .store import GraphStore

EDGE_RISK={"CALLS":4,"IMPORTS":2,"CONTAINS":1,"HTTP_CALL":5,"EVENT_PUBLISH":5,"EVENT_CONSUME":5,"DB_SHARED":4}


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
        # Impact flows primarily to dependents/callers; CONTAINS is traversed both ways by store.
        for n in store.neighbors(nid,"in"):
            other=n["id"]
            if other in seen: continue
            seen.add(other)
            ek=n["edge_kind"]
            w=EDGE_RISK.get(ek,2)
            score += max(1,w*(depth-d))
            affected.append({"id":other,"name":n["name"],"kind":n["node_kind"],"path":n["path"],"line":n["line"],"via":ek,"depth":d+1})
            q.append((other,d+1))
    if score>=120: risk="CRITICAL"
    elif score>=60: risk="HIGH"
    elif score>=25: risk="MEDIUM"
    else: risk="LOW"
    return {"target":target,"resolved":roots,"affected":affected,"score":score,"risk":risk,"depth":depth}
