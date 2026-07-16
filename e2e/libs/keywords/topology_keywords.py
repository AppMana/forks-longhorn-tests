import os
from pathlib import Path

import yaml
from kubernetes import client

from topology import load_node_inventory, select_nodes_for_requirements


class topology_keywords:
    def __init__(self):
        self.core_api = client.CoreV1Api()

    def select_topology_nodes(self, worker_nodes):
        topology = os.environ.get("LONGHORN_TEST_TOPOLOGY", "linux")
        default_file = Path(__file__).resolve().parents[2] / "topologies.yaml"
        topology_file = Path(os.environ.get("LONGHORN_TOPOLOGY_FILE", default_file))
        document = yaml.safe_load(topology_file.read_text(encoding="utf-8"))
        try:
            profile = document["profiles"][topology]
        except KeyError as error:
            raise AssertionError(
                f"unknown LONGHORN_TEST_TOPOLOGY {topology!r} in {topology_file}"
            ) from error

        node_attributes = {}
        for node_name in worker_nodes:
            node = self.core_api.read_node(node_name)
            node_attributes[node_name] = {
                "os": (
                    node.metadata.labels.get("kubernetes.io/os")
                    or node.status.node_info.operating_system
                    or "linux"
                ).lower(),
                "filesystem": node.metadata.labels.get(
                    "longhorn.io/test-filesystem", ""
                ).lower(),
            }

        inventory_path = os.environ.get("LONGHORN_NODE_INVENTORY")
        if inventory_path and Path(inventory_path).is_file():
            inventory = load_node_inventory(inventory_path)
            for node_name, attributes in node_attributes.items():
                if node_name not in inventory:
                    raise AssertionError(
                        f"Kubernetes node {node_name} is absent from {inventory_path}"
                    )
                for key in ("os", "filesystem"):
                    expected = str(inventory[node_name].get(key, "")).lower()
                    if expected != attributes[key]:
                        raise AssertionError(
                            f"node {node_name} {key} is {attributes[key]!r}, expected {expected!r} from inventory"
                        )

        requirements = profile.get("nodes") or [
            {"os": operating_system} for operating_system in profile["node_os"]
        ]
        return select_nodes_for_requirements(requirements, node_attributes)

    def find_topology_node(self, operating_system, filesystem=""):
        matches = []
        for node in self.core_api.list_node().items:
            node_os = (
                node.metadata.labels.get("kubernetes.io/os")
                or node.status.node_info.operating_system
                or "linux"
            ).lower()
            node_filesystem = node.metadata.labels.get(
                "longhorn.io/test-filesystem", ""
            ).lower()
            if node_os == operating_system.lower() and (
                not filesystem or node_filesystem == filesystem.lower()
            ):
                matches.append(node.metadata.name)
        if not matches:
            raise AssertionError(
                f"no {operating_system} node with filesystem {filesystem or '*'} is available"
            )
        return sorted(matches)[0]
