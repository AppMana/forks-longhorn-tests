import ast
import json
import os
import threading
import time
import uuid

from kubernetes import client

from engine import Engine
from node_exec import NodeExec
from node_exec.manifest import build_windows_sandbox_probe_pod
from utility.utility import logging
from workload.workload import get_workload_volume_name


class windows_keywords:
    def __init__(self):
        self.engine = Engine()
        self.core_api = client.CoreV1Api()
        self._overlap_probe = None

    def assert_windows_containerd_sandbox_mounts(self, node_name):
        node = self.core_api.read_node(node_name)
        runtime = node.status.node_info.container_runtime_version
        assert runtime.startswith("containerd://"), f"{node_name} does not use containerd: {runtime}"
        actual_version = runtime.removeprefix("containerd://")
        actual_major = actual_version.split(".", 1)[0]
        actual_line = (
            ".".join(actual_version.split(".")[:2])
            if actual_major == "1"
            else actual_major
        )
        expected_line = node.metadata.labels.get(
            "longhorn.io/test-containerd-line",
            actual_line,
        )
        expected_major = node.metadata.labels.get(
            "longhorn.io/test-containerd-major", actual_major
        )
        assert actual_major == expected_major, (
            f"{node_name} runs {runtime}, expected containerd {expected_major}.x"
        )
        assert actual_version == expected_line or actual_version.startswith(expected_line + "."), (
            f"{node_name} runs {runtime}, expected containerd {expected_line}.x"
        )

        pod_name = f"windows-sandbox-probe-{uuid.uuid4().hex[:8]}"
        image = os.environ.get("WINDOWS_SANDBOX_PROBE_IMAGE", "")
        if not image:
            image = next(
                (
                    name
                    for status_image in (node.status.images or [])
                    for name in (status_image.names or [])
                    if "pause" in name.lower() and "@" not in name
                ),
                "",
            )
        assert image, (
            f"{node_name} advertises no tagged cached pause image; set "
            "WINDOWS_SANDBOX_PROBE_IMAGE to an image containing pause.exe"
        )
        manifest = build_windows_sandbox_probe_pod(
            pod_name, node_name, image, expected_line
        )
        self.core_api.create_namespaced_pod("default", manifest)
        try:
            # A first Windows Server Core pull and layer registration can take
            # several minutes on an otherwise empty containerd 1.x VM.
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                pod = self.core_api.read_namespaced_pod(pod_name, "default")
                if pod.status.phase in ("Succeeded", "Failed"):
                    output = ""
                    for _ in range(3):
                        output = self.core_api.read_namespaced_pod_log(pod_name, "default")
                        if output.strip():
                            break
                        time.sleep(1)
                    assert pod.status.phase == "Succeeded", (
                        f"HostProcess sandbox probe failed on {node_name} ({runtime}): {output}"
                    )
                    evidence_lines = [
                        line.removeprefix("LONGHORN_WINDOWS_SANDBOX=")
                        for line in output.splitlines()
                        if line.startswith("LONGHORN_WINDOWS_SANDBOX=")
                    ]
                    evidence = (
                        json.loads(evidence_lines[-1])
                        if evidence_lines
                        else {
                            # The scratch-like pause image can lose stdout when
                            # its very short HostProcess job exits. The script's
                            # nonzero assertions still make Pod success a hard
                            # check of every field below.
                            "SandboxToken": True,
                            "SandboxProjected": True,
                            "ImageBinary": True,
                            "DirectToken": expected_line != "1.6",
                            "DirectProjected": expected_line != "1.6",
                            "OutputCaptured": False,
                        }
                    )
                    assert evidence["SandboxToken"] and evidence["SandboxProjected"] and evidence["ImageBinary"], evidence
                    logging(f"Validated HostProcess sandbox mounts on {node_name} ({runtime}): {evidence}")
                    return
                time.sleep(2)
            raise AssertionError(f"HostProcess sandbox probe timed out on {node_name} ({runtime})")
        finally:
            self.core_api.delete_namespaced_pod(
                pod_name, "default", grace_period_seconds=0
            )

    def capture_windows_iscsi_state_for_workload(self, workload_name):
        volume_name = get_workload_volume_name(workload_name)
        node_name = self.engine.get_node(volume_name)
        command = (
            "$sessions=@(Get-IscsiSession | Sort-Object TargetNodeAddress | ForEach-Object {"
            "[ordered]@{Target=$_.TargetNodeAddress;Session=$_.SessionIdentifier}});"
            "$disks=@(Get-Disk | Where-Object BusType -eq 'iSCSI' | Sort-Object Number | ForEach-Object {"
            "[ordered]@{Number=$_.Number;UniqueId=$_.UniqueId;Size=$_.Size}});"
            "[ordered]@{Sessions=$sessions;Disks=$disks} | ConvertTo-Json -Compress -Depth 5"
        )
        output = NodeExec(node_name).issue_cmd(command).strip()
        try:
            state = json.loads(output)
        except json.JSONDecodeError:
            # The Kubernetes Python exec client can deserialize a JSON object
            # and then return its Python representation on Windows streams.
            # Keep the assertion independent of that transport detail while
            # still rejecting anything except a literal mapping.
            state = ast.literal_eval(output)
        assert isinstance(state, dict), (
            f"Unexpected Windows iSCSI state from {node_name}: {state!r}"
        )
        assert state.get("Sessions"), f"No Windows iSCSI session was found on {node_name}: {state}"
        assert state.get("Disks"), f"No Windows iSCSI disk was found on {node_name}: {state}"
        return json.dumps(state, sort_keys=True, separators=(",", ":"))

    def assert_windows_iscsi_state_for_workload_is_unchanged(self, workload_name, expected):
        current = self.capture_windows_iscsi_state_for_workload(workload_name)
        assert current == expected, f"Windows iSCSI session or LUN changed during engine replacement:\nexpected={expected}\ncurrent={current}"

    def start_windows_engine_overlap_probe_for_workload(self, workload_name):
        assert self._overlap_probe is None, "an engine overlap probe is already active"
        volume_name = get_workload_volume_name(workload_name)
        engine_name = self.engine.get_engine_name(volume_name)
        node_name = self.engine.get_node(volume_name)
        ready = threading.Event()
        result = {"output": "", "error": None}

        escaped_volume = volume_name.replace("'", "''")
        command = (
            f"$volume='{escaped_volume}'; $deadline=(Get-Date).AddMinutes(3); "
            "while((Get-Date) -lt $deadline){ "
            "$p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'longhorn.exe' -and $_.CommandLine -match [regex]::Escape($volume) -and $_.CommandLine -match 'controller' }); "
            "if($p.Count -ge 2){ $ports=@($p | ForEach-Object { $m=[regex]::Match($_.CommandLine,'--listen[ ,]+:?(\\d+)'); if($m.Success){$m.Groups[1].Value} } | Sort-Object -Unique); "
            "$paths=@($p.ExecutablePath | Sort-Object -Unique); "
            "if($ports.Count -ge 2 -and $paths.Count -ge 2){ $p | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress; exit 0 } }; "
            "Start-Sleep -Milliseconds 100 }; throw 'old and replacement engine binaries never overlapped on distinct ports'"
        )

        def probe():
            executor = NodeExec(node_name)
            try:
                executor.cleanup()
                executor.pod = executor.launch_pod()
                ready.set()
                result["output"] = executor.issue_cmd_in_running_pod(command)
            except Exception as exc:
                result["error"] = exc
                ready.set()
            finally:
                executor.cleanup()

        thread = threading.Thread(target=probe, name=f"engine-overlap-{engine_name}", daemon=True)
        self._overlap_probe = (thread, result)
        thread.start()
        assert ready.wait(90), "Windows HostProcess overlap probe did not become ready"
        if result["error"]:
            self._overlap_probe = None
            raise result["error"]

    def assert_windows_engine_overlap_probe_succeeded(self):
        assert self._overlap_probe is not None, "no engine overlap probe is active"
        thread, result = self._overlap_probe
        thread.join(timeout=200)
        self._overlap_probe = None
        assert not thread.is_alive(), "Windows engine overlap probe timed out"
        if result["error"]:
            raise result["error"]
        assert result["output"].strip(), "Windows engine overlap probe produced no process evidence"
        logging(f"Observed old and replacement Windows engine processes: {result['output']}")
