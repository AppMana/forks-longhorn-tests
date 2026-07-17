#!/usr/bin/env python3
"""Forced-command SSH endpoint for an in-cluster E2E runner.

The account running this command should have an authorized_keys entry using
`restrict,command=".../host_control.py --run-dir ..."`. Requests are one JSON
object on stdin and responses are one JSON object on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from test_framework.cluster.provider import CommandError, vagrant_fixture_directory
else:
    from .provider import CommandError, vagrant_fixture_directory


VAGRANT_ACTIONS = {"status", "up", "halt", "reload", "snapshot"}
SNAPSHOT_ACTIONS = {"save", "delete", "restore"}
FAULT_ACTIONS = {"isolate", "partition", "netem", "clear"}


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(1)


def validate_vagrant(arguments: list[str], nodes: set[str]) -> None:
    if not arguments or arguments[0] not in VAGRANT_ACTIONS:
        fail("Vagrant action is not allowed")
    action = arguments[0]
    remaining = arguments[1:]
    if action == "status":
        if remaining not in ([], ["--machine-readable"]): fail("invalid status arguments")
    elif action in {"up", "halt", "reload"}:
        if any(value not in nodes for value in remaining): fail("unknown node")
    elif action == "snapshot":
        if len(remaining) != 3 or remaining[0] not in SNAPSHOT_ACTIONS or remaining[1] not in nodes:
            fail("invalid snapshot request")
        expected_prefix = f"{remaining[1]}-snap-"
        if not remaining[2].startswith(expected_prefix): fail("snapshot name must be node scoped")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("SSH_ORIGINAL_COMMAND"):
        fail("commands must be supplied as JSON on stdin")
    try:
        request = json.load(sys.stdin)
        topology = json.loads((args.run_dir / "topology.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(str(exc))
    nodes = {node["name"] for node in topology["nodes"]}
    kind = request.get("kind")
    arguments = request.get("arguments")
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        fail("arguments must be a string array")
    if kind == "vagrant":
        validate_vagrant(arguments, nodes)
        command = ["vagrant", *arguments]
        try:
            cwd = vagrant_fixture_directory(args.repository, topology["cluster"])
        except (CommandError, KeyError) as exc:
            fail(str(exc))
        environment = {**os.environ, "LONGHORN_TEST_TOPOLOGY_FILE": str(args.run_dir / "topology.json"), "LONGHORN_TEST_RUN_DIR": str(args.run_dir)}
    elif kind == "fault":
        if not arguments or arguments[0] not in FAULT_ACTIONS:
            fail("fault action is not allowed")
        mentioned_nodes = [value for value in arguments[1:3] if not value.startswith(("delay", "loss", "rate", "limit", "corrupt", "duplicate", "reorder"))]
        if arguments[0] != "netem" and any(value not in nodes for value in mentioned_nodes): fail("unknown node")
        command = ["sudo", "-n", "python3", str(args.repository / "test_framework" / "cluster" / "network.py"), "--topology", str(args.run_dir / "topology.json"), *arguments]
        cwd = args.repository
        environment = os.environ.copy()
    else:
        fail("request kind is not allowed")
    completed = subprocess.run(command, cwd=cwd, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(json.dumps({"ok": completed.returncode == 0, "returncode": completed.returncode, "output": completed.stdout}))
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
