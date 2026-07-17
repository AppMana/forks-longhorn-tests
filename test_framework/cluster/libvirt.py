from __future__ import annotations

import json
import os
import secrets
import shlex
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

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
            "LONGHORN_TEST_TOPOLOGY_FILE": str(self.run_dir / "topology.json"),
            "LONGHORN_TEST_RUN_DIR": str(self.run_dir),
            "VAGRANT_CWD": str(self.vagrant_dir),
        })
        return environment

    def _vagrant_command(self) -> list[str]:
        # The system-libvirt wrapper preserves the invoking user's Vagrant
        # home while elevating only actions that open qemu:///system.
        return shlex.split(os.environ.get("VAGRANT_CMD", "vagrant"))

    def _vagrant(self, *args: str) -> None:
        command = [*self._vagrant_command(), *args]
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
        running_nodes = self._running_vagrant_nodes()
        additional_memory_mb = sum(
            node.memory_mb for node in self.topology.nodes if node.name not in running_nodes
        )
        required_kib = (additional_memory_mb + 16384) * 1024
        if available_kib < required_kib:
            raise CommandError(
                f"profile requires {required_kib // 1024} MiB including host headroom; "
                f"only {available_kib // 1024} MiB is available"
            )
        bridge = self.topology.cluster["data_network"]["bridge"]
        if len(bridge) > 15:
            raise CommandError("OVS bridge names must fit the Linux interface-name limit")

    def _running_vagrant_nodes(self) -> set[str]:
        completed = subprocess.run(
            [*self._vagrant_command(), "status", "--machine-readable"],
            cwd=self.vagrant_dir,
            env=self._vagrant_environment(),
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            return set()
        running: set[str] = set()
        for line in completed.stdout.splitlines():
            fields = line.split(",", 3)
            if len(fields) == 4 and fields[2] == "state" and fields[3] == "running":
                running.add(fields[1])
        return running

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
        self._record_discovered_node_versions()
        self._validate_containerd_generation()
        self._configure_storage_network()

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
        configured_path = str(self.topology.cluster.get("server_kubeconfig_path", ""))
        # The VM provider owns transport, not Kubernetes distribution layout.
        # Prefer an explicitly supplied path, then discover the usual admin
        # kubeconfig without requiring the caller to know which distribution
        # produced it.
        discover = r"""set -eu
configured=$1
if [ -n "$configured" ] && [ -f "$configured" ]; then cat "$configured"; exit 0; fi
if [ -n "${KUBECONFIG:-}" ] && [ -f "${KUBECONFIG:-}" ]; then cat "$KUBECONFIG"; exit 0; fi
for path in /etc/kubernetes/admin.conf /etc/rancher/rke2/rke2.yaml /etc/rancher/k3s/k3s.yaml; do
  if [ -f "$path" ]; then cat "$path"; exit 0; fi
done
path=$(find /etc -maxdepth 5 -type f \( -name admin.conf -o -name rke2.yaml -o -name k3s.yaml \) -print -quit 2>/dev/null || true)
if [ -n "$path" ]; then cat "$path"; exit 0; fi
echo 'no Kubernetes admin kubeconfig found' >&2
exit 1
"""
        kubeconfig = run(
            [
                *self._vagrant_command(), "ssh", server.name, "-c",
                f"sudo sh -c {shlex.quote(discover)} sh {shlex.quote(configured_path)}",
            ],
            cwd=self.vagrant_dir,
            capture=True,
            environment=self._vagrant_environment(),
        )
        document = yaml.safe_load(kubeconfig)
        current_context_name = document.get("current-context")
        contexts = {
            item["name"]: item.get("context", {})
            for item in document.get("contexts", [])
        }
        cluster_name = contexts.get(current_context_name, {}).get("cluster")
        clusters = {
            item["name"]: item.get("cluster", {})
            for item in document.get("clusters", [])
        }
        cluster = clusters.get(cluster_name)
        if not cluster or not cluster.get("server"):
            raise CommandError("discovered kubeconfig has no server for its current context")
        endpoint = urlsplit(cluster["server"])
        port = endpoint.port or 6443
        cluster["server"] = urlunsplit((
            endpoint.scheme or "https",
            f"{server.management_ip}:{port}",
            endpoint.path,
            endpoint.query,
            endpoint.fragment,
        ))
        destination.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

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

    def _validate_containerd_generation(self) -> None:
        expected = str(
            self.topology.cluster.get("expected_containerd_line")
            or self.topology.cluster.get("expected_containerd_major")
            or ""
        )
        if not expected:
            return
        kubeconfig = self.run_dir / "kubeconfig.yaml"
        document = json.loads(run([
            "kubectl", "--kubeconfig", str(kubeconfig), "get", "nodes", "-o", "json"
        ], capture=True))
        mismatches: list[str] = []
        for item in document.get("items", []):
            labels = item["metadata"].get("labels", {})
            if labels.get("kubernetes.io/os") != "windows":
                continue
            name = item["metadata"]["name"]
            version = item.get("status", {}).get("nodeInfo", {}).get("containerRuntimeVersion", "")
            prefix = "containerd://"
            runtime = version[len(prefix):] if version.startswith(prefix) else ""
            if runtime != expected and not runtime.startswith(expected + "."):
                mismatches.append(f"{name}={version or '<missing>'}")
        if mismatches:
            raise CommandError(
                f"profile requires containerd {expected}.x on Windows; observed {', '.join(mismatches)}. "
                "Destroy the other runtime profile before provisioning this one."
            )

    def _record_discovered_node_versions(self) -> None:
        kubeconfig = self.run_dir / "kubeconfig.yaml"
        document = json.loads(run([
            "kubectl", "--kubeconfig", str(kubeconfig), "get", "nodes", "-o", "json"
        ], capture=True))
        inventory_path = self.run_dir / "node-inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        for item in document.get("items", []):
            name = item.get("metadata", {}).get("name")
            if name not in inventory["nodes"]:
                continue
            node_info = item.get("status", {}).get("nodeInfo", {})
            runtime = node_info.get("containerRuntimeVersion", "")
            entry = inventory["nodes"][name]
            entry["container_runtime_version"] = runtime or None
            entry["kubelet_version"] = node_info.get("kubeletVersion") or None
            if runtime.startswith("containerd://"):
                version = runtime.removeprefix("containerd://")
                major = version.split(".", 1)[0]
                entry["containerd_major"] = major
                entry["containerd_line"] = (
                    ".".join(version.split(".")[:2]) if major == "1" else major
                )
        inventory_path.write_text(
            json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
        )

    def _configure_storage_network(self, timeout_seconds: int = 600) -> None:
        secondary = self.topology.cluster.get("secondary_cni", {})
        network = self.topology.cluster.get("data_network", {})
        if secondary.get("name") != "multus":
            return

        kubeconfig = self.run_dir / "kubeconfig.yaml"
        deadline = time.monotonic() + timeout_seconds
        command = [
            "kubectl", "--kubeconfig", str(kubeconfig), "get", "crd",
            "network-attachment-definitions.k8s.cni.cncf.io",
        ]
        while time.monotonic() < deadline:
            if subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(5)
        else:
            raise CommandError("RKE2 Multus NetworkAttachmentDefinition CRD did not become ready")

        manifest = {
            "apiVersion": "k8s.cni.cncf.io/v1",
            "kind": "NetworkAttachmentDefinition",
            "metadata": {"name": network["network_attachment"], "namespace": "kube-system"},
            "spec": {"config": json.dumps({
                "cniVersion": "0.3.1",
                "type": "macvlan",
                "master": network["pod_interface"],
                "mode": "bridge",
                "ipam": {
                    "type": secondary.get("ipam", "whereabouts"),
                    "range": network["cidr"],
                    "range_start": network["pod_range_start"],
                    "range_end": network["pod_range_end"],
                },
            }, separators=(",", ":"))},
        }
        manifest_path = self.run_dir / "storage-network.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        run(["kubectl", "--kubeconfig", str(kubeconfig), "apply", "-f", str(manifest_path)])

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
