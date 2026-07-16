from replica import Replica
from utility.utility import get_retry_count_and_interval
from utility.utility import logging
import time


class replica_keywords:

    def __init__(self):
        self.replica = Replica()

    def validate_replica_setting(self, volume_name, setting_name, value):
        return self.replica.validate_replica_setting(volume_name, setting_name, value)

    def get_replicas(self, volume_name=None, node_name=None, disk_uuid=None):
        return self.replica.get(volume_name, node_name, disk_uuid)

    def wait_for_disk_replica_count(self, volume_name=None, node_name=None, disk_uuid=None, count=None):
        return self.replica.wait_for_disk_replica_count(volume_name, node_name, disk_uuid, count)

    def get_replica_names(self, volume_name, numberOfReplicas=3):
        return self.replica.get_replica_names(volume_name, numberOfReplicas)

    def wait_for_replica_file_size(self, volume_name, expected_size):
        return self.replica.wait_for_replica_file_size(volume_name, expected_size)

    def wait_for_replica_failed(self, volume_name, node_name):
        return self.replica.wait_for_replica_failed(volume_name, node_name)

    def wait_for_volume_replica_nodes(self, volume_name, *expected_nodes):
        retry_count, retry_interval = get_retry_count_and_interval()
        expected = sorted(expected_nodes)
        for attempt in range(retry_count):
            replicas = self.replica.get(volume_name, None)
            actual = sorted(replica.get("spec", {}).get("nodeID", "") for replica in replicas)
            if actual == expected:
                return
            logging(
                f"Waiting for volume {volume_name} replica nodes {expected}; got {actual} ({attempt})"
            )
            time.sleep(retry_interval)
        raise AssertionError(
            f"volume {volume_name} replica nodes are {actual}, expected {expected}"
        )
