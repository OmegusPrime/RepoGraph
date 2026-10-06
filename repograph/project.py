from __future__ import annotations

import json
from pathlib import Path
from .util import write_json


def ensure_project(root: Path) -> dict:
    root=Path(root).resolve(); d=root/".repograph"; (d/"cache").mkdir(parents=True,exist_ok=True)
    cfg=d/"config.json"
    if not cfg.exists():
        write_json(cfg,{"version":1,"repo":root.name,"watch_interval_seconds":1.5,"export_markdown":True})
    team=d/"team.json"
    if not team.exists():
        write_json(team,{"version":1,"project":root.name,"graph_markdown":"PROJECT_GRAPH.md","policy":{"commit_markdown_graph":True,"commit_local_database":False}})
    gitignore=root/".gitignore"
    entry="\n# RepoGraph local cache\n.repograph/cache/\n"
    try:
        existing=gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if ".repograph/cache/" not in existing: gitignore.write_text(existing.rstrip()+entry+"\n",encoding="utf-8")
    except OSError: pass
    mcp=root/".mcp.json"
    if not mcp.exists():
        write_json(mcp,{"servers":{"repograph":{"type":"stdio","command":"python","args":["-m","repograph.mcp_server"],"env":{"REPOGRAPH_ROOT":"${workspaceFolder}"}}}})
    return json.loads(cfg.read_text(encoding="utf-8"))
