from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from .context import symbol_context
from .impact import impact
from .store import GraphStore
from .util import git_info

LEGACY_PROTOCOL_VERSION="2025-11-25"
MODERN_PROTOCOL_VERSION="2026-07-28"

def project_root() -> Path:
    return Path(os.environ.get("REPOGRAPH_ROOT",os.getcwd())).resolve()

def db_for(root: Path) -> Path:
    return root/".repograph"/"cache"/"graph.db"

TOOLS=[
 {"name":"graph_search","description":"Search repository graph symbols and files without reading the whole repository.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["query"]}},
 {"name":"symbol_context","description":"Return a compact graph neighborhood for a symbol/path under a token budget.","inputSchema":{"type":"object","properties":{"target":{"type":"string"},"depth":{"type":"integer","default":2},"token_budget":{"type":"integer","default":3000}},"required":["target"]}},
 {"name":"impact","description":"Estimate change blast radius by traversing inbound dependency/call edges.","inputSchema":{"type":"object","properties":{"target":{"type":"string"},"depth":{"type":"integer","default":4}},"required":["target"]}},
 {"name":"graph_stats","description":"Get repository graph counts and node/edge kinds.","inputSchema":{"type":"object","properties":{}}},
 {"name":"changed_context","description":"Return Git working-tree changes so an agent can request only relevant graph context.","inputSchema":{"type":"object","properties":{}}}
]

def result(value):
    return {"content":[{"type":"text","text":json.dumps(value,indent=2,default=str)}],"structuredContent":value}

def main():
    root=project_root(); store=GraphStore(db_for(root))
    server_info={"name":"repograph-local","version":"0.1.0"}
    for raw in sys.stdin:
        raw=raw.strip()
        if not raw: continue
        try:
            req=json.loads(raw); mid=req.get("id"); method=req.get("method"); params=req.get("params") or {}
            if method=="server/discover":
                out={"supportedVersions":[MODERN_PROTOCOL_VERSION,LEGACY_PROTOCOL_VERSION],"capabilities":{"tools":{}},"instructions":"Use graph_search and symbol_context before opening broad sets of repository files.","_meta":{"io.modelcontextprotocol/serverInfo":server_info}}
            elif method=="initialize":
                proposed=params.get("protocolVersion",LEGACY_PROTOCOL_VERSION)
                negotiated=proposed if proposed != MODERN_PROTOCOL_VERSION else LEGACY_PROTOCOL_VERSION
                out={"protocolVersion":negotiated,"capabilities":{"tools":{}},"serverInfo":server_info}
            elif method=="tools/list": out={"tools":TOOLS}
            elif method=="tools/call":
                name=params.get("name"); a=params.get("arguments") or {}
                if name=="graph_search": out=result(store.search(a.get("query",""),int(a.get("limit",20))))
                elif name=="symbol_context": out=result(symbol_context(store,a.get("target",""),int(a.get("depth",2)),int(a.get("token_budget",3000))))
                elif name=="impact": out=result(impact(store,a.get("target",""),int(a.get("depth",4))))
                elif name=="graph_stats": out=result(store.stats())
                elif name=="changed_context": out=result(git_info(root))
                else: raise ValueError(f"Unknown tool: {name}")
            elif method in ("notifications/initialized","ping"):
                if mid is None: continue
                out={}
            else:
                if mid is None: continue
                raise ValueError(f"Unsupported method: {method}")
            if mid is not None:
                meta=(params.get("_meta") or {}) if isinstance(params,dict) else {}
                modern=meta.get("io.modelcontextprotocol/protocolVersion")==MODERN_PROTOCOL_VERSION or method=="server/discover"
                if modern and isinstance(out,dict):
                    out.setdefault("_meta",{}).setdefault("io.modelcontextprotocol/serverInfo",server_info)
                sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":mid,"result":out})+"\n");sys.stdout.flush()
        except Exception as e:
            try: mid=req.get("id")
            except Exception: mid=None
            if mid is not None:
                sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":mid,"error":{"code":-32603,"message":str(e)}})+"\n");sys.stdout.flush()

if __name__=="__main__": main()
