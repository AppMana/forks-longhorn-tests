import unittest

from node_exec.manifest import (
    build_linux_node_exec_pod,
    build_windows_node_exec_pod,
    build_windows_sandbox_probe_pod,
)


class NodeExecManifestTest(unittest.TestCase):
    def test_windows_uses_hostprocess(self):
        pod = build_windows_node_exec_pod("win-1", "windows:test")
        spec = pod["spec"]
        self.assertTrue(spec["hostNetwork"])
        self.assertTrue(spec["securityContext"]["windowsOptions"]["hostProcess"])
        self.assertEqual(
            "NT AUTHORITY\\SYSTEM",
            spec["securityContext"]["windowsOptions"]["runAsUserName"],
        )
        self.assertNotIn("volumes", spec)

    def test_linux_retains_privileged_nsenter_container(self):
        pod = build_linux_node_exec_pod("linux-1", "linux:test")
        container = pod["spec"]["containers"][0]
        self.assertTrue(container["securityContext"]["privileged"])
        self.assertEqual("/rootfs", container["volumeMounts"][0]["mountPath"])

    def test_windows_sandbox_probe_checks_both_runtime_mount_contracts(self):
        legacy = build_windows_sandbox_probe_pod("probe", "win-1", "windows:test", 1)
        current = build_windows_sandbox_probe_pod("probe", "win-1", "windows:test", 2)
        legacy_script = legacy["spec"]["containers"][0]["args"][0]
        current_script = current["spec"]["containers"][0]["args"][0]
        self.assertIn("CONTAINER_SANDBOX_MOUNT_POINT", legacy_script)
        self.assertIn("SandboxToken", legacy_script)
        self.assertIn("DirectToken", legacy_script)
        self.assertIn("'1' -eq '1'", legacy_script)
        self.assertIn("'2' -ne '1'", current_script)


if __name__ == "__main__":
    unittest.main()
