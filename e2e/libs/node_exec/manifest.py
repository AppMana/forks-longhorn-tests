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


def build_windows_sandbox_probe_pod(pod_name, node_name, image_name, expected_containerd_line):
    script = r"""
$ErrorActionPreference = 'Stop'
# hcsshim 0.9.x substitutes this token into the command line before launching
# PowerShell. Quote it so the resulting C:/C/<sandbox> value remains a string
# expression instead of being parsed as a command.
$sandbox = "$env:CONTAINER_SANDBOX_MOUNT_POINT"
$relativeToken = Join-Path $sandbox 'var\run\secrets\kubernetes.io\serviceaccount\token'
$directToken = 'C:\var\run\secrets\kubernetes.io\serviceaccount\token'
$relativeProjected = Join-Path $sandbox 'probe-projected\pod-name'
$directProjected = 'C:\probe-projected\pod-name'
$imagePause = Join-Path $sandbox 'pause.exe'
$result = [ordered]@{
    Sandbox = $sandbox
    SandboxToken = Test-Path $relativeToken
    SandboxProjected = Test-Path $relativeProjected
    DirectToken = Test-Path $directToken
    DirectProjected = Test-Path $directProjected
    ImageBinary = Test-Path $imagePause
}
Write-Output ('LONGHORN_WINDOWS_SANDBOX=' + ($result | ConvertTo-Json -Compress))
if (-not $result.SandboxToken) { throw "service-account token is absent below $sandbox" }
if (-not $result.SandboxProjected) { throw "projected volume is absent below $sandbox" }
if (-not $result.ImageBinary) { throw "image binary is absent below $sandbox" }
if ('%s' -eq '1.6' -and ($result.DirectToken -or $result.DirectProjected)) { throw 'containerd 1.6 unexpectedly exposed a projected file at its absolute mount path' }
if ('%s' -ne '1.6' -and (-not $result.DirectToken -or -not $result.DirectProjected)) { throw 'containerd 1.7+ did not expose a projected file at its absolute mount path' }
# Give the Windows HostProcess shim time to drain the short-lived process pipe
# into the CRI log before the job object exits.
Start-Sleep -Seconds 2
""" % (expected_containerd_line, expected_containerd_line)
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
                "volumeMounts": [{
                    "name": "probe-projected",
                    "mountPath": "C:\\probe-projected",
                    "readOnly": True,
                }],
            }],
            "volumes": [{
                "name": "probe-projected",
                "projected": {
                    "sources": [{
                        "downwardAPI": {
                            "items": [{
                                "path": "pod-name",
                                "fieldRef": {"fieldPath": "metadata.name"},
                            }]
                        }
                    }]
                },
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
