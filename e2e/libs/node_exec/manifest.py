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
