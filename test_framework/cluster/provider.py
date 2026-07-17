from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Mapping, Sequence

from .topology import Topology


class CommandError(RuntimeError):
    pass


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    environment: Mapping[str, str] | None = None,
) -> str:
    printable = " ".join(shlex.quote(part) for part in command)
    print(f"+ {printable}", flush=True)
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, check=True, text=True, env=environment,
            stdout=subprocess.PIPE if capture else None,
        )
    except subprocess.CalledProcessError as exc:
        raise CommandError(f"command failed with exit code {exc.returncode}: {printable}") from exc
    return completed.stdout if capture else ""


class Provider(ABC):
    def __init__(self, topology: Topology, run_dir: Path, repository: Path):
        self.topology = topology
        self.run_dir = run_dir
        self.repository = repository

    @abstractmethod
    def up(self) -> None: ...

    @abstractmethod
    def down(self) -> None: ...

    @abstractmethod
    def status(self) -> None: ...

    @abstractmethod
    def snapshot(self, node: str, name: str) -> None: ...

    @abstractmethod
    def restore(self, node: str, name: str) -> None: ...

    def write_common_outputs(self, provider_name: str) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "topology.json").write_text(
            json.dumps(self.topology.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        inventory = {
            "schema_version": 1,
            "cluster_name": self.topology.cluster["name"],
            "provider": provider_name,
            "kubernetes": self.topology.cluster["kubernetes"],
            "nodes": {
                node.name: {
                    "os": node.os,
                    "role": node.role,
                    "private_ip": node.data_ip,
                    "management_ip": node.management_ip,
                    "filesystem": node.filesystem,
                    "containerd_major": (
                        self.topology.cluster.get("expected_containerd_major")
                        if node.os == "windows" else None
                    ),
                }
                for node in self.topology.nodes
            },
        }
        (self.run_dir / "node-inventory.json").write_text(
            json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
        )
        (self.run_dir / "instance-mapping.json").write_text(
            json.dumps({node.name: node.name for node in self.topology.nodes}, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def require_commands(*commands: str) -> None:
        missing = [command for command in commands if shutil.which(command) is None]
        if missing:
            raise CommandError(f"required commands are missing: {', '.join(missing)}")

    @staticmethod
    def require_kvm() -> None:
        if not os.access("/dev/kvm", os.R_OK | os.W_OK):
            raise CommandError("/dev/kvm is not available to the current user")
