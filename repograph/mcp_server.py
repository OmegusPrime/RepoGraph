from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .context import symbol_context
from .git_sync import GitSyncManager
from .impact import impact
from .whatif import proposed_change_impact
from .quality import collect_quality
from .store import GraphStore

LEGACY_PROTOCOL_VERSION = "2025-11-25"
MODERN_PROTOCOL_VERSION = "2026-07-28"


def project_root() -> Path:
    configured = os.environ.get("REPOGRAPH_ROOT", "").strip()
    # Some clients pass unresolved editor placeholders literally. Falling back
    # to the process working directory prevents silently opening an empty graph
    # at <workspace>/${workspaceFolder}/.repograph.
    if configured and "${" not in configured:
        return Path(configured).resolve()
    return Path(os.getcwd()).resolve()


def db_for(root: Path, team: bool = False) -> Path:
    return root / ".repograph" / "cache" / ("team_graph.db" if team else "graph.db")


TOOLS = [
    {"name":"graph_search","description":"Search the local working-tree repository graph without reading the whole repository.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["query"]}},
    {"name":"symbol_context","description":"Return a compact local graph neighborhood under a strict token budget.","inputSchema":{"type":"object","properties":{"target":{"type":"string"},"depth":{"type":"integer","default":2},"token_budget":{"type":"integer","default":3000}},"required":["target"]}},
    {"name":"impact","description":"Estimate local change blast radius by traversing inbound dependency/call edges.","inputSchema":{"type":"object","properties":{"target":{"type":"string"},"depth":{"type":"integer","default":4}},"required":["target"]}},
    {"name":"team_graph_search","description":"Search the latest fetched remote/team graph without modifying the local worktree.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["query"]}},
    {"name":"team_symbol_context","description":"Return compact context from the latest fetched remote/team graph under a token budget.","inputSchema":{"type":"object","properties":{"target":{"type":"string"},"depth":{"type":"integer","default":2},"token_budget":{"type":"integer","default":3000}},"required":["target"]}},
    {"name":"team_impact","description":"Estimate blast radius against the latest fetched remote/team graph.","inputSchema":{"type":"object","properties":{"target":{"type":"string"},"depth":{"type":"integer","default":4}},"required":["target"]}},
    {"name":"graph_stats","description":"Get local and team graph counts and relationship kinds.","inputSchema":{"type":"object","properties":{}}},
    {"name":"changed_context","description":"Return local Git working-tree and remote synchronization state.","inputSchema":{"type":"object","properties":{}}},
    {"name":"git_sync","description":"Fetch configured Git remotes and incrementally refresh the isolated team graph. Never pulls into the user's working tree.","inputSchema":{"type":"object","properties":{"force":{"type":"boolean","default":False}}}},
    {"name":"proposed_change_impact","description":"Simulate the impact of a proposed natural-language change without modifying source files.","inputSchema":{"type":"object","properties":{"proposal":{"type":"string"},"depth":{"type":"integer","default":4},"team":{"type":"boolean","default":False}},"required":["proposal"]}},
    {"name":"quality_metrics","description":"Read local coverage artifacts and optional SonarQube metrics for the dashboard.","inputSchema":{"type":"object","properties":{}}},
]


def result(value):
    return {"content":[{"type":"text","text":json.dumps(value, indent=2, default=str)}],"structuredContent":value}


def main():
    root = project_root()
    store = GraphStore(db_for(root))
    team_store = GraphStore(db_for(root, team=True))
    git_manager = GitSyncManager(root, team_store)
    server_info = {"name":"repograph-local","version":"0.3.5"}
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        req = {}
        try:
            req = json.loads(raw)
            mid = req.get("id")
            method = req.get("method")
            params = req.get("params") or {}
            if method == "server/discover":
                out = {"supportedVersions":[MODERN_PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION],"capabilities":{"tools":{}},"instructions":"Query RepoGraph with a token budget before broad repository exploration. Use team_* tools for the latest fetched remote state.","_meta":{"io.modelcontextprotocol/serverInfo":server_info}}
            elif method == "initialize":
                proposed = params.get("protocolVersion", LEGACY_PROTOCOL_VERSION)
                negotiated = proposed if proposed != MODERN_PROTOCOL_VERSION else LEGACY_PROTOCOL_VERSION
                out = {"protocolVersion":negotiated,"capabilities":{"tools":{}},"serverInfo":server_info}
            elif method == "tools/list":
                out = {"tools": TOOLS}
            elif method == "tools/call":
                name = params.get("name")
                a = params.get("arguments") or {}
                if name == "graph_search": out = result(store.search(a.get("query", ""), int(a.get("limit", 20))))
                elif name == "symbol_context": out = result(symbol_context(store, a.get("target", ""), int(a.get("depth", 2)), int(a.get("token_budget", 3000))))
                elif name == "impact": out = result(impact(store, a.get("target", ""), int(a.get("depth", 4))))
                elif name == "team_graph_search": out = result(team_store.search(a.get("query", ""), int(a.get("limit", 20))))
                elif name == "team_symbol_context": out = result(symbol_context(team_store, a.get("target", ""), int(a.get("depth", 2)), int(a.get("token_budget", 3000))))
                elif name == "team_impact": out = result(impact(team_store, a.get("target", ""), int(a.get("depth", 4))))
                elif name == "graph_stats": out = result({"local": store.stats(), "team": team_store.stats()})
                elif name == "changed_context": out = result(git_manager.status())
                elif name == "git_sync": out = result(git_manager.sync(force=bool(a.get("force", False))))
                elif name == "proposed_change_impact": out = result(proposed_change_impact(team_store if a.get("team") else store, a.get("proposal", ""), int(a.get("depth", 4))))
                elif name == "quality_metrics": out = result(collect_quality(root))
                else: raise ValueError(f"Unknown tool: {name}")
            elif method in ("notifications/initialized", "ping"):
                if mid is None:
                    continue
                out = {}
            else:
                if mid is None:
                    continue
                raise ValueError(f"Unsupported method: {method}")
            if mid is not None:
                meta = (params.get("_meta") or {}) if isinstance(params, dict) else {}
                modern = meta.get("io.modelcontextprotocol/protocolVersion") == MODERN_PROTOCOL_VERSION or method == "server/discover"
                if modern and isinstance(out, dict):
                    out.setdefault("_meta", {}).setdefault("io.modelcontextprotocol/serverInfo", server_info)
                sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":mid,"result":out}) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            mid = req.get("id") if isinstance(req, dict) else None
            if mid is not None:
                sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":mid,"error":{"code":-32603,"message":str(exc)}}) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    main()
