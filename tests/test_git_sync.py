import subprocess
import tempfile
import unittest
from pathlib import Path

from repograph.git_sync import GitSyncManager
from repograph.store import GraphStore
from repograph.workspace import WorkspaceAnalyzer


def run(cwd, *args):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


class GitSyncTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.base = Path(self.t.name)
        self.origin = self.base / "origin.git"
        run(self.base, "git", "init", "--bare", str(self.origin))
        self.a = self.base / "dev-a"
        self.b = self.base / "dev-b"
        run(self.base, "git", "clone", str(self.origin), str(self.a))
        for repo in (self.a,):
            run(repo, "git", "config", "user.email", "test@example.com")
            run(repo, "git", "config", "user.name", "RepoGraph Test")
        (self.a / "service.py").write_text("def alpha():\n    return 1\n")
        run(self.a, "git", "add", ".")
        run(self.a, "git", "commit", "-m", "initial")
        run(self.a, "git", "branch", "-M", "main")
        run(self.a, "git", "push", "-u", "origin", "main")
        # Ensure bare HEAD points to main so fresh clones discover it.
        run(self.origin, "git", "symbolic-ref", "HEAD", "refs/heads/main")
        run(self.base, "git", "clone", str(self.origin), str(self.b))
        run(self.b, "git", "config", "user.email", "test@example.com")
        run(self.b, "git", "config", "user.name", "RepoGraph Test")

    def tearDown(self):
        self.t.cleanup()

    def test_remote_push_updates_team_graph_without_touching_worktree(self):
        store = GraphStore(self.b / ".repograph" / "cache" / "team_graph.db")
        mgr = GitSyncManager(self.b, store)
        first = mgr.sync()
        self.assertEqual(first["errors"], [])
        self.assertTrue(store.search("alpha"))

        local_before = (self.b / "service.py").read_text()
        (self.a / "service.py").write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n")
        run(self.a, "git", "add", "service.py")
        run(self.a, "git", "commit", "-m", "add beta")
        run(self.a, "git", "push")

        second = mgr.sync()
        self.assertEqual(second["errors"], [])
        self.assertEqual(second["changed_repositories"], 1)
        self.assertTrue(store.search("beta"))
        # Remote indexing must never auto-pull/overwrite the user's local checkout.
        self.assertEqual((self.b / "service.py").read_text(), local_before)
        self.assertNotIn("beta", local_before)

    def test_workspace_keeps_repo_namespaces_separate(self):
        workspace = self.base / "workspace"
        workspace.mkdir()
        r1 = workspace / "r1"; r2 = workspace / "r2"
        for r in (r1, r2):
            run(workspace, "git", "init", str(r))
            run(r, "git", "config", "user.email", "test@example.com")
            run(r, "git", "config", "user.name", "RepoGraph Test")
        (r1 / "a.py").write_text("def get():\n    return 1\n\ndef only_one():\n    return get()\n")
        (r2 / "b.py").write_text("def get():\n    return 2\n\ndef only_two():\n    return get()\n")
        store = GraphStore(workspace / ".repograph" / "cache" / "graph.db")
        wa = WorkspaceAnalyzer(workspace, store)
        wa.scan(force=True)
        gets = [n for n in store.search("get", 20) if n["name"] == "get"]
        self.assertEqual({n["repo"] for n in gets}, {"r1", "r2"})
        one = next(n for n in store.search("only_one") if n["name"] == "only_one")
        out = store.neighbors(one["id"], "out")
        called_gets = [n for n in out if n["edge_kind"] == "CALLS" and n["name"] == "get"]
        self.assertTrue(called_gets)
        self.assertTrue(all(n["repo"] == "r1" for n in called_gets))


if __name__ == "__main__":
    unittest.main()
