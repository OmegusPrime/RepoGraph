from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from .dashboard import serve
from .exporter import export_markdown
from .git_sync import GitSyncManager, install_git_hooks
from .impact import impact
from .whatif import proposed_change_impact
from .quality import collect_quality
from .project import ensure_project
from .store import GraphStore
from .watcher import PollingWatcher
from .workspace import WorkspaceAnalyzer


def setup(root: Path):
    root = Path(root).resolve()
    cfg = ensure_project(root)
    store = GraphStore(root / ".repograph" / "cache" / "graph.db")
    analyzer = WorkspaceAnalyzer(root, store)
    return root, store, analyzer, cfg


def main(argv=None):
    p = argparse.ArgumentParser(prog="repograph", description="Local-first repository knowledge graph, Git team sync, and impact dashboard")
    sub = p.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("init"); x.add_argument("path", nargs="?", default="."); x.add_argument("--git-sync", action="store_true"); x.add_argument("--install-hooks", action="store_true")
    x = sub.add_parser("scan"); x.add_argument("path", nargs="?", default="."); x.add_argument("--force", action="store_true")
    x = sub.add_parser("watch"); x.add_argument("path", nargs="?", default="."); x.add_argument("--interval", type=float, default=1.5); x.add_argument("--serve", action="store_true"); x.add_argument("--port", type=int, default=9739); x.add_argument("--git", action="store_true"); x.add_argument("--git-interval", type=float, default=60); x.add_argument("--remote", default="origin"); x.add_argument("--branch", default=None)
    x = sub.add_parser("serve"); x.add_argument("path", nargs="?", default="."); x.add_argument("--port", type=int, default=9739); x.add_argument("--no-open", action="store_true")
    x = sub.add_parser("impact"); x.add_argument("target"); x.add_argument("--path", default="."); x.add_argument("--depth", type=int, default=4); x.add_argument("--team", action="store_true")
    x = sub.add_parser("search"); x.add_argument("query"); x.add_argument("--path", default="."); x.add_argument("--limit", type=int, default=30); x.add_argument("--team", action="store_true")
    x = sub.add_parser("export-md"); x.add_argument("path", nargs="?", default=".")
    x = sub.add_parser("stats"); x.add_argument("path", nargs="?", default=".")
    x = sub.add_parser("git-sync"); x.add_argument("path", nargs="?", default="."); x.add_argument("--force", action="store_true"); x.add_argument("--remote", default="origin"); x.add_argument("--branch", default=None)
    x = sub.add_parser("git-status"); x.add_argument("path", nargs="?", default="."); x.add_argument("--remote", default="origin"); x.add_argument("--branch", default=None)
    x = sub.add_parser("install-hooks"); x.add_argument("path", nargs="?", default=".")
    x = sub.add_parser("what-if"); x.add_argument("proposal"); x.add_argument("--path", default="."); x.add_argument("--depth", type=int, default=4); x.add_argument("--team", action="store_true")
    x = sub.add_parser("quality"); x.add_argument("path", nargs="?", default=".")
    a = p.parse_args(argv)
    root = Path(a.path)
    root, store, analyzer, cfg = setup(root)
    team_store = GraphStore(root / ".repograph" / "cache" / "team_graph.db")

    if a.cmd == "init":
        r = analyzer.scan()
        sync = GitSyncManager(root, team_store).sync() if a.git_sync else None
        hooks = install_git_hooks(root) if a.install_hooks else None
        out = export_markdown(root, store)
        print(json.dumps({"local": r, "git_sync": sync, "hooks": hooks}, indent=2, default=str))
        print(f"Graph markdown: {out}")
    elif a.cmd == "scan":
        print(json.dumps(analyzer.scan(force=a.force), indent=2))
    elif a.cmd == "watch":
        analyzer.scan()
        if a.serve:
            threading.Thread(target=serve, args=(root, store, "127.0.0.1", a.port, True), daemon=True).start()
        PollingWatcher(root, analyzer, a.interval, git_sync=a.git, git_interval=a.git_interval, remote=a.remote, branch=a.branch).run()
    elif a.cmd == "serve":
        analyzer.scan(); serve(root, store, port=a.port, open_browser=not a.no_open)
    elif a.cmd == "impact":
        chosen = team_store if a.team else store
        print(json.dumps(impact(chosen, a.target, a.depth), indent=2, default=str))
    elif a.cmd == "search":
        chosen = team_store if a.team else store
        print(json.dumps(chosen.search(a.query, a.limit), indent=2, default=str))
    elif a.cmd == "export-md":
        print(export_markdown(root, store))
    elif a.cmd == "stats":
        print(json.dumps({"local": store.stats(), "team": team_store.stats(), "repositories": store.repo_stats()}, indent=2))
    elif a.cmd == "git-sync":
        print(json.dumps(GitSyncManager(root, team_store, remote=a.remote, branch=a.branch).sync(force=a.force), indent=2, default=str))
        export_markdown(root, store)
    elif a.cmd == "git-status":
        print(json.dumps(GitSyncManager(root, team_store, remote=a.remote, branch=a.branch).status(), indent=2, default=str))
    elif a.cmd == "install-hooks":
        print(json.dumps(install_git_hooks(root), indent=2))
    elif a.cmd == "what-if":
        chosen = team_store if a.team else store
        print(json.dumps(proposed_change_impact(chosen, a.proposal, a.depth), indent=2, default=str))
    elif a.cmd == "quality":
        print(json.dumps(collect_quality(root), indent=2, default=str))


if __name__ == "__main__":
    main()
