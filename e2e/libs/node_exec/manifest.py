from node_exec.constant import HOST_ROOTFS


def _node_affinity(node_name):
    return {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [{
                    "matchExpressions": [{
                        "key": "kubernetes.io/hostname",
                        "operator": "In",
                        "values": [node_name],
                    }]
                }]
            }
        }
    }


def _node_exec_tolerations():
    return [
        {
            "key": "node-role.kubernetes.io/control-plane",
            "operator": "Exists",
            "effect": "NoSchedule",
        },
        {
            "key": "node-role.kubernetes.io/control-plane",
            "operator": "Exists",
            "effect": "NoExecute",
        },
        {
            "key": "node-role.kubernetes.io/etcd",
            "operator": "Exists",
            "effect": "NoSchedule",
        },
        {
            "key": "node-role.kubernetes.io/etcd",
            "operator": "Exists",
            "effect": "NoExecute",
        },
        {
            "key": "node.kubernetes.io/unschedulable",
            "operator": "Exists",
            "effect": "NoSchedule",
        },
    ]


def build_windows_node_exec_pod(node_name, image_name):
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": node_name},
        "spec": {
            "affinity": _node_affinity(node_name),
            "hostNetwork": True,
            "restartPolicy": "Never",
            "tolerations": _node_exec_tolerations(),
            "securityContext": {
                "windowsOptions": {
                    "hostProcess": True,
                    "runAsUserName": "NT AUTHORITY\\SYSTEM",
                }
            },
            "containers": [{
                "image": image_name,
                "imagePullPolicy": "IfNotPresent",
                "name": "node-exec",
                "command": ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"],
                "args": ["Start-Sleep -Seconds 2147483"],
            }],
        },
    }


def build_windows_sandbox_probe_pod(pod_name, node_name, image_name, expected_containerd_major):
    script = r"""
$ErrorActionPreference = 'Stop'
$sandbox = $env:CONTAINER_SANDBOX_MOUNT_POINT
$relativeToken = Join-Path $sandbox 'var\run\secrets\kubernetes.io\serviceaccount\token'
$directToken = 'C:\var\run\secrets\kubernetes.io\serviceaccount\token'
$imagePowerShell = Join-Path $sandbox 'Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$result = [ordered]@{
    Sandbox = $sandbox
    SandboxToken = Test-Path $relativeToken
    DirectToken = Test-Path $directToken
    ImageBinary = Test-Path $imagePowerShell
}
$result | ConvertTo-Json -Compress
if (-not $result.SandboxToken) { throw "service-account token is absent below $sandbox" }
if (-not $result.ImageBinary) { throw "image binary is absent below $sandbox" }
if ('%s' -eq '1' -and $result.DirectToken) { throw 'containerd 1.6 unexpectedly exposed the projected token at its absolute mount path' }
if ('%s' -ne '1' -and -not $result.DirectToken) { throw 'containerd 1.7+ did not expose the projected token at its absolute mount path' }
""" % (expected_containerd_major, expected_containerd_major)
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": pod_name},
        "spec": {
            "nodeName": node_name,
            "hostNetwork": True,
            "restartPolicy": "Never",
            "tolerations": _node_exec_tolerations(),
            "securityContext": {
                "windowsOptions": {
                    "hostProcess": True,
                    "runAsUserName": "NT AUTHORITY\\SYSTEM",
                }
            },
            "containers": [{
                "image": image_name,
                "imagePullPolicy": "IfNotPresent",
                "name": "sandbox-probe",
                "command": ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"],
                "args": [script],
            }],
        },
    }


def build_linux_node_exec_pod(node_name, image_name):
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": node_name},
        "spec": {
            "affinity": _node_affinity(node_name),
            "tolerations": _node_exec_tolerations(),
            "containers": [{
                "image": image_name,
                "imagePullPolicy": "IfNotPresent",
                "securityContext": {"privileged": True},
                "name": "node-exec",
                "command": ["/bin/bash"],
                "args": ["-c", "tail -f /dev/null"],
                "volumeMounts": [
                    {"name": "rootfs", "mountPath": HOST_ROOTFS},
                    {"name": "bus", "mountPath": "/var/run"},
                    {"name": "rancher", "mountPath": "/var/lib/rancher"},
                ],
            }],
            "volumes": [
                {"name": "rootfs", "hostPath": {"path": "/"}},
                {"name": "bus", "hostPath": {"path": "/var/run"}},
                {"name": "rancher", "hostPath": {"path": "/var/lib/rancher"}},
            ],
        },
    }
