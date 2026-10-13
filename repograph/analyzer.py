from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .store import GraphStore
from .util import iter_source_files, relpath, sha256_bytes, stable_id
from .maven import build_maven_graph

LANG_MAP = {
    ".py":"python", ".pyi":"python", ".js":"javascript", ".jsx":"javascript",
    ".ts":"typescript", ".tsx":"typescript", ".java":"java", ".kt":"kotlin", ".kts":"kotlin",
    ".go":"go", ".rs":"rust", ".c":"c", ".h":"c", ".cc":"cpp", ".cpp":"cpp", ".hpp":"cpp",
    ".cs":"csharp", ".php":"php", ".rb":"ruby", ".swift":"swift", ".scala":"scala", ".sql":"sql",
    ".vue":"vue", ".svelte":"svelte", ".yaml":"yaml", ".yml":"yaml", ".json":"json", ".toml":"toml",
}

DEF_PATTERNS = {
    "javascript": re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"),
    "typescript": re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|interface\s+([A-Za-z_$][\w$]*)|type\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"),
    "java": re.compile(r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|native)\s+)*(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)|^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|native)\s+)+[\w<>,.?\[\] ]+\s+([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(?:throws[^\{]+)?\{"),
    "kotlin": re.compile(r"^\s*(?:(?:data|sealed|open|abstract|internal|private|public|protected)\s+)*(?:class|interface|object)\s+([A-Za-z_]\w*)|^\s*(?:(?:suspend|private|public|internal|protected|override)\s+)*fun\s+([A-Za-z_]\w*)\s*\("),
    "go": re.compile(r"^\s*(?:type\s+([A-Za-z_]\w*)\s+(?:struct|interface)|func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\()"),
    "rust": re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:fn\s+([A-Za-z_]\w*)|struct\s+([A-Za-z_]\w*)|enum\s+([A-Za-z_]\w*)|trait\s+([A-Za-z_]\w*))"),
    "c": re.compile(r"^\s*[A-Za-z_][\w\s\*]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{"),
    "cpp": re.compile(r"^\s*(?:template\s*<[^>]+>\s*)?(?:class|struct)\s+([A-Za-z_]\w*)|^\s*[\w:<>,~*&\s]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:const\s*)?\{"),
    "csharp": re.compile(r"^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|async|virtual|override)\s+)*(?:class|interface|record|struct|enum)\s+([A-Za-z_]\w*)|^\s*(?:(?:public|private|protected|internal|static|async|virtual|override)\s+)+[\w<>,.?\[\] ]+\s+([A-Za-z_]\w*)\s*\("),
}

IMPORT_PATTERNS = {
    "python": re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))"),
    "javascript": re.compile(r"(?:import\s+.*?\s+from\s+|require\s*\()\s*['\"]([^'\"]+)"),
    "typescript": re.compile(r"(?:import\s+.*?\s+from\s+|require\s*\()\s*['\"]([^'\"]+)"),
    "java": re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)"),
    "kotlin": re.compile(r"^\s*import\s+([\w.]+)"),
    "go": re.compile(r"^\s*import\s+(?:\w+\s+)?[\"`]([^\"`]+)[\"`]"),
    "rust": re.compile(r"^\s*use\s+([^;]+)"),
}

CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
CALL_BLACKLIST = {"if","for","while","switch","catch","return","sizeof","typeof","new","super","this","print","println"}


@dataclass
class ParsedFile:
    nodes: list[dict]
    edges: list[dict]
    imports: list[tuple[str, str]]  # (source node id, module text)
    calls: list[tuple[str, str]]    # (source node id, callee name)


class RepositoryAnalyzer:
    def __init__(self, root: Path, store: GraphStore, repo_name: str | None = None, exclude_roots: list[Path] | None = None):
        self.root = Path(root).resolve()
        self.store = store
        self.repo_name = repo_name or self.root.name
        self.exclude_roots = [Path(p).resolve() for p in (exclude_roots or [])]

    def source_files(self):
        for full in iter_source_files(self.root):
            resolved = full.resolve()
            excluded = False
            for ex in self.exclude_roots:
                try:
                    resolved.relative_to(ex)
                    excluded = True
                    break
                except ValueError:
                    pass
            if not excluded:
                yield full

    def language(self, path: Path) -> str:
        return LANG_MAP.get(path.suffix.lower(), "text")

    def parse_python(self, path: str, text: str, content_hash: str) -> ParsedFile:
        lang = "python"
        file_id = stable_id(self.repo_name, path, "file")
        nodes = [{"id":file_id,"kind":"file","name":Path(path).name,"line":1,"lang":lang,"content_hash":content_hash}]
        edges=[]; imports=[]; calls=[]
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ParsedFile(nodes,edges,imports,calls)

        symbol_stack=[file_id]
        class Visitor(ast.NodeVisitor):
            def visit_ClassDef(v, node):
                nid=stable_id(self.repo_name,path,"class",node.name,str(node.lineno))
                nodes.append({"id":nid,"kind":"class","name":node.name,"line":node.lineno,"lang":lang,"signature":f"class {node.name}","content_hash":content_hash})
                edges.append({"src":symbol_stack[-1],"dst":nid,"kind":"CONTAINS"})
                symbol_stack.append(nid); v.generic_visit(node); symbol_stack.pop()
            def _func(v, node, is_async=False):
                kind="method" if symbol_stack[-1] != file_id and next((n for n in nodes if n["id"]==symbol_stack[-1] and n["kind"]=="class"),None) else "function"
                args=[]
                for a in list(node.args.posonlyargs)+list(node.args.args): args.append(a.arg)
                sig=f"{'async ' if is_async else ''}def {node.name}({', '.join(args)})"
                nid=stable_id(self.repo_name,path,kind,node.name,str(node.lineno))
                nodes.append({"id":nid,"kind":kind,"name":node.name,"line":node.lineno,"lang":lang,"signature":sig,"content_hash":content_hash})
                edges.append({"src":symbol_stack[-1],"dst":nid,"kind":"CONTAINS"})
                symbol_stack.append(nid); v.generic_visit(node); symbol_stack.pop()
            def visit_FunctionDef(v,node): v._func(node,False)
            def visit_AsyncFunctionDef(v,node): v._func(node,True)
            def visit_Import(v,node):
                for a in node.names: imports.append((symbol_stack[-1],a.name))
            def visit_ImportFrom(v,node):
                if node.module: imports.append((symbol_stack[-1],node.module))
            def visit_Call(v,node):
                name=None
                if isinstance(node.func,ast.Name): name=node.func.id
                elif isinstance(node.func,ast.Attribute): name=node.func.attr
                if name and name not in CALL_BLACKLIST: calls.append((symbol_stack[-1],name))
                v.generic_visit(node)
        Visitor().visit(tree)
        return ParsedFile(nodes,edges,imports,calls)

    def parse_generic(self, path: str, text: str, content_hash: str, lang: str) -> ParsedFile:
        """Best-effort parser for non-Python languages.

        Imports are always attributed to the file. Calls are attributed to the active
        brace-delimited symbol where we can determine one; otherwise to the file. This
        avoids the old bug where `current` stayed stuck on the last definition and
        incorrectly attached the remainder of a source file to that symbol.
        """
        file_id=stable_id(self.repo_name,path,"file")
        nodes=[{"id":file_id,"kind":"file","name":Path(path).name,"line":1,"lang":lang,"content_hash":content_hash}]
        edges=[]; imports=[]; calls=[]
        pattern=DEF_PATTERNS.get(lang)
        brace_lang=lang in {"javascript","typescript","java","kotlin","go","rust","c","cpp","csharp"}
        stack=[]  # (symbol id, brace depth where body began)
        brace_depth=0
        for lineno,line in enumerate(text.splitlines(),1):
            # Pop completed definitions before attributing this line.
            if brace_lang:
                while stack and brace_depth < stack[-1][1]: stack.pop()
            active=stack[-1][0] if stack else file_id
            found_id=None
            if pattern:
                m=pattern.search(line)
                if m:
                    name=next((g for g in m.groups() if g),None)
                    if name:
                        lowered=line.lower()
                        kind="class" if any(k in lowered for k in ("class ","interface ","struct ","enum ","record ","trait ","type ")) else "function"
                        nid=stable_id(self.repo_name,path,kind,name,str(lineno))
                        nodes.append({"id":nid,"kind":kind,"name":name,"line":lineno,"lang":lang,"signature":line.strip()[:500],"content_hash":content_hash})
                        edges.append({"src":file_id,"dst":nid,"kind":"CONTAINS"})
                        found_id=nid
                        active=nid
            ip=IMPORT_PATTERNS.get(lang)
            if ip:
                im=ip.search(line)
                if im:
                    module=next((g for g in im.groups() if g),None)
                    if module: imports.append((file_id,module))
            # Ignore the declaration token itself as a call where possible.
            declared = next((n["name"] for n in reversed(nodes[-2:]) if n["line"]==lineno and n["kind"] in ("function","class")), None)
            for c in CALL_RE.findall(line):
                if c not in CALL_BLACKLIST and c != declared:
                    calls.append((active,c))
            if brace_lang:
                opens=line.count("{"); closes=line.count("}")
                # If a new definition opens a body on this line, remember its body depth.
                if found_id and opens>0:
                    stack.append((found_id, brace_depth+1))
                brace_depth += opens-closes
                while stack and brace_depth < stack[-1][1]: stack.pop()
        return ParsedFile(nodes,edges,imports,calls)

    def parse_file(self, full: Path) -> tuple[ParsedFile, str, int, int]:
        data=full.read_bytes()
        digest=sha256_bytes(data)
        stat=full.stat()
        text=data.decode("utf-8",errors="replace")
        rp=relpath(full,self.root)
        lang=self.language(full)
        parsed=self.parse_python(rp,text,digest) if lang=="python" else self.parse_generic(rp,text,digest,lang)
        return parsed,digest,stat.st_mtime_ns,stat.st_size

    def index_file(self, full: Path, force: bool=False) -> bool:
        rp=relpath(full,self.root)
        try:
            parsed,digest,mtime,size=self.parse_file(full)
        except (OSError,UnicodeError):
            return False
        state=self.store.file_state(self.repo_name,rp)
        if not force and state and state["sha256"]==digest:
            return False
        self.store.replace_file_graph(self.repo_name,rp,parsed.nodes,parsed.edges)
        self.store.upsert_file(self.repo_name,rp,digest,mtime,size)
        self.store.log_event("index",rp,{"nodes":len(parsed.nodes),"edges":len(parsed.edges)})
        # deferred refs survive graph replacement through ephemeral metadata node-free tables? we resolve immediately after batch instead.
        return True

    def rebuild_cross_edges(self) -> None:
        # Re-read files cheaply to resolve imports and calls against stable definitions.
        self.store.clear_edge_kind_for_repo("CALLS", self.repo_name)
        self.store.clear_edge_kind_for_repo("IMPORTS", self.repo_name)
        with self.store.connect() as con:
            nodes=[dict(n) for n in con.execute("SELECT * FROM nodes WHERE repo=? ORDER BY path,line", (self.repo_name,)).fetchall()]
        by_name={}; file_nodes={}; local_by_path={}
        for n in nodes:
            by_name.setdefault(n["name"],[]).append(n)
            local_by_path.setdefault(n["path"],[]).append(n)
            if n["kind"]=="file": file_nodes[n["path"]]=n
        edges=[]; edge_keys=set()
        for full in self.source_files():
            rp=relpath(full,self.root)
            try:
                text=full.read_text(encoding="utf-8",errors="replace")
                lang=self.language(full)
                ch=self.store.file_state(self.repo_name,rp)
                digest=ch["sha256"] if ch else ""
                parsed=self.parse_python(rp,text,digest) if lang=="python" else self.parse_generic(rp,text,digest,lang)
            except OSError:
                continue
            # symbols in this file by name and approximate source mapping
            local=local_by_path.get(rp, [])
            local_ids={n["id"] for n in local}
            default_src=next((n["id"] for n in local if n["kind"]=="file"),None)
            for src,name in parsed.calls:
                candidates=[n for n in by_name.get(name,[]) if n["kind"] in ("function","method") and n["repo"] == self.repo_name]
                if candidates:
                    # Never resolve an unqualified call across repository boundaries.
                    candidates.sort(key=lambda n:(n["path"]!=rp,n["path"],n["line"]))
                    edge={"src":src if src in local_ids else default_src,"dst":candidates[0]["id"],"kind":"CALLS"}
                    key=(edge["src"],edge["dst"],edge["kind"])
                    if key not in edge_keys: edge_keys.add(key); edges.append(edge)
            for src,module in parsed.imports:
                mod_tail=module.split(".")[-1]
                targets=[]
                for p,fn in file_nodes.items():
                    stem=Path(p).stem
                    if stem==mod_tail or p.replace("/",".").removesuffix(Path(p).suffix).endswith(module):
                        targets.append(fn)
                if targets:
                    targets.sort(key=lambda n:n["path"])
                    edge={"src":src if src in local_ids else default_src,"dst":targets[0]["id"],"kind":"IMPORTS"}
                    key=(edge["src"],edge["dst"],edge["kind"])
                    if key not in edge_keys: edge_keys.add(key); edges.append(edge)
        self.store.add_edges(e for e in edges if e.get("src") and e.get("dst") and e["src"]!=e["dst"])
        self.rebuild_maven_graph()

    def rebuild_maven_graph(self) -> None:
        with self.store.connect() as con:
            existing_nodes = [
                dict(node)
                for node in con.execute(
                    "SELECT * FROM nodes WHERE repo=? AND kind<>'maven_module' ORDER BY path,line",
                    (self.repo_name,),
                ).fetchall()
            ]
        nodes, edges = build_maven_graph(self.root, self.repo_name, existing_nodes)
        self.store.replace_repo_nodes_by_kind(self.repo_name, "maven_module", nodes, edges)

    def scan(self, force: bool=False) -> dict:
        changed=0; seen=set()
        for full in self.source_files():
            rp=relpath(full,self.root); seen.add(rp)
            if self.index_file(full,force=force): changed+=1
        with self.store.connect() as con:
            known=[r[0] for r in con.execute("SELECT path FROM files WHERE repo=?",(self.repo_name,)).fetchall()]
        removed=0
        for p in known:
            if p not in seen:
                self.store.remove_file(self.repo_name,p); self.store.log_event("delete",p); removed+=1
        if changed or removed or force:
            self.rebuild_cross_edges()
        else:
            # Populate newly introduced derived graph kinds when an existing
            # database is opened after an upgrade, even if no file changed.
            self.rebuild_maven_graph()
        return {"changed":changed,"removed":removed,**self.store.stats()}
