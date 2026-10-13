# RepoGraph Local v0.3.5

RepoGraph is a **local-first repository knowledge graph**, continuous indexer, Git-aware team graph, change-impact engine, compact Git-shareable project summary, local dashboard, and MCP server for GitHub Copilot/other coding agents.

The full graph stays local in SQLite. AI agents retrieve only a small graph neighborhood under a token budget instead of scanning the whole repository. Remote Git changes are fetched into isolated hidden worktrees, so RepoGraph can understand teammates' latest commits **without running `git pull` or modifying your working tree**.

## v0.3.5 Copilot workspace-root fix

- Writes the resolved repository path into `REPOGRAPH_ROOT` instead of relying on editor-specific `${workspaceFolder}` interpolation.
- Falls back safely to the MCP process working directory if a client passes an unresolved placeholder literally.
- Prevents Copilot from silently opening an empty database under a `${workspaceFolder}` subdirectory.

## v0.3.4 MCP startup fix

- Fixed invalid lowercase JSON boolean literals in the Python MCP tool definitions.
- Added an end-to-end MCP initialize and tool-discovery regression test.

## v0.3.3 Maven multi-module indexing

- Parses every repository `pom.xml` with namespace-aware, offline XML handling.
- Creates first-class `maven_module` nodes for aggregators and child modules.
- Adds `PARENT_OF`, `DEPENDS_ON_MODULE`, and `MODULE_CONTAINS` relationships.
- Resolves intra-repository dependencies by Maven group/artifact coordinates, with a safe unique-artifact fallback.
- Links each indexed source file and class to its deepest owning Maven module.
- Traverses module dependents transitively during impact and what-if analysis.
- Prioritizes and labels Maven modules in the dashboard dependency graph.
- Adds a synthetic four-module fixture covering `A -> B`, `A -> C`, `D -> A`, ownership, dashboard visibility, and transitive impact.

## v0.3.1 scalability hotfix

- Fixed `sqlite3.OperationalError: too many SQL variables` when re-indexing/removing repositories with many graph nodes.
- Repository/file cleanup now uses SQLite subqueries instead of one bound parameter per node ID.
- Added repository/path indexes for faster large-workspace cleanup.
- Added a regression test with an artificially low SQLite variable limit.


## v0.2.0 changes

- Added remote Git polling (`git fetch`) and one-shot `git-sync`.
- Added isolated remote worktrees under `.repograph/worktrees/`.
- Added a separate **team graph**: `.repograph/cache/team_graph.db`.
- Added multi-repository workspace discovery and repository namespaces.
- Prevented unqualified `CALLS`/`IMPORTS` resolution from jumping across repository boundaries.
- Added Git status to the dashboard: local commit, remote ref, indexed remote commit, ahead/behind.
- Added dashboard **Fetch & sync now** action.
- Added MCP tools for the remote/team graph: `team_graph_search`, `team_symbol_context`, `team_impact`, and `git_sync`.
- Replaced the enormous full Markdown dump with a compact `PROJECT_GRAPH.md` architecture/team summary. The full symbol/edge data remains in SQLite.
- Added optional Git hooks for immediate re-indexing after local commit/checkout/merge/rewrite/applypatch.
- Migrates older `.mcp.json` `servers` configuration to `mcpServers`.

## Install / upgrade

Requires Python 3.10+.

From this project directory:

```bat
py -m pip install -e .
```

If `repograph.exe` is not on PATH, either add your Python `Scripts` directory to PATH or run the CLI through Python:

```bat
py -m repograph.cli --help
```

## Initialize

For one repository:

```bat
repograph init "D:\path\to\repo" --git-sync
```

For a workspace containing several repositories:

```bat
repograph init "D:\iDEAfORGE" --git-sync
```

RepoGraph detects nested Git repositories and keeps their symbol namespaces separate.

Generated state:

```text
workspace/
├── .mcp.json
├── PROJECT_GRAPH.md          # compact team summary
└── .repograph/
    ├── config.json
    ├── team.json
    ├── cache/
    │   ├── graph.db          # your current local checkout(s)
    │   └── team_graph.db     # latest fetched remote/team state
    └── worktrees/
        └── ...               # isolated remote checkouts
```

`.repograph/cache/` and `.repograph/worktrees/` are ignored by Git.

## Recommended always-running command

```bat
repograph watch "D:\iDEAfORGE" --serve --git --git-interval 60
```

This simultaneously watches:

1. **Filesystem edits** on your machine (fast local polling).
2. **Local Git changes** as files/branches are updated.
3. **Remote Git changes** every 60 seconds via `git fetch`.

Remote Git synchronization does **not** run `git pull`. RepoGraph indexes the remote ref from a hidden isolated worktree and updates `team_graph.db`.

Open the dashboard at:

```text
http://127.0.0.1:9739
```

## Git commands

Fetch remotes and update the team graph immediately:

```bat
repograph git-sync "D:\iDEAfORGE"
```

Force a complete remote re-index:

```bat
repograph git-sync "D:\iDEAfORGE" --force
```

Inspect local/remote/indexed commit state:

```bat
repograph git-status "D:\iDEAfORGE"
```

Pin remote/branch if required:

```bat
repograph watch "D:\iDEAfORGE" --serve --git --remote origin --branch main
```

### Optional Git hooks

```bat
repograph install-hooks "D:\iDEAfORGE"
```

Hooks are appended without replacing existing hook contents. Remote polling is still recommended because hooks only react to Git activity on the current machine.

## Local vs team graph

RepoGraph deliberately keeps two graphs:

```text
LOCAL GRAPH                              TEAM GRAPH
.repograph/cache/graph.db                .repograph/cache/team_graph.db

Your branch + uncommitted edits          Latest fetched origin/main (or configured ref)
       │                                         │
       └────────────── MCP ──────────────────────┘
```

This lets an agent answer both:

- "What does my current code do?"
- "What changed on the team's latest remote branch?"

without overwriting your worktree.

## Copilot / MCP

`repograph init` maintains a workspace `.mcp.json` launching:

```bat
py -m repograph.mcp_server
```

Available MCP tools:

### Local working tree

- `graph_search(query, limit)`
- `symbol_context(target, depth, token_budget)`
- `impact(target, depth)`

### Latest fetched team/remote state

- `team_graph_search(query, limit)`
- `team_symbol_context(target, depth, token_budget)`
- `team_impact(target, depth)`

### Git / control

- `graph_stats()`
- `changed_context()`
- `git_sync(force)`

Recommended agent instruction:

```text
Use RepoGraph graph_search/symbol_context before broad repository searches.
Keep RepoGraph context under the requested token budget.
Use team_* tools when I ask about code pushed by other developers or origin/main.
Use impact/team_impact before making changes with a large blast radius.
```

## Token usage

Do **not** attach the full graph database or repeatedly paste `PROJECT_GRAPH.md` into Copilot.

The intended workflow is:

```text
Question
  ↓
graph_search
  ↓
symbol_context(target, token_budget=3000)
  ↓
small relevant subgraph
  ↓
open only the required source files
```

`PROJECT_GRAPH.md` is now intentionally compact and contains repository status, graph counts, relationship summaries, a limited set of high-connectivity symbols, working-tree changes, and recent graph events. The detailed 10k/100k+ node graph stays in SQLite.

## Impact analysis

Local branch/current edits:

```bat
repograph impact processPayment --path "D:\path\to\repo" --depth 4
```

Latest fetched team graph:

```bat
repograph impact processPayment --path "D:\path\to\repo" --depth 4 --team
```

## Search

```bat
repograph search PaymentService --path "D:\path\to\repo"
repograph search PaymentService --path "D:\path\to\repo" --team
```

## Safety model for Git

RepoGraph remote synchronization performs approximately:

```text
git fetch origin
      ↓
read origin/main SHA
      ↓
update isolated .repograph/worktrees/<repo>
      ↓
incrementally index that checkout into team_graph.db
```

It does **not** automatically:

```text
git pull
git merge
git rebase
git reset your working tree
```

## Current analyzer limitation

The MVP analyzer is still deliberately lightweight. It uses Python AST plus regex extraction for several common languages. For production-grade semantic resolution across many languages, the next major step is to plug in the Codebase Memory/Tree-sitter/LSP analyzer while retaining RepoGraph's Git synchronization, local/team graph separation, token-budget API, and dashboard.

## Test

```bat
py -m unittest discover -s tests -v
```

The current test suite includes an end-to-end two-developer Git test verifying that a remote push updates `team_graph.db` without modifying the other developer's working checkout.

## License

MIT for this MVP scaffold. When incorporating code from external repositories, retain their applicable license and notices.

---

# v0.3.0 Executive Intelligence Upgrade

This package is v0.3.1. It keeps all v0.3.0 executive-dashboard and pre-change intelligence features and adds the SQLite scalability hotfix above.

## New dashboard

Run:

```bat
repograph watch "D:\iDEAfORGE" --serve --git --git-interval 60
```

Open `http://127.0.0.1:9739`.

The dashboard now includes the five-tier executive layout (Health, Intelligence, Operations, Efficiency, Activity), Knowledge Health, release/dependency health, local/team sync, dependency visualization, commit activity, SonarQube/code-quality cards, coverage/test metrics, and a **Proposed Change Impact** panel.

## What-if impact before changing code

CLI:

```bat
repograph what-if "Add OAuth2 authentication middleware to Payment API" --path "D:\iDEAfORGE"
```

MCP tool:

```text
proposed_change_impact(proposal, depth, team)
```

The simulation does not patch or write source files. It extracts meaningful terms from the proposal, locates matching graph roots, traverses the existing dependency/call graph, and reports risk, affected modules/files/tests, blast-radius percentage, and matched symbols.

## SonarQube and coverage

The dashboard automatically looks for local artifacts including:

- `coverage.xml` (Coverage.py / Cobertura-style)
- `jacoco.xml`
- `lcov.info`
- `.repograph/quality.json` (CI/custom override)

Inspect from CLI:

```bat
repograph quality "D:\iDEAfORGE"
```

For live SonarQube metrics, configure either `sonar-project.properties` or environment variables:

```bat
set SONAR_HOST_URL=http://localhost:9000
set SONAR_PROJECT_KEY=my-project
set SONAR_TOKEN=your-token
```

The dashboard can display coverage, bugs, vulnerabilities, code smells, duplication, maintainability, reliability, security rating, security hotspots, and quality-gate state. Sonar credentials are not stored in the graph.

You can also produce a CI-derived `.repograph/quality.json`, for example:

```json
{
  "coverage": 81.4,
  "test_pass_rate": 97.8,
  "bugs": 0,
  "vulnerabilities": 0,
  "code_smells": 12,
  "duplications": 2.9,
  "maintainability": "A",
  "reliability": "A",
  "security": "A",
  "quality_gate": "Passed"
}
```

## Review fixes included

- **Non-Python symbol attribution:** generic parsers now track brace-delimited symbol ownership instead of leaving all later calls/imports attached to the last declaration.
- **Cross-edge rebuild scaling:** per-repository nodes are loaded directly and indexed by path/name; repeated full-node filtering was removed.
- **MCP runtime correctness:** `.mcp.json` is refreshed to use the exact Python executable that initialized/upgraded RepoGraph rather than assuming `python`/`py` resolves to the right environment.
- **Repository-scoped lookup:** `GraphStore.search()` and `resolve()` now support repo constraints.
- **Multi-repo isolation:** retained from v0.2 and used throughout local/team graph handling.

## New MCP tools

In addition to the v0.2 tools:

- `proposed_change_impact` — graph-grounded what-if analysis with no source modifications.
- `quality_metrics` — coverage + SonarQube/code-quality data.

## Validation

Run:

```bat
py -m unittest discover -s tests -v
```

v0.3.5 contains 21 passing tests, including MCP startup/tool discovery and resolved workspace-root configuration, Maven parent/dependency/ownership indexing, transitive module impact, dashboard module visibility, the large-repository SQLite-variable regression, remote Git isolation, multi-repo namespace isolation, non-Python attribution regression coverage, repo-scoped search, coverage ingestion, correct MCP Python selection, and no-write what-if analysis.

## v0.3.2 dashboard interaction fixes

- Sidebar navigation is now made of real accessible buttons and scrolls to live sections.
- Tier cards and all 12 dashboard widgets are clickable.
- Search now has a visible Search button and Enter-key behavior.
- Analyze Impact, Git Sync, Refresh, graph mode switching, and diagnostics show busy/error/success feedback.
- Dashboard API failures no longer silently break every other widget.
- Added local/team graph switching with `/api/team-graph`.
- API responses are no-cache and server-side errors return JSON, so stale UI and silent failures are easier to diagnose.
- Dynamic activity/search content is HTML-escaped before rendering.
