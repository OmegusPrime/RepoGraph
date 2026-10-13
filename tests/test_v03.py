import json
import sys
import tempfile
import unittest
from pathlib import Path

from repograph.analyzer import RepositoryAnalyzer
from repograph.project import ensure_project
from repograph.quality import collect_quality
from repograph.store import GraphStore
from repograph.whatif import proposed_change_impact


class V03Tests(unittest.TestCase):
    def test_generic_symbol_attribution_does_not_stick_to_previous_function(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'app.js').write_text('function alpha() {\n  helper();\n}\n\nfunction beta() {\n  other();\n}\n', encoding='utf-8')
            store=GraphStore(root/'.repograph/cache/graph.db')
            a=RepositoryAnalyzer(root,store)
            a.scan(force=True)
            alpha=next(n for n in store.search('alpha') if n['name']=='alpha')
            beta=next(n for n in store.search('beta') if n['name']=='beta')
            aout=[n['name'] for n in store.neighbors(alpha['id'],'out') if n['edge_kind']=='CALLS']
            bout=[n['name'] for n in store.neighbors(beta['id'],'out') if n['edge_kind']=='CALLS']
            # unresolved helper/other do not create edges, but beta must be a distinct node and not nested in alpha
            self.assertNotEqual(alpha['id'],beta['id'])
            contains=[n for n in store.neighbors(alpha['id'],'out') if n['edge_kind']=='CONTAINS']
            self.assertFalse(any(n['name']=='beta' for n in contains))

    def test_what_if_simulates_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            f=root/'auth.py'; f.write_text('def validate_token():\n    return True\n\ndef login():\n    return validate_token()\n', encoding='utf-8')
            before=f.read_text()
            store=GraphStore(root/'.repograph/cache/graph.db'); RepositoryAnalyzer(root,store).scan(force=True)
            r=proposed_change_impact(store,'change validate_token authentication behavior')
            self.assertFalse(r['source_modified'])
            self.assertTrue(r['matched'])
            self.assertEqual(f.read_text(),before)

    def test_coverage_xml_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'coverage.xml').write_text('<coverage line-rate="0.83"></coverage>',encoding='utf-8')
            q=collect_quality(root)
            self.assertEqual(q['coverage'],83.0)
            self.assertIn('coverage.xml',q['sources'])

    def test_mcp_config_uses_current_python(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ensure_project(root)
            m=json.loads((root/'.mcp.json').read_text())
            self.assertEqual(Path(m['mcpServers']['repograph']['command']).resolve(),Path(sys.executable).resolve())
            self.assertEqual(Path(m['mcpServers']['repograph']['env']['REPOGRAPH_ROOT']).resolve(),root.resolve())
            self.assertNotIn('${workspaceFolder}',m['mcpServers']['repograph']['env']['REPOGRAPH_ROOT'])

    def test_repo_scoped_search(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); store=GraphStore(root/'g.db')
            store.replace_file_graph('a','x.py',[{'id':'1','kind':'file','name':'x.py','line':1},{'id':'2','kind':'function','name':'get','line':2}],[])
            store.replace_file_graph('b','y.py',[{'id':'3','kind':'file','name':'y.py','line':1},{'id':'4','kind':'function','name':'get','line':2}],[])
            self.assertEqual({x['repo'] for x in store.search('get',repo='a')},{'a'})

if __name__=='__main__': unittest.main()


class SqliteScaleRegressionTests(unittest.TestCase):
    def test_remove_repo_does_not_expand_node_ids_into_sql_variables(self):
        """Regression for v0.3.0: large repos exceeded SQLite variable limits."""
        from unittest.mock import patch
        import sqlite3
        import repograph.store as store_module

        real_connect = sqlite3.connect

        def limited_connect(*args, **kwargs):
            con = real_connect(*args, **kwargs)
            # Force a low limit so the old implementation (2 placeholders per
            # node id) fails with a small, fast fixture.
            if hasattr(con, "setlimit") and hasattr(sqlite3, "SQLITE_LIMIT_VARIABLE_NUMBER"):
                con.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 100)
            return con

        with tempfile.TemporaryDirectory() as td, patch.object(store_module.sqlite3, "connect", side_effect=limited_connect):
            root = Path(td)
            store = GraphStore(root / "g.db")
            nodes = [
                {"id": f"n{i}", "kind": "function", "name": f"f{i}", "line": i + 1}
                for i in range(80)
            ]
            edges = [
                {"src": f"n{i}", "dst": f"n{i+1}", "kind": "CALLS"}
                for i in range(79)
            ]
            store.replace_file_graph("big-repo", "big.py", nodes, edges)
            store.upsert_file("big-repo", "big.py", "sha", 1, 123)
            # Add an edge from another repo into this repo to verify both src
            # and dst references are cleaned up.
            store.replace_file_graph(
                "other-repo",
                "other.py",
                [{"id": "other", "kind": "function", "name": "other", "line": 1}],
                [{"src": "other", "dst": "n1", "kind": "CALLS"}],
            )

            store.remove_repo("big-repo")

            self.assertEqual(store.search("f", repo="big-repo"), [])
            self.assertNotIn("big-repo", store.repositories())
            self.assertFalse(any(e["src"].startswith("n") or e["dst"].startswith("n") for e in store.all_edges()))
            self.assertTrue(store.resolve("other", repo="other-repo"))

class DashboardInteractionRegressionTests(unittest.TestCase):
    def test_dashboard_controls_are_real_buttons_and_have_handlers(self):
        from repograph.dashboard import HTML
        self.assertIn('id="analyzeBtn"', HTML)
        self.assertIn('id="syncBtn"', HTML)
        self.assertIn('id="searchBtn"', HTML)
        self.assertIn('id="refreshBtn"', HTML)
        self.assertIn('id="localGraphBtn"', HTML)
        self.assertIn('id="teamGraphBtn"', HTML)
        self.assertIn('class="navbtn active"', HTML)
        self.assertIn('class="widget" data-target=', HTML)
        self.assertIn("addEventListener('click',runWhatIf)", HTML)
        self.assertIn("addEventListener('click',syncGit)", HTML)
        self.assertIn("'/api/team-graph?limit=170'", HTML)

    def test_dashboard_js_surfaces_http_errors(self):
        from repograph.dashboard import HTML
        self.assertIn('if(!r.ok)throw new Error', HTML)
        self.assertIn("toast('Git sync failed: '+e.message,'error')", HTML)
        self.assertIn("toast('Impact analysis failed: '+e.message,'error')", HTML)
