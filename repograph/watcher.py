from __future__ import annotations

import time
from pathlib import Path

from .exporter import export_markdown
from .git_sync import GitSyncManager
from .util import iter_source_files, relpath


class PollingWatcher:
    def __init__(
        self,
        root: Path,
        analyzer,
        interval: float = 1.5,
        export_md: bool = True,
        git_sync: bool = False,
        git_interval: float = 60.0,
        remote: str = "origin",
        branch: str | None = None,
    ):
        self.root = Path(root).resolve()
        self.analyzer = analyzer
        self.interval = max(.5, interval)
        self.export_md = export_md
        self.snapshot = {}
        self.git_sync_enabled = git_sync
        self.git_interval = max(10.0, git_interval)
        self.git_manager = GitSyncManager(self.root, remote=remote, branch=branch) if git_sync else None
        self._last_git_sync = 0.0

    def take_snapshot(self):
        snap = {}
        for p in iter_source_files(self.root):
            try:
                s = p.stat()
                snap[relpath(p, self.root)] = (s.st_mtime_ns, s.st_size)
            except OSError:
                pass
        return snap

    def _sync_remote(self, force: bool = False):
        if not self.git_manager:
            return None
        now = time.monotonic()
        if not force and now - self._last_git_sync < self.git_interval:
            return None
        self._last_git_sync = now
        result = self.git_manager.sync(force=force)
        changed = result.get("changed_repositories", 0)
        errors = result.get("errors", [])
        if changed:
            print(f"Team graph updated from Git: {changed} remote repos changed")
        if errors:
            print(f"RepoGraph Git sync warnings: {len(errors)}")
        return result

    def run(self):
        self.analyzer.scan()
        self._sync_remote(force=False)
        if self.export_md:
            export_markdown(self.root, self.analyzer.store)
        self.snapshot = self.take_snapshot()
        git_msg = f", remote Git every {self.git_interval:.0f}s" if self.git_sync_enabled else ""
        print(f"RepoGraph watching {self.root} every {self.interval:.1f}s{git_msg} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(self.interval)
                new = self.take_snapshot()
                changed = [p for p, v in new.items() if self.snapshot.get(p) != v]
                removed = [p for p in self.snapshot if p not in new]
                dirty = False
                for rp in changed:
                    full = self.root / rp
                    if full.exists() and self.analyzer.index_file(full, force=True):
                        dirty = True
                for rp in removed:
                    if self.analyzer.remove_path(self.root / rp):
                        dirty = True
                if dirty:
                    self.analyzer.rebuild_cross_edges()
                    if self.export_md:
                        export_markdown(self.root, self.analyzer.store)
                    print(f"Updated local graph: ~{len(changed)} changed, {len(removed)} removed")
                sync = self._sync_remote(force=False)
                if sync and sync.get("changed_repositories") and self.export_md:
                    export_markdown(self.root, self.analyzer.store)
                self.snapshot = new
        except KeyboardInterrupt:
            print("RepoGraph watcher stopped")
