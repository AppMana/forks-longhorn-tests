#!/usr/bin/env python3
"""Run Vagrant against system libvirt without switching Vagrant HOME."""

from __future__ import annotations

import os
import subprocess
import sys


ALLOWED_ACTIONS = {"status", "up", "halt", "reload", "snapshot"}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ALLOWED_ACTIONS:
        raise SystemExit("vagrant_system.py only supports E2E host-control actions")

    forwarded = {
        name: os.environ[name]
        for name in (
            "LONGHORN_TEST_TOPOLOGY_FILE",
            "LONGHORN_TEST_RUN_DIR",
            "VAGRANT_CWD",
        )
        if os.environ.get(name)
    }
    home = os.path.expanduser("~")
    command = ["sudo", "-n", "env", f"HOME={home}"]
    command.extend(f"{name}={value}" for name, value in forwarded.items())
    command.extend(["vagrant", *sys.argv[1:]])
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
