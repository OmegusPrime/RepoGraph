from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    line INTEGER NOT NULL DEFAULT 1,
    lang TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    kind TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (src, dst, kind)
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE TABLE IF NOT EXISTS files (
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    PRIMARY KEY (repo, path)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class GraphStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db_path, timeout=20)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def get_meta(self, key: str, default: str = "") -> str:
        with self.connect() as con:
            row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def upsert_file(self, repo: str, path: str, sha256: str, mtime_ns: int, size: int) -> None:
        with self.connect() as con:
            con.execute("""INSERT INTO files(repo,path,sha256,mtime_ns,size) VALUES(?,?,?,?,?)
                         ON CONFLICT(repo,path) DO UPDATE SET sha256=excluded.sha256,mtime_ns=excluded.mtime_ns,size=excluded.size""",
                        (repo, path, sha256, mtime_ns, size))

    def file_state(self, repo: str, path: str):
        with self.connect() as con:
            return con.execute("SELECT * FROM files WHERE repo=? AND path=?", (repo, path)).fetchone()

    def remove_file(self, repo: str, path: str) -> None:
        with self.connect() as con:
            ids = [r[0] for r in con.execute("SELECT id FROM nodes WHERE repo=? AND path=?", (repo, path)).fetchall()]
            if ids:
                marks = ",".join("?" for _ in ids)
                con.execute(f"DELETE FROM edges WHERE src IN ({marks}) OR dst IN ({marks})", (*ids, *ids))
                con.execute(f"DELETE FROM nodes WHERE id IN ({marks})", ids)
            con.execute("DELETE FROM files WHERE repo=? AND path=?", (repo, path))

    def replace_file_graph(self, repo: str, path: str, nodes: list[dict], edges: list[dict]) -> None:
        with self.connect() as con:
            old = [r[0] for r in con.execute("SELECT id FROM nodes WHERE repo=? AND path=?", (repo, path)).fetchall()]
            if old:
                marks = ",".join("?" for _ in old)
                con.execute(f"DELETE FROM edges WHERE src IN ({marks}) OR dst IN ({marks})", (*old, *old))
                con.execute(f"DELETE FROM nodes WHERE id IN ({marks})", old)
            for n in nodes:
                con.execute("""INSERT OR REPLACE INTO nodes
                    (id,repo,kind,name,path,line,lang,signature,content_hash,metadata_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (n["id"], repo, n["kind"], n["name"], path, n.get("line",1), n.get("lang",""),
                     n.get("signature",""), n.get("content_hash",""), json.dumps(n.get("metadata",{}), sort_keys=True)))
            for e in edges:
                con.execute("INSERT OR REPLACE INTO edges(src,dst,kind,weight,metadata_json) VALUES(?,?,?,?,?)",
                            (e["src"], e["dst"], e["kind"], e.get("weight",1.0), json.dumps(e.get("metadata",{}), sort_keys=True)))

    def add_edges(self, edges: Iterable[dict]) -> None:
        with self.connect() as con:
            for e in edges:
                con.execute("INSERT OR REPLACE INTO edges(src,dst,kind,weight,metadata_json) VALUES(?,?,?,?,?)",
                            (e["src"], e["dst"], e["kind"], e.get("weight",1.0), json.dumps(e.get("metadata",{}), sort_keys=True)))

    def clear_edge_kind(self, kind: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM edges WHERE kind=?", (kind,))

    def log_event(self, event_type: str, path: str, details: dict | None = None) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO events(event_type,path,details_json) VALUES(?,?,?)", (event_type, path, json.dumps(details or {})))

    def stats(self) -> dict:
        with self.connect() as con:
            nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            files = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            kinds = {r[0]: r[1] for r in con.execute("SELECT kind,COUNT(*) FROM nodes GROUP BY kind ORDER BY COUNT(*) DESC")}
            edge_kinds = {r[0]: r[1] for r in con.execute("SELECT kind,COUNT(*) FROM edges GROUP BY kind ORDER BY COUNT(*) DESC")}
        return {"nodes": nodes, "edges": edges, "files": files, "node_kinds": kinds, "edge_kinds": edge_kinds}

    def search(self, query: str, limit: int = 30) -> list[dict]:
        q = f"%{query}%"
        with self.connect() as con:
            rows = con.execute("""SELECT * FROM nodes WHERE name LIKE ? OR path LIKE ? OR signature LIKE ?
                                  ORDER BY CASE WHEN name=? THEN 0 WHEN name LIKE ? THEN 1 ELSE 2 END, kind, path, line LIMIT ?""",
                               (q,q,q,query,f"{query}%",limit)).fetchall()
        return [dict(r) for r in rows]

    def node(self, node_id: str):
        with self.connect() as con:
            r = con.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return dict(r) if r else None

    def resolve(self, target: str) -> list[dict]:
        with self.connect() as con:
            exact = con.execute("SELECT * FROM nodes WHERE id=? OR name=? OR path=? ORDER BY kind", (target,target,target)).fetchall()
        if exact:
            return [dict(r) for r in exact]
        return self.search(target, limit=10)

    def neighbors(self, node_id: str, direction: str = "both") -> list[dict]:
        sql = []
        params = []
        if direction in ("out", "both"):
            sql.append("SELECT e.src,e.dst,e.kind AS edge_kind,e.weight,n.id AS id,n.repo AS repo,n.kind AS node_kind,n.name AS name,n.path AS path,n.line AS line,n.lang AS lang,n.signature AS signature,n.content_hash AS content_hash,n.metadata_json AS metadata_json FROM edges e JOIN nodes n ON n.id=e.dst WHERE e.src=?")
            params.append(node_id)
        if direction in ("in", "both"):
            sql.append("SELECT e.src,e.dst,e.kind AS edge_kind,e.weight,n.id AS id,n.repo AS repo,n.kind AS node_kind,n.name AS name,n.path AS path,n.line AS line,n.lang AS lang,n.signature AS signature,n.content_hash AS content_hash,n.metadata_json AS metadata_json FROM edges e JOIN nodes n ON n.id=e.src WHERE e.dst=?")
            params.append(node_id)
        if not sql:
            return []
        with self.connect() as con:
            rows = con.execute(" UNION ALL ".join(sql), params).fetchall()
        return [dict(r) for r in rows]

    def graph_slice(self, limit: int = 250) -> dict:
        with self.connect() as con:
            nodes = [dict(r) for r in con.execute("SELECT * FROM nodes ORDER BY kind,path,line LIMIT ?", (limit,)).fetchall()]
            ids = {n["id"] for n in nodes}
            if ids:
                marks = ",".join("?" for _ in ids)
                edges = [dict(r) for r in con.execute(f"SELECT * FROM edges WHERE src IN ({marks}) AND dst IN ({marks}) LIMIT ?", (*ids, *ids, limit*3)).fetchall()]
            else:
                edges=[]
        return {"nodes": nodes, "edges": edges}

    def all_nodes(self) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM nodes ORDER BY repo,path,line,kind,name").fetchall()]

    def all_edges(self) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM edges ORDER BY kind,src,dst").fetchall()]

    def recent_events(self, limit: int = 100) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
