from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from .analyzer import RepositoryAnalyzer
from .dashboard import serve
from .exporter import export_markdown
from .impact import impact
from .project import ensure_project
from .store import GraphStore
from .watcher import PollingWatcher


def setup(root: Path):
    root=Path(root).resolve(); ensure_project(root); store=GraphStore(root/".repograph"/"cache"/"graph.db"); analyzer=RepositoryAnalyzer(root,store);return root,store,analyzer

def main(argv=None):
    p=argparse.ArgumentParser(prog="repograph",description="Local-first repository knowledge graph and impact dashboard")
    sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("init");x.add_argument("path",nargs="?",default=".")
    x=sub.add_parser("scan");x.add_argument("path",nargs="?",default=".");x.add_argument("--force",action="store_true")
    x=sub.add_parser("watch");x.add_argument("path",nargs="?",default=".");x.add_argument("--interval",type=float,default=1.5);x.add_argument("--serve",action="store_true");x.add_argument("--port",type=int,default=9739)
    x=sub.add_parser("serve");x.add_argument("path",nargs="?",default=".");x.add_argument("--port",type=int,default=9739);x.add_argument("--no-open",action="store_true")
    x=sub.add_parser("impact");x.add_argument("target");x.add_argument("--path",default=".");x.add_argument("--depth",type=int,default=4)
    x=sub.add_parser("search");x.add_argument("query");x.add_argument("--path",default=".");x.add_argument("--limit",type=int,default=30)
    x=sub.add_parser("export-md");x.add_argument("path",nargs="?",default=".")
    x=sub.add_parser("stats");x.add_argument("path",nargs="?",default=".")
    a=p.parse_args(argv)
    if a.cmd in ("impact","search"): root=Path(a.path)
    else: root=Path(a.path)
    root,store,analyzer=setup(root)
    if a.cmd=="init":
        r=analyzer.scan(); out=export_markdown(root,store);print(json.dumps(r,indent=2));print(f"Graph markdown: {out}")
    elif a.cmd=="scan": print(json.dumps(analyzer.scan(force=a.force),indent=2))
    elif a.cmd=="watch":
        analyzer.scan();
        if a.serve:
            threading.Thread(target=serve,args=(root,store,"127.0.0.1",a.port,True),daemon=True).start()
        PollingWatcher(root,analyzer,a.interval).run()
    elif a.cmd=="serve": analyzer.scan();serve(root,store,port=a.port,open_browser=not a.no_open)
    elif a.cmd=="impact": print(json.dumps(impact(store,a.target,a.depth),indent=2,default=str))
    elif a.cmd=="search": print(json.dumps(store.search(a.query,a.limit),indent=2,default=str))
    elif a.cmd=="export-md": print(export_markdown(root,store))
    elif a.cmd=="stats": print(json.dumps(store.stats(),indent=2))

if __name__=="__main__": main()
