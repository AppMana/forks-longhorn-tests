from __future__ import annotations

import copy
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Node:
    name: str
    os: str
    role: str
    data_ip: str
    management_ip: str
    mac: str
    tap: str
    filesystem: str
    box: str
    cpus: int
    memory_mb: int
    root_disk_gb: int
    data_disk_gb: int
    labels: dict[str, str]
    taints: list[str]


@dataclass(frozen=True)
class Topology:
    schema_version: int
    cluster: dict[str, Any]
    profile: str
    nodes: tuple[Node, ...]

    @property
    def server(self) -> Node:
        servers = [node for node in self.nodes if node.role == "server"]
        if len(servers) != 1:
            raise ValueError(f"profile {self.profile!r} must contain exactly one server")
        return servers[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cluster": self.cluster,
            "profile": self.profile,
            "nodes": [node.__dict__ for node in self.nodes],
        }


def load_topology(path: Path, profile: str) -> Topology:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("only topology schema_version 1 is supported")

    profiles = raw.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"unknown topology profile {profile!r}")
    selected = copy.deepcopy(profiles[profile])
    canonical_nodes = {str(node["name"]): node for node in raw.get("nodes", [])}
    node_names = selected.get("node_names")
    if node_names is not None:
        missing = [name for name in node_names if name not in canonical_nodes]
        if missing:
            raise ValueError(f"profile {profile!r} references unknown nodes: {', '.join(missing)}")
        node_specs = [copy.deepcopy(canonical_nodes[name]) for name in node_names]
    else:
        inherited: list[dict[str, Any]] = []
        if base_name := selected.get("extends"):
            if base_name not in profiles:
                raise ValueError(f"profile {profile!r} extends unknown profile {base_name!r}")
            inherited = copy.deepcopy(profiles[base_name].get("nodes", []))
        node_specs = inherited + selected.get("nodes", [])

    defaults = raw.get("defaults", {})
    nodes: list[Node] = []
    names: set[str] = set()
    addresses: set[str] = set()
    macs: set[str] = set()
    taps: set[str] = set()
    for spec in node_specs:
        os_name = str(spec["os"]).lower()
        if os_name not in {"linux", "windows"}:
            raise ValueError(f"node {spec.get('name')!r} has unsupported OS {os_name!r}")
        merged = {**defaults.get(os_name, {}), **spec}
        if merged["role"] == "agent":
            merged = {**defaults.get("worker", {}), **merged}
        node = Node(
            name=str(merged["name"]),
            os=os_name,
            role=str(merged["role"]),
            data_ip=str(merged["data_ip"]),
            management_ip=str(merged["management_ip"]),
            mac=str(merged["mac"]).lower(),
            tap=str(merged["tap"]),
            filesystem=str(merged.get("filesystem", "")),
            box=str(merged["box"]),
            cpus=int(merged["cpus"]),
            memory_mb=int(merged["memory_mb"]),
            root_disk_gb=int(merged["root_disk_gb"]),
            data_disk_gb=int(merged.get("data_disk_gb", 0)),
            labels={str(k): str(v) for k, v in merged.get("labels", {}).items()},
            taints=[str(value) for value in merged.get("taints", [])],
        )
        if node.name in names or node.data_ip in addresses or node.management_ip in addresses:
            raise ValueError(f"duplicate node name or address in {node.name!r}")
        if node.mac in macs or node.tap in taps:
            raise ValueError(f"duplicate MAC or tap name in {node.name!r}")
        if node.role not in {"server", "agent"}:
            raise ValueError(f"node {node.name!r} has unsupported role {node.role!r}")
        if node.os == "windows" and node.role == "server":
            raise ValueError("RKE2 does not support Windows server nodes")
        if node.filesystem not in {"", "ext4", "ntfs", "refs"}:
            raise ValueError(f"node {node.name!r} has unsupported filesystem {node.filesystem!r}")
        names.add(node.name)
        addresses.update((node.data_ip, node.management_ip))
        macs.add(node.mac)
        taps.add(node.tap)
        nodes.append(node)

    topology = Topology(int(raw["schema_version"]), copy.deepcopy(raw["cluster"]), profile, tuple(nodes))
    topology.server
    data_network = ipaddress.ip_network(topology.cluster["data_network"]["cidr"])
    management_network = ipaddress.ip_network(topology.cluster["management_network"]["cidr"])
    for node in nodes:
        if ipaddress.ip_address(node.data_ip) not in data_network:
            raise ValueError(f"{node.data_ip} is outside the data network")
        if ipaddress.ip_address(node.management_ip) not in management_network:
            raise ValueError(f"{node.management_ip} is outside the management network")
    return topology
