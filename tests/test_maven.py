import tempfile
import unittest
from pathlib import Path

from repograph.analyzer import RepositoryAnalyzer
from repograph.impact import impact
from repograph.store import GraphStore
from repograph.whatif import proposed_change_impact


PARENT = """\
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>fixture-parent</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <modules>
    <module>a</module><module>b</module><module>c</module><module>d</module>
  </modules>
</project>
"""


def child_pom(artifact: str, dependencies: tuple[str, ...] = ()) -> str:
    dependency_xml = "".join(
        f"<dependency><groupId>com.example</groupId><artifactId>{dependency}</artifactId>"
        "<version>${project.version}</version></dependency>"
        for dependency in dependencies
    )
    return f"""\
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example</groupId><artifactId>fixture-parent</artifactId>
    <version>1.0.0</version><relativePath>../pom.xml</relativePath>
  </parent>
  <artifactId>{artifact}</artifactId>
  <dependencies>{dependency_xml}</dependencies>
</project>
"""


class MavenMultiModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pom.xml").write_text(PARENT, encoding="utf-8")
        dependencies = {"A": ("B", "C"), "B": (), "C": (), "D": ("A",)}
        for artifact, deps in dependencies.items():
            directory = self.root / artifact.lower()
            source = directory / "src" / ("test" if artifact == "D" else "main") / "java" / "com" / "example"
            source.mkdir(parents=True)
            (directory / "pom.xml").write_text(child_pom(artifact, deps), encoding="utf-8")
            (source / f"{artifact}Service.java").write_text(
                f"package com.example;\npublic class {artifact}Service {{}}\n", encoding="utf-8"
            )
        self.store = GraphStore(self.root / ".repograph" / "cache" / "graph.db")
        RepositoryAnalyzer(self.root, self.store, repo_name="fixture").scan(force=True)

    def tearDown(self):
        self.temp.cleanup()

    def module(self, name: str) -> dict:
        return next(node for node in self.store.search(name, 30, repo="fixture") if node["kind"] == "maven_module" and node["name"] == name)

    def test_indexes_parent_dependencies_and_source_ownership(self):
        modules = {node["name"] for node in self.store.all_nodes() if node["kind"] == "maven_module"}
        self.assertEqual(modules, {"fixture-parent", "A", "B", "C", "D"})

        edges = {(edge["src"], edge["dst"], edge["kind"]) for edge in self.store.all_edges()}
        parent = self.module("fixture-parent")
        a, b, c = self.module("A"), self.module("B"), self.module("C")
        self.assertIn((parent["id"], a["id"], "PARENT_OF"), edges)
        self.assertIn((a["id"], b["id"], "DEPENDS_ON_MODULE"), edges)
        self.assertIn((a["id"], c["id"], "DEPENDS_ON_MODULE"), edges)

        owned = self.store.neighbors(a["id"], "out")
        self.assertTrue(any(node["edge_kind"] == "MODULE_CONTAINS" and node["name"] == "AService.java" for node in owned))
        self.assertTrue(any(node["edge_kind"] == "MODULE_CONTAINS" and node["name"] == "AService" for node in owned))

    def test_module_impact_reaches_direct_and_transitive_dependents(self):
        result = impact(self.store, self.module("B")["id"], depth=4)
        affected_modules = {node["name"] for node in result["affected"] if node["kind"] == "maven_module"}
        self.assertIn("A", affected_modules)
        self.assertIn("D", affected_modules)

    def test_what_if_counts_real_modules_files_and_tests(self):
        result = proposed_change_impact(self.store, "Change the B module public contract", depth=4)
        self.assertEqual(result["matched"][0]["kind"], "maven_module")
        module_names = {module["name"] for module in result["modules"]}
        self.assertTrue({"B", "A", "D"}.issubset(module_names))
        self.assertGreaterEqual(result["files_likely_to_change"], 3)
        self.assertTrue(any("src/test" in path for path in result["tests"]))

    def test_dashboard_slice_prioritizes_maven_modules(self):
        graph = self.store.graph_slice(limit=5)
        self.assertEqual({node["kind"] for node in graph["nodes"]}, {"maven_module"})


if __name__ == "__main__":
    unittest.main()
