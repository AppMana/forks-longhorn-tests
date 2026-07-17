from __future__ import annotations

import json
import shutil

from .provider import Provider, run


class AwsProvider(Provider):
    """Thin adapter around the existing mixed-rke2 Terraform workspace."""

    @property
    def workspace(self):
        return self.repository / "test_framework" / "terraform" / "aws" / "mixed-rke2"

    def _variables(self) -> dict[str, object]:
        linux_workers = [n for n in self.topology.nodes if n.os == "linux" and n.role == "agent"]
        ntfs_workers = [n for n in self.topology.nodes if n.os == "windows" and n.filesystem == "ntfs"]
        refs_workers = [n for n in self.topology.nodes if n.os == "windows" and n.filesystem == "refs"]
        return {
            "cluster_name": self.topology.cluster["name"],
            "k8s_distro_version": self.topology.cluster["rke2_version"],
            "linux_worker_count": len(linux_workers),
            "windows_ntfs_worker_count": len(ntfs_workers),
            "windows_refs_worker_count": len(refs_workers),
        }

    def up(self) -> None:
        self.require_commands("terraform")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        variables = self.run_dir / "topology.auto.tfvars.json"
        variables.write_text(json.dumps(self._variables(), indent=2) + "\n", encoding="utf-8")
        run(["terraform", "init"], cwd=self.workspace)
        run(["terraform", "apply", "-auto-approve", f"-var-file={variables}"], cwd=self.workspace)
        self.write_common_outputs("aws")
        shutil.copy2(self.workspace / "rke2.yaml", self.run_dir / "kubeconfig.yaml")
        inventory = run(["terraform", "output", "-raw", "node_inventory"], cwd=self.workspace, capture=True)
        (self.run_dir / "node-inventory.json").write_text(inventory + "\n", encoding="utf-8")
        mapping_rows = json.loads(run(["terraform", "output", "-raw", "instance_mapping"], cwd=self.workspace, capture=True))
        mapping = {row["name"].split(".")[0]: row["id"] for row in mapping_rows}
        (self.run_dir / "instance-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    def down(self) -> None:
        variables = self.run_dir / "topology.auto.tfvars.json"
        args = ["terraform", "destroy", "-auto-approve"]
        if variables.exists():
            args.append(f"-var-file={variables}")
        run(args, cwd=self.workspace)

    def status(self) -> None:
        run(["terraform", "show"], cwd=self.workspace)

    def snapshot(self, node: str, name: str) -> None:
        raise NotImplementedError("AWS snapshots remain exposed through the E2E host provider")

    def restore(self, node: str, name: str) -> None:
        raise NotImplementedError("AWS restore remains exposed through the E2E host provider")
