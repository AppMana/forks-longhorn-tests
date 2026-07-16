import os
import time

from kubernetes import client
from kubernetes.stream import stream

from node_exec.constant import DEFAULT_POD_INTERVAL
from node_exec.constant import DEFAULT_POD_TIMEOUT
from node_exec.constant import HOST_ROOTFS
from node_exec.constant import (
    DEFAULT_IMAGE,
    FIO_IMAGE,
    WINDOWS_DEFAULT_IMAGE,
    WINDOWS_IO_IMAGE,
)
from node_exec.manifest import build_linux_node_exec_pod
from node_exec.manifest import build_windows_node_exec_pod

from utility.utility import logging
from utility.utility import delete_pod, get_pod
from utility.utility import get_retry_count_and_interval


class NodeExec:

    def __init__(self, node_name):
        self.node_name = node_name
        self.core_api = client.CoreV1Api()
        self.retry_count, self.retry_interval = get_retry_count_and_interval()
        node = self.core_api.read_node(node_name)
        self.operating_system = (
            node.metadata.labels.get("kubernetes.io/os")
            or node.status.node_info.operating_system
            or "linux"
        ).lower()

    def cleanup(self):
        if get_pod(self.node_name):
            logging(f"Cleaning up pod {self.node_name}")
            delete_pod(self.node_name)

    def issue_cmd(self, cmd):

        self.cleanup()

        if self._needs_fio(cmd):
            if self.operating_system == "windows":
                image = os.environ.get("WINDOWS_IO_IMAGE", WINDOWS_IO_IMAGE)
                assert image, "WINDOWS_IO_IMAGE must contain diskspd for Windows I/O tests"
                self.pod = self.launch_pod(image)
            else:
                self.pod = self.launch_pod(FIO_IMAGE)
        else:
            self.pod = self.launch_pod()

        logging(f"Issuing command on {self.node_name}: {cmd}")

        if isinstance(cmd, list):
            exec_command = cmd
        elif self.operating_system == "windows":
            exec_command = [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                cmd,
            ]
        else:
            ns_mnt = os.path.join(HOST_ROOTFS, "proc/1/ns/mnt")
            ns_net = os.path.join(HOST_ROOTFS, "proc/1/ns/net")
            exec_command = [
                'nsenter',
                f'--mount={ns_mnt}',
                f'--net={ns_net}',
                '--', 'sh', '-c', cmd
            ]
        for i in range(self.retry_count):
            try:
                res = stream(
                    self.core_api.connect_get_namespaced_pod_exec,
                    self.pod.metadata.name,
                    'default',
                    command=exec_command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False
                )
                logging(f"Issued command: {cmd} on {self.node_name} with result:\n{res}")
                return res
            except Exception as e:
                logging(f"Failed to issue command: {cmd} on {self.node_name} with error: {e}")
                time.sleep(self.retry_interval)
        assert False, f"Failed to issue command: {cmd} on {self.node_name}"

    def _needs_fio(self, cmd):
        if isinstance(cmd, list):
            return any('fio' in str(part) for part in cmd)
        return 'fio' in str(cmd)

    def launch_pod(self, image_name=None):
        if self.operating_system == "windows":
            return self._launch_manifest(
                build_windows_node_exec_pod(
                    self.node_name,
                    image_name
                    or os.environ.get("WINDOWS_NODE_EXEC_IMAGE", WINDOWS_DEFAULT_IMAGE),
                )
            )

        return self._launch_manifest(
            build_linux_node_exec_pod(
                self.node_name,
                image_name or DEFAULT_IMAGE,
            )
        )

    def _launch_manifest(self, pod_manifest):
        pod = self.core_api.create_namespaced_pod(
            body=pod_manifest,
            namespace='default'
        )
        for i in range(DEFAULT_POD_TIMEOUT):
            pod = self.core_api.read_namespaced_pod(
                    name=self.node_name,
                    namespace='default'
                  )
            if pod is not None and pod.status.phase == 'Running':
                break
            time.sleep(DEFAULT_POD_INTERVAL)
        return pod
