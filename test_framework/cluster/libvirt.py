from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

from .provider import CommandError, Provider, run


class LibvirtProvider(Provider):
    @property
    def vagrant_dir(self) -> Path:
        return self.repository / "test_framework" / "vagrant" / "mixed-rke2"

    @property
    def network_cli(self) -> Path:
        return self.repository / "test_framework" / "cluster" / "network.py"

    def _vagrant_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update({
            "LONGHORN_TEST_TOPOLOGY": str(self.run_dir / "topology.json"),
            "LONGHORN_TEST_RUN_DIR": str(self.run_dir),
            "VAGRANT_CWD": str(self.vagrant_dir),
        })
        return environment

    def _vagrant(self, *args: str) -> None:
        command = ["vagrant", *args]
        print("+ " + " ".join(command), flush=True)
        try:
            subprocess.run(command, cwd=self.vagrant_dir, env=self._vagrant_environment(), check=True)
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"Vagrant failed with exit code {exc.returncode}") from exc

    def preflight(self) -> None:
        self.require_commands("vagrant", "virsh", "qemu-system-x86_64", "ovs-vsctl", "ovs-ofctl", "tc", "kubectl")
        self.require_kvm()
        plugins = run(["vagrant", "plugin", "list"], capture=True)
        if "vagrant-libvirt" not in plugins:
            raise CommandError("vagrant-libvirt is not installed")
        self._require_local_windows_boxes()
        meminfo = Path("/proc/meminfo").read_text(encoding="ascii")
        available_kib = int(next(line.split()[1] for line in meminfo.splitlines() if line.startswith("MemAvailable:")))
        required_kib = (sum(node.memory_mb for node in self.topology.nodes) + 16384) * 1024
        if available_kib < required_kib:
            raise CommandError(
                f"profile requires {required_kib // 1024} MiB including host headroom; "
                f"only {available_kib // 1024} MiB is available"
            )
        bridge = self.topology.cluster["data_network"]["bridge"]
        if len(bridge) > 15:
            raise CommandError("OVS bridge names must fit the Linux interface-name limit")

    def up(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.write_common_outputs("libvirt")
        token_file = self.run_dir / "cluster-token"
        if not token_file.exists():
            token_file.write_text(secrets.token_hex(32), encoding="ascii")
            token_file.chmod(0o600)
        self.preflight()
        self._network("up")
        self._vagrant("up", "--provider=libvirt", "--parallel")
        self._export_kubeconfig()
        self._wait_for_nodes()

    def _require_local_windows_boxes(self) -> None:
        required = {node.box for node in self.topology.nodes if node.os == "windows"}
        if not required:
            return
        listed = run(["vagrant", "box", "list", "--machine-readable"], capture=True)
        installed = {
            fields[3]
            for line in listed.splitlines()
            if len(fields := line.split(",", 4)) >= 4 and fields[2] == "box-name"
        }
        missing = sorted(required - installed)
        if missing:
            build_dir = self.repository / "test_framework" / "packer" / "windows-server-2022"
            raise CommandError(
                "Windows profiles require locally built Vagrant box(es): "
                f"{', '.join(missing)}. Build and install the private Windows Server 2022 box from {build_dir}"
            )

    def _export_kubeconfig(self) -> None:
        server = self.topology.server
        destination = self.run_dir / "kubeconfig.yaml"
        kubeconfig = run(
            ["vagrant", "ssh", server.name, "-c", "sudo cat /etc/rancher/rke2/rke2.yaml"],
            cwd=self.vagrant_dir,
            capture=True,
            environment=self._vagrant_environment(),
        )
        text = kubeconfig.replace(
            "https://127.0.0.1:6443", f"https://{server.management_ip}:6443"
        )
        destination.write_text(text, encoding="utf-8")

    def _wait_for_nodes(self, timeout_seconds: int = 1800) -> None:
        kubeconfig = self.run_dir / "kubeconfig.yaml"
        expected = {node.name: node.os for node in self.topology.nodes}
        deadline = time.monotonic() + timeout_seconds
        last_detail = "Kubernetes API has not responded"
        command = ["kubectl", "--kubeconfig", str(kubeconfig), "get", "nodes", "-o", "json"]
        while time.monotonic() < deadline:
            completed = subprocess.run(command, check=False, text=True, capture_output=True)
            if completed.returncode == 0:
                document = json.loads(completed.stdout)
                observed: dict[str, tuple[str, bool]] = {}
                for item in document.get("items", []):
                    name = item["metadata"]["name"]
                    os_name = item["metadata"].get("labels", {}).get("kubernetes.io/os", "")
                    ready = any(
                        condition.get("type") == "Ready" and condition.get("status") == "True"
                        for condition in item.get("status", {}).get("conditions", [])
                    )
                    observed[name] = (os_name, ready)
                if all(observed.get(name) == (os_name, True) for name, os_name in expected.items()):
                    return
                last_detail = f"expected {expected}; observed {observed}"
            else:
                last_detail = completed.stderr.strip() or completed.stdout.strip()
            time.sleep(5)
        raise CommandError(f"nodes did not become Ready within {timeout_seconds}s: {last_detail}")

    def down(self) -> None:
        if (self.run_dir / "topology.json").exists():
            self._vagrant("destroy", "-f")
            self._network("down")

    def status(self) -> None:
        self._vagrant("status")

    def snapshot(self, node: str, name: str) -> None:
        self._vagrant("snapshot", "save", node, name)

    def restore(self, node: str, name: str) -> None:
        self._vagrant("snapshot", "restore", node, name)

    def fault(self, action: str, *arguments: str) -> None:
        self._network(action, *arguments)

    def _network(self, action: str, *arguments: str) -> None:
        run(["sudo", "-n", "python3", str(self.network_cli), "--topology", str(self.run_dir / "topology.json"), action, *arguments])
