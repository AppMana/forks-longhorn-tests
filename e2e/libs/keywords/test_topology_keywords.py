import json
import tempfile
import unittest
from pathlib import Path

from topology import (
    load_node_inventory,
    select_nodes_for_operating_systems,
    select_nodes_for_requirements,
)


class TopologySelectionTest(unittest.TestCase):
    def test_windows_engine_with_mixed_replicas(self):
        selected = select_nodes_for_operating_systems(
            ["windows", "windows", "linux"],
            {
                "linux-b": "linux",
                "windows-b": "windows",
                "windows-a": "windows",
                "linux-a": "linux",
            },
        )
        self.assertEqual(["windows-a", "windows-b", "linux-a"], selected)

    def test_missing_role_node_fails(self):
        with self.assertRaisesRegex(AssertionError, "another node matching"):
            select_nodes_for_operating_systems(
                ["windows", "windows"], {"windows-a": "windows"}
            )

    def test_filesystem_requirement_selects_refs_node(self):
        selected = select_nodes_for_requirements(
            [{"os": "windows", "filesystem": "refs"}],
            {
                "windows-ntfs": {"os": "windows", "filesystem": "ntfs"},
                "windows-refs": {"os": "windows", "filesystem": "refs"},
            },
        )
        self.assertEqual(["windows-refs"], selected)

    def test_load_node_inventory_rejects_unknown_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps({"schema_version": 2, "nodes": {}}))
            with self.assertRaisesRegex(AssertionError, "invalid node inventory"):
                load_node_inventory(path)


if __name__ == "__main__":
    unittest.main()
