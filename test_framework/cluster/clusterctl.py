#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from test_framework.cluster.aws import AwsProvider
    from test_framework.cluster.libvirt import LibvirtProvider
    from test_framework.cluster.provider import CommandError
    from test_framework.cluster.topology import load_topology
else:
    from .aws import AwsProvider
    from .libvirt import LibvirtProvider
    from .provider import CommandError
    from .topology import load_topology


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    default_state = Path.home() / "Documents" / ".longhorn-test" / "runs" / "mixed-rke2"
    parser = argparse.ArgumentParser(description="Provision Longhorn E2E clusters through a stable provider contract")
    parser.add_argument("--provider", choices=("aws", "libvirt"), default=os.getenv("LONGHORN_TEST_PROVIDER", "libvirt"))
    parser.add_argument("--profile", default=os.getenv("LONGHORN_TEST_PROFILE", "windows-gate"))
    parser.add_argument("--topology", type=Path, default=repository / "test_framework" / "topologies" / "mixed-rke2.yaml")
    parser.add_argument("--run-dir", type=Path, default=Path(os.getenv("LONGHORN_TEST_RUN_DIR", default_state)))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("up")
    sub.add_parser("down")
    sub.add_parser("status")
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("node")
    snapshot.add_argument("name")
    restore = sub.add_parser("restore")
    restore.add_argument("node")
    restore.add_argument("name")
    fault = sub.add_parser("fault")
    fault.add_argument("fault_action", choices=("isolate", "partition", "netem", "clear"))
    fault.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    topology = load_topology(args.topology, args.profile)
    provider_class = AwsProvider if args.provider == "aws" else LibvirtProvider
    provider = provider_class(topology, args.run_dir.resolve(), repository)
    if args.action == "up": provider.up()
    elif args.action == "down": provider.down()
    elif args.action == "status": provider.status()
    elif args.action == "snapshot": provider.snapshot(args.node, args.name)
    elif args.action == "restore": provider.restore(args.node, args.name)
    elif args.action == "fault":
        if not isinstance(provider, LibvirtProvider):
            raise SystemExit("network faults are currently provided by the local libvirt provider")
        provider.fault(args.fault_action, *args.arguments)


if __name__ == "__main__":
    try:
        main()
    except CommandError as exc:
        raise SystemExit(f"clusterctl: {exc}") from exc
