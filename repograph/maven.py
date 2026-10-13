from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .util import SKIP_DIRS, relpath, stable_id


PROPERTY_RE = re.compile(r"\$\{([^}]+)\}")


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    for candidate in element:
        if candidate.tag.rsplit("}", 1)[-1] == name:
            return candidate
    return None


def _text(element: ET.Element | None, name: str, default: str = "") -> str:
    value = _child(element, name)
    return (value.text or "").strip() if value is not None else default


def _interpolate(value: str, properties: dict[str, str]) -> str:
    current = value or ""
    for _ in range(8):
        updated = PROPERTY_RE.sub(lambda match: properties.get(match.group(1), match.group(0)), current)
        if updated == current:
            break
        current = updated
    return current


@dataclass
class MavenModule:
    pom: Path
    pom_path: str
    module_dir: str
    group_id: str
    artifact_id: str
    version: str
    packaging: str
    parent_group_id: str = ""
    parent_artifact_id: str = ""
    parent_version: str = ""
    declared_modules: list[str] = field(default_factory=list)
    dependencies: list[tuple[str, str, str, str]] = field(default_factory=list)

    @property
    def ga(self) -> tuple[str, str]:
        return self.group_id, self.artifact_id


def _pom_files(root: Path):
    for base, dirs, files in os.walk(root):
        dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS]
        if "pom.xml" in files:
            yield Path(base) / "pom.xml"


def _parse_pom(root: Path, pom: Path) -> MavenModule | None:
    try:
        project = ET.parse(pom).getroot()
    except (ET.ParseError, OSError):
        return None

    parent = _child(project, "parent")
    parent_group = _text(parent, "groupId")
    parent_artifact = _text(parent, "artifactId")
    parent_version = _text(parent, "version")
    raw_group = _text(project, "groupId") or parent_group
    raw_artifact = _text(project, "artifactId") or pom.parent.name or root.name
    raw_version = _text(project, "version") or parent_version

    properties: dict[str, str] = {}
    property_element = _child(project, "properties")
    if property_element is not None:
        for item in property_element:
            properties[item.tag.rsplit("}", 1)[-1]] = (item.text or "").strip()
    properties.update(
        {
            "project.groupId": raw_group,
            "project.artifactId": raw_artifact,
            "project.version": raw_version,
            "pom.groupId": raw_group,
            "pom.artifactId": raw_artifact,
            "pom.version": raw_version,
            "parent.groupId": parent_group,
            "parent.artifactId": parent_artifact,
            "parent.version": parent_version,
        }
    )
    for key in list(properties):
        properties[key] = _interpolate(properties[key], properties)

    group_id = _interpolate(raw_group, properties)
    artifact_id = _interpolate(raw_artifact, properties)
    version = _interpolate(raw_version, properties)
    packaging = _interpolate(_text(project, "packaging", "jar"), properties) or "jar"

    declared_modules: list[str] = []
    modules_element = _child(project, "modules")
    if modules_element is not None:
        for module_element in modules_element:
            if module_element.tag.rsplit("}", 1)[-1] == "module" and module_element.text:
                declared_modules.append(_interpolate(module_element.text.strip(), properties))

    dependencies: list[tuple[str, str, str, str]] = []
    dependencies_element = _child(project, "dependencies")
    if dependencies_element is not None:
        for dependency in dependencies_element:
            if dependency.tag.rsplit("}", 1)[-1] != "dependency":
                continue
            dependencies.append(
                (
                    _interpolate(_text(dependency, "groupId"), properties),
                    _interpolate(_text(dependency, "artifactId"), properties),
                    _interpolate(_text(dependency, "version"), properties),
                    _interpolate(_text(dependency, "scope", "compile"), properties) or "compile",
                )
            )

    module_dir = relpath(pom.parent, root)
    return MavenModule(
        pom=pom,
        pom_path=relpath(pom, root),
        module_dir=module_dir,
        group_id=group_id,
        artifact_id=artifact_id,
        version=version,
        packaging=packaging,
        parent_group_id=_interpolate(parent_group, properties),
        parent_artifact_id=_interpolate(parent_artifact, properties),
        parent_version=_interpolate(parent_version, properties),
        declared_modules=declared_modules,
        dependencies=dependencies,
    )


def discover_maven_modules(root: Path) -> list[MavenModule]:
    root = Path(root).resolve()
    modules = [module for pom in _pom_files(root) if (module := _parse_pom(root, pom))]
    return sorted(modules, key=lambda module: (len(Path(module.module_dir).parts), module.pom_path))


def build_maven_graph(root: Path, repo_name: str, existing_nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    modules = discover_maven_modules(root)
    if not modules:
        return [], []

    node_id: dict[str, str] = {}
    nodes: list[dict] = []
    for module in modules:
        identifier = stable_id(repo_name, module.pom_path, "maven_module", module.artifact_id)
        node_id[module.pom_path] = identifier
        coordinate = ":".join(part for part in (module.group_id, module.artifact_id, module.version) if part)
        nodes.append(
            {
                "id": identifier,
                "kind": "maven_module",
                "name": module.artifact_id,
                "path": module.pom_path,
                "line": 1,
                "lang": "maven",
                "signature": f"{coordinate} [{module.packaging}]",
                "metadata": {
                    "build_system": "maven",
                    "group_id": module.group_id,
                    "artifact_id": module.artifact_id,
                    "version": module.version,
                    "packaging": module.packaging,
                    "module_dir": module.module_dir,
                },
            }
        )

    by_dir = {module.module_dir: module for module in modules}
    by_ga = {module.ga: module for module in modules if all(module.ga)}
    by_artifact: dict[str, list[MavenModule]] = {}
    for module in modules:
        by_artifact.setdefault(module.artifact_id, []).append(module)

    edges: list[dict] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_edge(source: MavenModule, target: MavenModule, kind: str, metadata: dict | None = None) -> None:
        edge = (node_id[source.pom_path], node_id[target.pom_path], kind)
        if source.pom_path == target.pom_path or edge in edge_keys:
            return
        edge_keys.add(edge)
        edges.append({"src": edge[0], "dst": edge[1], "kind": kind, "metadata": metadata or {}})

    for parent_module in modules:
        for declared in parent_module.declared_modules:
            child_path = (parent_module.pom.parent / declared).resolve()
            if child_path.name == "pom.xml":
                child_path = child_path.parent
            try:
                child_dir = relpath(child_path, root)
            except ValueError:
                continue
            child_module = by_dir.get(child_dir)
            if child_module:
                add_edge(parent_module, child_module, "PARENT_OF", {"source": "modules"})

    for child_module in modules:
        parent_module = by_ga.get((child_module.parent_group_id, child_module.parent_artifact_id))
        if parent_module:
            add_edge(parent_module, child_module, "PARENT_OF", {"source": "parent"})

        for group_id, artifact_id, version, scope in child_module.dependencies:
            target = by_ga.get((group_id, artifact_id))
            if target is None and len(by_artifact.get(artifact_id, [])) == 1:
                target = by_artifact[artifact_id][0]
            if target:
                add_edge(
                    child_module,
                    target,
                    "DEPENDS_ON_MODULE",
                    {"group_id": group_id, "artifact_id": artifact_id, "version": version, "scope": scope},
                )

    def owner_for(path: str) -> MavenModule | None:
        candidates = [
            module
            for module in modules
            if module.module_dir == "." or path == module.module_dir or path.startswith(module.module_dir.rstrip("/") + "/")
        ]
        return max(candidates, key=lambda module: len(Path(module.module_dir).parts), default=None)

    pom_paths = {module.pom_path for module in modules}
    for graph_node in existing_nodes:
        if graph_node.get("kind") not in {"file", "class"} or graph_node.get("path") in pom_paths:
            continue
        owner = owner_for(graph_node.get("path", ""))
        if owner is None:
            continue
        edge = (node_id[owner.pom_path], graph_node["id"], "MODULE_CONTAINS")
        if edge not in edge_keys:
            edge_keys.add(edge)
            edges.append(
                {
                    "src": edge[0],
                    "dst": edge[1],
                    "kind": edge[2],
                    "metadata": {"member_kind": graph_node["kind"]},
                }
            )

    return nodes, edges
