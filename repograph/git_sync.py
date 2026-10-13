from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .analyzer import RepositoryAnalyzer
from .store import GraphStore
from .util import discover_git_repositories, git_run, relpath


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "repo"


def repo_key(repo_root: Path, workspace_root: Path) -> str:
    repo_root = Path(repo_root).resolve()
    workspace_root = Path(workspace_root).resolve()
    try:
        rel = repo_root.relative_to(workspace_root).as_posix()
        return workspace_root.name if rel == "." else rel
    except ValueError:
        return repo_root.name


def _default_remote_branch(repo: Path, remote: str, configured: str | None = None) -> str:
    if configured:
        return configured
    current = git_run(repo, "branch", "--show-current")
    if current and git_run(repo, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{current}", check=False).returncode == 0:
        return current
    head = git_run(repo, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD")
    if head.startswith(remote + "/"):
        return head[len(remote) + 1 :]
    for candidate in ("main", "master"):
        if git_run(repo, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{candidate}", check=False).returncode == 0:
            return candidate
    return current or "main"


def git_repository_status(repo: Path, workspace_root: Path | None = None, remote: str = "origin", branch: str | None = None) -> dict:
    repo = Path(repo).resolve()
    workspace_root = Path(workspace_root or repo).resolve()
    local_branch = git_run(repo, "branch", "--show-current") or git_run(repo, "rev-parse", "--abbrev-ref", "HEAD")
    local_commit = git_run(repo, "rev-parse", "HEAD")
    remotes = [x for x in git_run(repo, "remote").splitlines() if x.strip()]
    selected_remote = remote if remote in remotes else (remotes[0] if remotes else "")
    remote_branch = _default_remote_branch(repo, selected_remote, branch) if selected_remote else ""
    remote_ref = f"{selected_remote}/{remote_branch}" if selected_remote and remote_branch else ""
    remote_commit = git_run(repo, "rev-parse", remote_ref) if remote_ref else ""
    status = git_run(repo, "status", "--porcelain=v1")
    changed = []
    for line in status.splitlines():
        if len(line) >= 4:
            changed.append({"status": line[:2].strip() or "?", "path": line[3:]})
    ahead = behind = 0
    if remote_ref and local_commit and remote_commit:
        counts = git_run(repo, "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}")
        try:
            ahead, behind = [int(x) for x in counts.split()[:2]]
        except Exception:
            pass
    return {
        "repo": repo_key(repo, workspace_root),
        "path": str(repo),
        "branch": local_branch,
        "commit": local_commit,
        "changed": changed,
        "remote": selected_remote,
        "remote_branch": remote_branch,
        "remote_ref": remote_ref,
        "remote_commit": remote_commit,
        "ahead": ahead,
        "behind": behind,
    }


def workspace_git_status(root: Path, remote: str = "origin", branch: str | None = None) -> dict:
    root = Path(root).resolve()
    repos = discover_git_repositories(root)
    return {
        "workspace": root.name,
        "repositories": [git_repository_status(r, root, remote, branch) for r in repos],
        "repository_count": len(repos),
    }


@dataclass
class SyncResult:
    repo: str
    remote_ref: str
    old_commit: str
    new_commit: str
    changed: bool
    files: list[dict]
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "repo": self.repo,
            "remote_ref": self.remote_ref,
            "old_commit": self.old_commit,
            "new_commit": self.new_commit,
            "changed": self.changed,
            "files": self.files,
            "error": self.error,
        }


class GitSyncManager:
    """Maintain an isolated team graph from remote Git refs without touching the user's worktree."""

    def __init__(
        self,
        workspace_root: Path,
        remote_store: GraphStore | None = None,
        remote: str = "origin",
        branch: str | None = None,
        fetch: bool = True,
    ):
        self.root = Path(workspace_root).resolve()
        self.remote = remote
        self.branch = branch
        self.fetch = fetch
        self.worktrees = self.root / ".repograph" / "worktrees"
        self.worktrees.mkdir(parents=True, exist_ok=True)
        self.store = remote_store or GraphStore(self.root / ".repograph" / "cache" / "team_graph.db")

    def _meta_key(self, key: str, repo: str) -> str:
        return f"git.{key}.{repo}"

    def _changed_files(self, repo: Path, old: str, new: str) -> list[dict]:
        if not old or not new or old == new:
            return []
        out = git_run(repo, "diff", "--name-status", old, new)
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if not parts:
                continue
            status = parts[0]
            if status.startswith("R") and len(parts) >= 3:
                rows.append({"status": status, "old_path": parts[1], "path": parts[2]})
            elif len(parts) >= 2:
                rows.append({"status": status, "path": parts[-1]})
        return rows

    def _ensure_worktree(self, repo_root: Path, key: str, remote_ref: str) -> Path:
        target = self.worktrees / _safe_name(key)
        git_file = target / ".git"
        if not target.exists() or not git_file.exists():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            p = git_run(repo_root, "worktree", "add", "--detach", "--force", str(target), remote_ref, check=False)
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f"Failed to create worktree for {key}")
        else:
            p = git_run(target, "reset", "--hard", remote_ref, check=False)
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f"Failed to update worktree for {key}")
            git_run(target, "clean", "-fd", check=False)
        return target

    def _purge_missing_repos(self, active: set[str]) -> None:
        for repo in self.store.repositories():
            if repo not in active:
                self.store.remove_repo(repo)

    def sync(self, force: bool = False) -> dict:
        repos = discover_git_repositories(self.root)
        active = set()
        results: list[dict] = []
        analyzers: list[RepositoryAnalyzer] = []
        for repo_root in repos:
            key = repo_key(repo_root, self.root)
            active.add(key)
            try:
                remotes = [x for x in git_run(repo_root, "remote").splitlines() if x.strip()]
                selected_remote = self.remote if self.remote in remotes else (remotes[0] if remotes else "")
                if not selected_remote:
                    results.append(SyncResult(key, "", "", "", False, [], "No Git remote configured").as_dict())
                    continue
                if self.fetch:
                    fetch_result = git_run(repo_root, "fetch", selected_remote, "--prune", "--quiet", check=False)
                    if fetch_result.returncode != 0:
                        raise RuntimeError(fetch_result.stderr.strip() or f"git fetch {selected_remote} failed")
                rb = _default_remote_branch(repo_root, selected_remote, self.branch)
                remote_ref = f"{selected_remote}/{rb}"
                new_sha = git_run(repo_root, "rev-parse", remote_ref)
                if not new_sha:
                    raise RuntimeError(f"Cannot resolve {remote_ref}")
                old_sha = self.store.get_meta(self._meta_key("remote_sha", key), "")
                files = self._changed_files(repo_root, old_sha, new_sha)
                changed = force or old_sha != new_sha or key not in self.store.repositories()
                if changed:
                    wt = self._ensure_worktree(repo_root, key, remote_ref)
                    analyzer = RepositoryAnalyzer(wt, self.store, repo_name=key)
                    analyzer.scan(force=force or not old_sha)
                    analyzers.append(analyzer)
                    self.store.set_meta(self._meta_key("remote_sha", key), new_sha)
                    self.store.set_meta(self._meta_key("remote_ref", key), remote_ref)
                    self.store.set_meta(self._meta_key("last_sync", key), str(int(time.time())))
                    self.store.log_event("git_remote_sync", key, {"old": old_sha, "new": new_sha, "remote_ref": remote_ref, "files": files[:200]})
                results.append(SyncResult(key, remote_ref, old_sha, new_sha, changed, files).as_dict())
            except Exception as exc:
                results.append(SyncResult(key, "", "", "", False, [], str(exc)).as_dict())
        self._purge_missing_repos(active)
        return {
            "workspace": self.root.name,
            "repositories": results,
            "changed_repositories": sum(1 for r in results if r.get("changed")),
            "errors": [r for r in results if r.get("error")],
            "stats": self.store.stats(),
        }

    def status(self) -> dict:
        repos = []
        for repo_root in discover_git_repositories(self.root):
            key = repo_key(repo_root, self.root)
            row = git_repository_status(repo_root, self.root, self.remote, self.branch)
            row["indexed_remote_commit"] = self.store.get_meta(self._meta_key("remote_sha", key), "")
            row["indexed_remote_ref"] = self.store.get_meta(self._meta_key("remote_ref", key), "")
            row["last_sync_epoch"] = self.store.get_meta(self._meta_key("last_sync", key), "")
            repos.append(row)
        return {"workspace": self.root.name, "repositories": repos, "team_graph": self.store.stats()}


def install_git_hooks(workspace_root: Path) -> dict:
    """Append lightweight hooks that request a fast local rescan. Existing hook content is preserved."""
    root = Path(workspace_root).resolve()
    results = []
    marker_start = "# >>> repograph hook >>>"
    marker_end = "# <<< repograph hook <<<"
    block = (
        f"\n{marker_start}\n"
        "# Keep RepoGraph's local graph fresh after Git changes.\n"
        f'python -m repograph.cli scan "{root.as_posix()}" >/dev/null 2>&1 || true\n'
        f"{marker_end}\n"
    )
    for repo in discover_git_repositories(root):
        hooks = Path(git_run(repo, "rev-parse", "--git-path", "hooks") or (repo / ".git" / "hooks"))
        if not hooks.is_absolute():
            hooks = repo / hooks
        hooks.mkdir(parents=True, exist_ok=True)
        for name in ("post-commit", "post-checkout", "post-merge", "post-rewrite", "post-applypatch"):
            path = hooks / name
            try:
                existing = path.read_text(encoding="utf-8") if path.exists() else "#!/bin/sh\n"
                if marker_start not in existing:
                    path.write_text(existing.rstrip() + "\n" + block, encoding="utf-8")
                    try:
                        os.chmod(path, path.stat().st_mode | 0o111)
                    except OSError:
                        pass
                results.append({"repo": repo_key(repo, root), "hook": name, "path": str(path), "installed": True})
            except OSError as exc:
                results.append({"repo": repo_key(repo, root), "hook": name, "path": str(path), "installed": False, "error": str(exc)})
    return {"hooks": results}
