import yaml
import os
from abc import ABC, abstractmethod
from node.node import Node
from node_exec import NodeExec


class Base(ABC):

    def __init__(self, mapping=None):
        if mapping:
            self.mapping = mapping
        else:
            run_dir = os.getenv('LONGHORN_TEST_RUN_DIR')
            mapping_path = os.getenv('LONGHORN_TEST_INSTANCE_MAPPING')
            if not mapping_path and run_dir:
                mapping_path = os.path.join(run_dir, 'instance-mapping.json')
            mapping_path = mapping_path or '/tmp/instance_mapping'
            with open(mapping_path, 'r') as f:
                self.mapping = yaml.safe_load(f)
        self.node = Node()

    @abstractmethod
    def reboot_all_nodes(self, shut_down_time_in_sec):
        return NotImplemented

    @abstractmethod
    def reboot_node(self, node_name, shut_down_time_in_sec):
        return NotImplemented

    @abstractmethod
    def reboot_all_worker_nodes(self, shut_down_time_in_sec):
        return NotImplemented

    @abstractmethod
    def power_off_node(self, node_name, waiting):
        return NotImplemented

    @abstractmethod
    def power_on_node(self, node_name):
        return NotImplemented

    @abstractmethod
    def create_snapshot(self, node_name):
        return NotImplemented

    @abstractmethod
    def cleanup_snapshots(self):
        return NotImplemented

    def get_host_log_files(self, node_name, log_path):
        cmd = f"ls -1 {log_path}"
        out = NodeExec(node_name).issue_cmd(cmd)
        return [line.strip() for line in out.strip().splitlines() if line.strip()]
