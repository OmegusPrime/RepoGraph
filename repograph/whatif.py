from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .impact import impact
from .store import GraphStore

STOP = {
    "a","an","the","to","of","in","on","for","with","and","or","is","are","be","add","change","modify",
    "update","new","make","support","implement","code","service","feature","using","use","from","into","that",
    "this","will","would","should","could","api","application","project","repo","repository"
}
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]*")


def _terms(proposal: str) -> list[str]:
    seen=[]
    for raw in TOKEN_RE.findall(proposal):
        term=raw.strip("./:-").lower()
        if term and term not in STOP and term not in seen:
            seen.append(term)
    return seen[:24]


def proposed_change_impact(store: GraphStore, proposal: str, depth: int = 4, max_roots: int = 8) -> dict:
    """Estimate blast radius without changing source code.

    This is deliberately graph-grounded: the proposal is mapped to existing symbols/files,
    then normal impact traversal is run from the strongest matches. No files are modified.
    """
    proposal=(proposal or "").strip()
    if not proposal:
        return {"proposal":"","risk":"UNKNOWN","score":0,"matched":[],"affected":[],"modules":[],"tests":[],"files":[],"blast_radius_pct":0,"reason":"Proposal is empty"}
    terms=_terms(proposal)
    scored={}
    for term in terms:
        for n in store.search(term, 20):
            sid=n["id"]
            score=scored.setdefault(sid,{"node":n,"score":0,"terms":set()})
            name=(n.get("name") or "").lower(); path=(n.get("path") or "").lower(); sig=(n.get("signature") or "").lower()
            w=8 if name==term else 5 if name.startswith(term) else 3 if term in name else 2 if term in path else 1 if term in sig else 0
            if n.get("kind")=="maven_module": w += 5
            score["score"] += w; score["terms"].add(term)
    ranked=sorted(scored.values(), key=lambda x:(-x["score"], x["node"].get("path", ""), x["node"].get("line",0)))[:max_roots]
    affected={}; total_score=0; risks=[]
    for item in ranked:
        node=item["node"]
        r=impact(store, node["id"], depth=depth, max_nodes=180)
        total_score += r.get("score",0)
        risks.append(r.get("risk","UNKNOWN"))
        for a in r.get("affected",[]):
            cur=affected.get(a["id"])
            if cur is None or a.get("depth",99)<cur.get("depth",99): affected[a["id"]]=a
    affected_list=sorted(affected.values(), key=lambda x:(x.get("depth",99),x.get("path",""),x.get("line",0)))
    files=sorted({
        x.get("path","") for x in affected_list
        if x.get("path") and x.get("kind") != "maven_module"
    })
    module_nodes={}
    for item in ranked:
        node=item["node"]
        if node.get("kind")=="maven_module": module_nodes[node["id"]]=node
    for node in affected_list:
        if node.get("kind")=="maven_module": module_nodes[node["id"]]=node
    modules=Counter({node["name"]:0 for node in module_nodes.values()})
    file_owners={}
    for node in affected_list:
        path=node.get("path","")
        if not path or node.get("kind")=="maven_module": continue
        owners=[owner for owner in store.neighbors(node["id"],"in") if owner["edge_kind"]=="MODULE_CONTAINS"]
        if owners: file_owners[path]=owners[0]["name"]
    for f in files:
        if f in file_owners:
            modules[file_owners[f]] += 1
        else:
            parts=Path(f).parts
            modules[parts[0] if len(parts)>1 else "."] += 1
    tests=sorted({f for f in files if any(k in f.lower() for k in ("test","spec","__tests__"))})
    stats=store.stats(); denominator=max(1,stats.get("files",0)); blast=min(100,round(len(files)*100/denominator,1))
    levels={"UNKNOWN":0,"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}
    risk=max(risks,key=lambda r:levels.get(r,0),default="UNKNOWN")
    # Account for multiple independently matched roots.
    if len(ranked)>=5 and levels.get(risk,0)<2: risk="MEDIUM"
    return {
        "proposal":proposal,"terms":terms,"risk":risk,"score":total_score,
        "matched":[{**x["node"],"match_score":x["score"],"matched_terms":sorted(x["terms"])} for x in ranked],
        "affected":affected_list,"files":files,"modules":[{"name":k,"files":v} for k,v in modules.most_common(12)],
        "tests":tests,"blast_radius_pct":blast,"files_likely_to_change":len(files),"tests_potentially_impacted":len(tests),
        "modules_affected":len(modules),"mode":"simulation","source_modified":False
    }
