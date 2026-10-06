from __future__ import annotations

from collections import deque
from .store import GraphStore


def estimate_tokens(text: str) -> int:
    return max(1,(len(text)+3)//4)


def symbol_context(store: GraphStore, target: str, depth: int=2, token_budget: int=3000) -> dict:
    roots=store.resolve(target)
    if not roots:
        return {"target":target,"items":[],"estimated_tokens":0}
    q=deque((r["id"],0) for r in roots[:3]); seen=set(); items=[]; used=0
    while q:
        nid,d=q.popleft()
        if nid in seen or d>depth: continue
        seen.add(nid)
        node=store.node(nid)
        if not node: continue
        line=f"{node['kind']} {node['name']} — {node['path']}:{node['line']} {node.get('signature','')}"
        t=estimate_tokens(line)
        if used+t>token_budget: break
        items.append({"id":nid,"kind":node["kind"],"name":node["name"],"path":node["path"],"line":node["line"],"signature":node.get("signature",""),"depth":d})
        used+=t
        if d<depth:
            for n in store.neighbors(nid,"both"):
                other=n["dst"] if n["src"]==nid else n["src"]
                if other not in seen: q.append((other,d+1))
    return {"target":target,"items":items,"estimated_tokens":used,"token_budget":token_budget}
