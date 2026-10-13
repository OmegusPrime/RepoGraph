from __future__ import annotations

import json
import sys
from pathlib import Path

from .util import read_json, write_json


def ensure_project(root: Path) -> dict:
    root = Path(root).resolve()
    d = root / ".repograph"
    (d / "cache").mkdir(parents=True, exist_ok=True)
    (d / "worktrees").mkdir(parents=True, exist_ok=True)
    cfg = d / "config.json"
    current = read_json(cfg, {}) if cfg.exists() else {}
    defaults = {
        "version": 3,
        "repo": root.name,
        "watch_interval_seconds": 1.5,
        "export_markdown": True,
        "git": {
            "enabled": True,
            "remote": "origin",
            "branch": None,
            "fetch_interval_seconds": 60,
        },
        "context": {"default_token_budget": 3000},
        "quality": {"sonarqube": True, "coverage": True},
    }
    merged = defaults
    if isinstance(current, dict):
        merged = {**defaults, **current}
        merged["git"] = {**defaults["git"], **(current.get("git") or {})}
        merged["context"] = {**defaults["context"], **(current.get("context") or {})}
        merged["version"] = 3
    write_json(cfg, merged)

    team = d / "team.json"
    team_current = read_json(team, {}) if team.exists() else {}
    team_defaults = {
        "version": 3,
        "project": root.name,
        "graph_markdown": "PROJECT_GRAPH.md",
        "policy": {
            "commit_markdown_graph": True,
            "commit_local_database": False,
            "remote_graph_is_derived": True,
        },
    }
    write_json(team, {**team_defaults, **team_current, "version": 3})

    gitignore = root / ".gitignore"
    entries = [".repograph/cache/", ".repograph/worktrees/"]
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        additions = [e for e in entries if e not in existing]
        if additions:
            gitignore.write_text(existing.rstrip() + "\n\n# RepoGraph local derived state\n" + "\n".join(additions) + "\n", encoding="utf-8")
    except OSError:
        pass

    mcp = root / ".mcp.json"
    mcp_value = read_json(mcp, {}) if mcp.exists() else {}
    if "servers" in mcp_value and "mcpServers" not in mcp_value:
        mcp_value["mcpServers"] = mcp_value.pop("servers")
    mcp_value.setdefault("mcpServers", {})
    # Always refresh our own entry on upgrade so a stale `py`/`python` launcher
    # cannot point Copilot at a different environment from the installed package.
    mcp_value["mcpServers"]["repograph"] = {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "repograph.mcp_server"],
        # Portable MCP clients do not consistently interpolate VS Code's
        # ${workspaceFolder} token inside environment values. Use the actual
        # initialized repository path so the server cannot create an empty
        # graph below a literal "${workspaceFolder}" directory.
        "env": {"REPOGRAPH_ROOT": str(root)},
    }
    write_json(mcp, mcp_value)
    return merged
