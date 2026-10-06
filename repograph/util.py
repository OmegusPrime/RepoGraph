from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

SKIP_DIRS = {
    ".git", ".repograph", ".idea", ".vscode", "node_modules", "dist", "build",
    "target", ".next", ".nuxt", ".venv", "venv", "__pycache__", ".pytest_cache",
    "coverage", ".coverage", "vendor", "Pods", ".gradle", ".mvn"
}

SOURCE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".kts",
    ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".php", ".rb",
    ".swift", ".scala", ".sql", ".sh", ".bash", ".ps1", ".vue", ".svelte",
    ".yaml", ".yml", ".json", ".toml", ".xml", ".gradle"
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha1(payload).hexdigest()[:24]


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def iter_source_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        b = Path(base)
        for name in files:
            p = b / name
            if p.suffix.lower() in SOURCE_EXTS or name in {"Dockerfile", "Makefile"}:
                try:
                    if p.stat().st_size <= 4 * 1024 * 1024:
                        yield p
                except OSError:
                    continue


def git_info(root: Path) -> dict:
    def run(*args: str) -> str:
        try:
            return subprocess.check_output(
                ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, text=True,
                timeout=5,
            ).strip()
        except Exception:
            return ""

    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain=v1")
    changed = []
    for line in status.splitlines():
        if len(line) >= 4:
            changed.append({"status": line[:2].strip() or "?", "path": line[3:]})
    return {"branch": branch, "commit": commit, "changed": changed}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
