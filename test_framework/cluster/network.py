#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


COOKIE = "0x4c480001"


def command(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        args,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=None if check else subprocess.DEVNULL,
    )
    return result.stdout.strip()


class Network:
    def __init__(self, topology_path: Path):
        self.topology = json.loads(topology_path.read_text(encoding="utf-8"))
        self.bridge = self.topology["cluster"]["data_network"]["bridge"]
        self.nodes = {node["name"]: node for node in self.topology["nodes"]}

    def up(self) -> None:
        bridge_exists = subprocess.run(
            ("ovs-vsctl", "br-exists", self.bridge),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if not bridge_exists:
            try:
                from mininet.net import Containernet
            except ImportError as exc:
                raise SystemExit("Containernet is required; run test_framework/scripts/install-libvirt-runtime.sh") from exc
            # Containernet owns only the switch. Real libvirt VM interfaces
            # attach afterward; no container represents a Kubernetes node.
            network = Containernet(controller=None, build=False)
            switch = network.addSwitch(self.bridge, protocols="OpenFlow13")
            switch.start([])
        command("ovs-vsctl", "set", "bridge", self.bridge, "protocols=OpenFlow13")
        command("ovs-ofctl", "-O", "OpenFlow13", "del-flows", self.bridge, f"cookie={COOKIE}/-1")
        command("ovs-ofctl", "-O", "OpenFlow13", "add-flow", self.bridge, f"cookie={COOKIE},priority=0,actions=NORMAL")

    def down(self) -> None:
        self.clear()
        command("ovs-vsctl", "--if-exists", "del-br", self.bridge)

    def clear(self) -> None:
        bridge_exists = subprocess.run(
            ("ovs-vsctl", "br-exists", self.bridge),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if bridge_exists:
            command("ovs-ofctl", "-O", "OpenFlow13", "del-flows", self.bridge, f"cookie={COOKIE}/-1")
            command("ovs-ofctl", "-O", "OpenFlow13", "add-flow", self.bridge, f"cookie={COOKIE},priority=0,actions=NORMAL", check=False)
        for node in self.nodes.values():
            if Path("/sys/class/net", node["tap"]).exists():
                command("tc", "qdisc", "del", "dev", node["tap"], "root", check=False)

    def _node(self, name: str) -> dict[str, str]:
        try:
            return self.nodes[name]
        except KeyError as exc:
            raise SystemExit(f"unknown node {name!r}") from exc

    def isolate(self, name: str) -> None:
        node = self._node(name)
        for match in (f"dl_src={node['mac']}", f"dl_dst={node['mac']}"):
            command("ovs-ofctl", "-O", "OpenFlow13", "add-flow", self.bridge,
                    f"cookie={COOKIE},priority=300,{match},actions=drop")

    def partition(self, left: str, right: str) -> None:
        a, b = self._node(left), self._node(right)
        for source, destination in ((a, b), (b, a)):
            command("ovs-ofctl", "-O", "OpenFlow13", "add-flow", self.bridge,
                    f"cookie={COOKIE},priority=300,dl_src={source['mac']},dl_dst={destination['mac']},actions=drop")

    def netem(self, name: str, arguments: list[str]) -> None:
        node = self._node(name)
        command("tc", "qdisc", "replace", "dev", node["tap"], "root", "netem", *arguments)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("up")
    sub.add_parser("down")
    sub.add_parser("clear")
    isolate = sub.add_parser("isolate")
    isolate.add_argument("node")
    partition = sub.add_parser("partition")
    partition.add_argument("left")
    partition.add_argument("right")
    netem = sub.add_parser("netem")
    netem.add_argument("node")
    netem.add_argument("parameters", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    network = Network(args.topology)
    if args.action == "up": network.up()
    elif args.action == "down": network.down()
    elif args.action == "clear": network.clear()
    elif args.action == "isolate": network.isolate(args.node)
    elif args.action == "partition": network.partition(args.left, args.right)
    elif args.action == "netem": network.netem(args.node, args.parameters)


if __name__ == "__main__":
    main()
