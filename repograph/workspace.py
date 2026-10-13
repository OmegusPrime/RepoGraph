from __future__ import annotations

from pathlib import Path

from .analyzer import RepositoryAnalyzer
from .store import GraphStore
from .util import discover_git_repositories, iter_source_files, relpath
from .git_sync import repo_key


class WorkspaceAnalyzer:
    """Index a directory containing one or more Git repositories without merging their namespaces."""

    def __init__(self, root: Path, store: GraphStore):
        self.root = Path(root).resolve()
        self.store = store
        self.repo_roots = discover_git_repositories(self.root)
        if not self.repo_roots:
            self.repo_roots = [self.root]
        self.analyzers = {
            repo_key(r, self.root): RepositoryAnalyzer(r, store, repo_name=repo_key(r, self.root))
            for r in self.repo_roots
        }
        if self.repo_roots != [self.root]:
            loose_key = f"{self.root.name}__workspace"
            self.analyzers[loose_key] = RepositoryAnalyzer(self.root, store, repo_name=loose_key, exclude_roots=self.repo_roots)

    @property
    def repo_name(self) -> str:
        return self.root.name

    def refresh(self) -> None:
        roots = discover_git_repositories(self.root) or [self.root]
        git_keys = {repo_key(r, self.root) for r in roots}
        desired = set(git_keys)
        for r in roots:
            key = repo_key(r, self.root)
            if key not in self.analyzers:
                self.analyzers[key] = RepositoryAnalyzer(r, self.store, repo_name=key)
        if roots != [self.root]:
            loose_key = f"{self.root.name}__workspace"
            desired.add(loose_key)
            self.analyzers[loose_key] = RepositoryAnalyzer(self.root, self.store, repo_name=loose_key, exclude_roots=roots)
        for key in list(self.analyzers):
            if key not in desired:
                self.store.remove_repo(key)
                del self.analyzers[key]
        self.repo_roots = roots

    def owner(self, full: Path) -> RepositoryAnalyzer | None:
        full = Path(full).resolve()
        candidates = []
        for analyzer in self.analyzers.values():
            try:
                full.relative_to(analyzer.root)
                candidates.append(analyzer)
            except ValueError:
                continue
        if not candidates:
            return None
        return max(candidates, key=lambda a: len(a.root.parts))

    def index_file(self, full: Path, force: bool = False) -> bool:
        analyzer = self.owner(full)
        return analyzer.index_file(full, force=force) if analyzer else False

    def remove_path(self, full: Path) -> bool:
        analyzer = self.owner(full)
        if not analyzer:
            return False
        try:
            rp = relpath(full, analyzer.root)
        except ValueError:
            return False
        analyzer.store.remove_file(analyzer.repo_name, rp)
        analyzer.store.log_event("delete", f"{analyzer.repo_name}:{rp}")
        return True

    def rebuild_cross_edges(self) -> None:
        for analyzer in self.analyzers.values():
            analyzer.rebuild_cross_edges()

    def scan(self, force: bool = False) -> dict:
        self.refresh()
        changed = removed = 0
        per_repo = []
        active = set(self.analyzers)
        for key, analyzer in self.analyzers.items():
            result = analyzer.scan(force=force)
            changed += result.get("changed", 0)
            removed += result.get("removed", 0)
            per_repo.append({"repo": key, "changed": result.get("changed", 0), "removed": result.get("removed", 0)})
        for repo in self.store.repositories():
            if repo not in active:
                self.store.remove_repo(repo)
        return {"changed": changed, "removed": removed, "repositories": per_repo, **self.store.stats()}
