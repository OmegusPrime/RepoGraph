# RepoGraph Local MVP

RepoGraph is a **local-first repository knowledge graph**, continuous indexer, change-impact engine, Git-shareable Markdown graph, local dashboard, and MCP server for GitHub Copilot/other coding agents.

It is deliberately cloud-free: no Neo4j, hosted vector database, API key, or LLM is required. The local SQLite graph is a derived cache; `PROJECT_GRAPH.md` is deterministic and can be committed so the team shares the project-level graph.

## What is implemented

- Repository structure scan from any local path.
- Symbol/file graph persisted in `.repograph/cache/graph.db` (SQLite/WAL).
- Python AST parsing plus lightweight symbol/import/call extraction for JavaScript, TypeScript, Java, Kotlin, Go, Rust, C/C++, C#, and common config/source files.
- Incremental polling watcher; only changed/deleted files are re-indexed.
- Global project graph with `CONTAINS`, `IMPORTS`, and `CALLS` relationships.
- Change-impact analysis based on inbound graph traversal.
- Token-budgeted `symbol_context` retrieval for AI agents.
- MCP stdio server exposing graph search, compact symbol context, impact, stats, and changed Git context.
- Local dashboard at `http://127.0.0.1:9739`.
- Deterministic `PROJECT_GRAPH.md` export for Git/team sharing.
- `.mcp.json` generation for a workspace-level MCP configuration.
- Core test suite covering scanning, impact, context budgeting, incremental changes, and Markdown export.

## Install

Requires Python 3.10+.

```bash
cd repograph_mvp
python -m pip install -e .
```

## Initialize a repository

```bash
repograph init /path/to/your/repository
```

This creates:

```text
repo/
├── .mcp.json
├── PROJECT_GRAPH.md
└── .repograph/
    ├── config.json
    ├── team.json
    └── cache/
        └── graph.db       # ignored by Git
```

`PROJECT_GRAPH.md`, `.repograph/config.json`, `.repograph/team.json`, and `.mcp.json` are intended to be shareable. `.repograph/cache/` is machine-local.

## Run continuously + dashboard

```bash
repograph watch /path/to/repo --serve
```

The daemon rescans changed files, rebuilds cross-file call/import edges, updates `PROJECT_GRAPH.md`, and refreshes the dashboard data. Open:

```text
http://127.0.0.1:9739
```

## Impact analysis

```bash
repograph impact processPayment --path /path/to/repo --depth 4
repograph impact src/payments/PaymentService.java --path /path/to/repo
```

The response contains resolved graph targets, affected callers/dependents, traversal depth, a numeric blast-radius score, and a LOW/MEDIUM/HIGH/CRITICAL risk label.

## Search

```bash
repograph search PaymentService --path /path/to/repo
```

## Copilot / MCP

`repograph init` creates a workspace `.mcp.json` that launches:

```bash
python -m repograph.mcp_server
```

MCP tools:

- `graph_search(query, limit)`
- `symbol_context(target, depth, token_budget)`
- `impact(target, depth)`
- `graph_stats()`
- `changed_context()`

The intended AI workflow is:

1. Agent asks RepoGraph for a symbol/subgraph.
2. RepoGraph returns only the related graph neighborhood within a token budget.
3. Agent opens actual source only for the handful of files/symbols that require implementation detail.

This avoids scanning the entire repo for every question.

## Git/team model

Do **not** commit `graph.db`. It is a high-frequency derived database and would cause binary merge conflicts.

Commit the deterministic representation instead:

```text
PROJECT_GRAPH.md
.repograph/config.json
.repograph/team.json
.mcp.json
```

Each teammate maintains their own fast local graph cache from the same checked-out source. The Markdown graph gives the team a reviewable project snapshot and fallback AI context.

## Current MVP limitation / next production step

The supplied analyzer is intentionally dependency-free. For production-grade parsing across 100+ languages, replace `RepositoryAnalyzer` extraction with the **Codebase Memory MCP / Tree-sitter backend** and keep RepoGraph's orchestration layers: team graph export, watcher lifecycle, impact dashboard, Git state, and MCP token-budget facade. This project is structured so the analyzer can be swapped without changing the dashboard or AI-facing APIs.

A second production extension is workspace federation: assign a `repo` id to every repository, merge their node/edge sets into one workspace database, and add `HTTP_CALL`, `EVENT_PUBLISH`, `EVENT_CONSUME`, and `DB_SHARED` edges for cross-service impact analysis.

## Test

```bash
python -m unittest discover -s tests -v
```

## License

MIT for this MVP scaffold. When incorporating code from external repositories, retain their applicable license and notices.
