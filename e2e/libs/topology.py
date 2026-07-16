import json
from pathlib import Path


def load_node_inventory(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("nodes"), dict):
        raise AssertionError(f"invalid node inventory schema in {path}")
    return document["nodes"]


def select_nodes_for_requirements(requirements, node_attributes):
    """Select distinct nodes matching ordered OS/filesystem requirements."""
    selected = []
    for requirement in requirements:
        candidates = [
            node
            for node, attributes in sorted(node_attributes.items())
            if node not in selected
            and all(
                str(attributes.get(key, "")).lower() == str(value).lower()
                for key, value in requirement.items()
            )
        ]
        if not candidates:
            raise AssertionError(
                f"topology requires another node matching {requirement}; "
                f"available node attributes: {node_attributes}"
            )
        selected.append(candidates[0])
    return selected


def select_nodes_for_operating_systems(required_operating_systems, node_operating_systems):
    """Backward-compatible wrapper for OS-only topology profiles."""
    return select_nodes_for_requirements(
        [{"os": operating_system} for operating_system in required_operating_systems],
        {
            node: {"os": operating_system}
            for node, operating_system in node_operating_systems.items()
        },
    )
