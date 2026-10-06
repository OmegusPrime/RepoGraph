import tempfile
import unittest
from pathlib import Path

from repograph.analyzer import RepositoryAnalyzer
from repograph.context import symbol_context
from repograph.exporter import export_markdown
from repograph.impact import impact
from repograph.store import GraphStore

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name)
        (self.root/"a.py").write_text("from b import helper\n\ndef run():\n    return helper()\n")
        (self.root/"b.py").write_text("def helper():\n    return 1\n")
        self.store=GraphStore(self.root/".repograph/cache/graph.db")
        self.a=RepositoryAnalyzer(self.root,self.store)
        self.a.scan(force=True)
    def tearDown(self): self.t.cleanup()
    def test_scan_builds_graph(self):
        s=self.store.stats(); self.assertGreaterEqual(s["files"],2); self.assertGreaterEqual(s["nodes"],4); self.assertGreaterEqual(s["edges"],2)
    def test_search(self): self.assertTrue(any(x["name"]=="helper" for x in self.store.search("helper")))
    def test_impact(self):
        r=impact(self.store,"helper",depth=4); self.assertNotEqual(r["risk"],"UNKNOWN"); self.assertTrue(any(x["name"] in ("run","a.py") for x in r["affected"]))
    def test_context_budget(self):
        r=symbol_context(self.store,"helper",2,400); self.assertLessEqual(r["estimated_tokens"],400); self.assertTrue(r["items"])
    def test_incremental_update(self):
        before=self.store.stats()["nodes"]
        (self.root/"b.py").write_text("def helper():\n    return 1\n\ndef added():\n    return helper()\n")
        self.a.scan(); self.assertGreater(self.store.stats()["nodes"],before)
    def test_markdown(self):
        p=export_markdown(self.root,self.store); txt=p.read_text(); self.assertIn("# Project Graph",txt); self.assertIn("helper",txt)

if __name__=="__main__": unittest.main()
