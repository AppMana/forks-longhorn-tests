from pathlib import Path
import unittest

from test_framework.cluster.topology import load_topology


TOPOLOGY = Path(__file__).parents[1] / "topologies" / "mixed-rke2.yaml"


class TopologyTest(unittest.TestCase):
    def test_linux_smoke_reuses_the_canonical_server_and_worker(self):
        topology = load_topology(TOPOLOGY, "linux-smoke")
        self.assertEqual(["server-0", "linux-worker-0"], [node.name for node in topology.nodes])

    def test_windows_gate_has_three_windows_replica_nodes(self):
        topology = load_topology(TOPOLOGY, "windows-gate")
        self.assertEqual(5, len(topology.nodes))
        self.assertEqual(3, len([node for node in topology.nodes if node.os == "windows"]))
        self.assertEqual({"ntfs", "refs"}, {node.filesystem for node in topology.nodes if node.os == "windows"})

    def test_full_matches_aws_worker_shape(self):
        topology = load_topology(TOPOLOGY, "full")
        workers = [node for node in topology.nodes if node.role == "agent"]
        self.assertEqual(7, len(topology.nodes))
        self.assertEqual(3, len([node for node in workers if node.os == "linux"]))
        self.assertEqual(2, len([node for node in workers if node.filesystem == "ntfs"]))
        self.assertEqual(1, len([node for node in workers if node.filesystem == "refs"]))

    def test_topology_addresses_and_taps_are_unique(self):
        topology = load_topology(TOPOLOGY, "full")
        self.assertEqual(len(topology.nodes), len({node.data_ip for node in topology.nodes}))
        self.assertEqual(len(topology.nodes), len({node.management_ip for node in topology.nodes}))
        self.assertEqual(len(topology.nodes), len({node.tap for node in topology.nodes}))


if __name__ == "__main__":
    unittest.main()
