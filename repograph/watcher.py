from __future__ import annotations

import time
from pathlib import Path
from .analyzer import RepositoryAnalyzer
from .exporter import export_markdown
from .util import iter_source_files, relpath


class PollingWatcher:
    def __init__(self, root: Path, analyzer: RepositoryAnalyzer, interval: float=1.5, export_md: bool=True):
        self.root=Path(root).resolve(); self.analyzer=analyzer; self.interval=max(.5,interval); self.export_md=export_md
        self.snapshot={}

    def take_snapshot(self):
        snap={}
        for p in iter_source_files(self.root):
            try:
                s=p.stat(); snap[relpath(p,self.root)]=(s.st_mtime_ns,s.st_size)
            except OSError: pass
        return snap

    def run(self):
        self.analyzer.scan()
        if self.export_md: export_markdown(self.root,self.analyzer.store)
        self.snapshot=self.take_snapshot()
        print(f"RepoGraph watching {self.root} every {self.interval:.1f}s (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(self.interval)
                new=self.take_snapshot()
                changed=[p for p,v in new.items() if self.snapshot.get(p)!=v]
                removed=[p for p in self.snapshot if p not in new]
                dirty=False
                for rp in changed:
                    full=self.root/rp
                    if full.exists() and self.analyzer.index_file(full,force=True): dirty=True
                for rp in removed:
                    self.analyzer.store.remove_file(self.analyzer.repo_name,rp)
                    self.analyzer.store.log_event("delete",rp); dirty=True
                if dirty:
                    self.analyzer.rebuild_cross_edges()
                    if self.export_md: export_markdown(self.root,self.analyzer.store)
                    print(f"Updated graph: +~{len(changed)} changed, -{len(removed)} removed")
                self.snapshot=new
        except KeyboardInterrupt:
            print("RepoGraph watcher stopped")
