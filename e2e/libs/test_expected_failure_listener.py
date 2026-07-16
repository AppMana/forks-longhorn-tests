import tempfile
import unittest
from pathlib import Path

import yaml

from e2e.libs.expected_failure_listener import ExpectedFailureListener


class FakeTags(set):
    pass


class FakeTest:
    id = "s1-t1"
    longname = "Longhorn Tests.Regression.Test RWX"


class FakeResult:
    def __init__(self, status, message=""):
        self.status = status
        self.message = message
        self.tags = FakeTags({"rwx"})
        self.longname = FakeTest.longname


class ExpectedFailureListenerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.manifest = root / "expected-failures.yaml"
        self.report = root / "report.json"
        self.manifest.write_text(
            yaml.safe_dump(
                {
                    "expected_failures": [
                        {
                            "id": "windows-rwx",
                            "test": "*RWX",
                            "tags": ["rwx"],
                            "topologies": ["windows"],
                            "capability": "access-mode:rwx",
                            "issue": "issue-1",
                            "failure_message": "unschedulable",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.listener = ExpectedFailureListener(
            "windows", str(self.manifest), str(self.report)
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_expected_failure_becomes_xfail(self):
        result = FakeResult("FAIL", "volume is unschedulable")
        self.listener.end_test(FakeTest(), result)
        self.assertEqual("SKIP", result.status)
        self.assertIn("xfail", result.tags)

    def test_unexpected_pass_is_strict_failure(self):
        result = FakeResult("PASS")
        self.listener.end_test(FakeTest(), result)
        self.assertEqual("FAIL", result.status)
        self.assertIn("XPASS", result.message)

    def test_wrong_failure_reason_remains_failure(self):
        result = FakeResult("FAIL", "connection refused")
        self.listener.end_test(FakeTest(), result)
        self.assertEqual("FAIL", result.status)
        self.assertIn("reason mismatch", result.message)


if __name__ == "__main__":
    unittest.main()
