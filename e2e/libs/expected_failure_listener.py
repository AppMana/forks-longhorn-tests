"""Strict expected-failure handling for the mirrored Windows test matrix.

Robot Framework has skip support but no strict xfail primitive. This listener
keeps unsupported parity tests executable: a matching failure becomes XFAIL,
an unexpected pass becomes a failing XPASS, and a different failure remains a
normal failure.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml


class ExpectedFailureListener:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, topology: str, manifest_path: str, report_path: str = ""):
        self.topology = topology
        self.manifest_path = Path(manifest_path)
        self.report_path = Path(
            report_path
            or os.environ.get(
                "LONGHORN_XFAIL_REPORT", "/tmp/test-report/expected-failures.json"
            )
        )
        self.require_all = os.environ.get("LONGHORN_XFAIL_REQUIRE_ALL", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        document = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8")) or {}
        self.entries = document.get("expected_failures", [])
        self.seen: set[str] = set()
        self.results: list[dict[str, Any]] = []
        self.root_suite_id: str | None = None

        ids = [entry.get("id") for entry in self.entries]
        if any(not entry_id for entry_id in ids):
            raise ValueError("every expected failure requires a non-empty id")
        if len(ids) != len(set(ids)):
            raise ValueError("expected failure ids must be unique")
        for entry in self.entries:
            for field in ("topologies", "capability", "issue"):
                if not entry.get(field):
                    raise ValueError(f"expected failure {entry['id']!r} requires {field}")

    def start_suite(self, data: Any, result: Any) -> None:
        del result
        if self.root_suite_id is None:
            self.root_suite_id = data.id

    def end_test(self, data: Any, result: Any) -> None:
        entry = self._match(data, result)
        if entry is None:
            return

        entry_id = entry["id"]
        self.seen.add(entry_id)
        original_status = result.status
        original_message = result.message or ""
        expected_pattern = entry.get("failure_message")

        if original_status == "FAIL":
            if expected_pattern and not re.search(expected_pattern, original_message, re.I | re.S):
                self.results.append(
                    self._record(data, entry, "FAIL", original_message, "failure-reason-mismatch")
                )
                result.message = (
                    f"Expected-failure reason mismatch for {entry_id}: "
                    f"/{expected_pattern}/ did not match.\n{original_message}"
                )
                return

            result.status = "SKIP"
            result.tags.add("xfail")
            result.message = (
                f"XFAIL [{entry['capability']}] {entry['issue']}\n{original_message}"
            )
            self.results.append(self._record(data, entry, "XFAIL", original_message))
            return

        if original_status == "PASS":
            result.status = "FAIL"
            result.tags.add("xpass")
            result.message = (
                f"XPASS: {entry_id} passed under topology {self.topology}. "
                f"Remove the expectation and advertise {entry['capability']} only after "
                f"the capability contract tests pass. Tracking: {entry['issue']}"
            )
            self.results.append(self._record(data, entry, "XPASS", result.message))

    def end_suite(self, data: Any, result: Any) -> None:
        if data.id != self.root_suite_id or not self.require_all:
            return
        applicable = {
            entry["id"]
            for entry in self.entries
            if self._topology_matches(entry.get("topologies", []))
        }
        unused = sorted(applicable - self.seen)
        if unused:
            result.status = "FAIL"
            suffix = "Unused strict expected-failure entries: " + ", ".join(unused)
            result.message = f"{result.message}\n{suffix}" if result.message else suffix

    def close(self) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "topology": self.topology,
            "manifest": str(self.manifest_path),
            "results": self.results,
        }
        self.report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def _match(self, data: Any, result: Any) -> dict[str, Any] | None:
        tags = {str(tag).lower() for tag in result.tags}
        if "capability-negative" in tags:
            return None
        longname = result.longname
        for entry in self.entries:
            if not self._topology_matches(entry.get("topologies", [])):
                continue
            if not fnmatch.fnmatchcase(longname, entry.get("test", "*")):
                continue
            required_tags = {str(tag).lower() for tag in entry.get("tags", [])}
            if not required_tags.issubset(tags):
                continue
            excluded_tags = {str(tag).lower() for tag in entry.get("exclude_tags", [])}
            if excluded_tags.intersection(tags):
                continue
            return entry
        return None

    def _topology_matches(self, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatchcase(self.topology, pattern) for pattern in patterns)

    def _record(
        self,
        data: Any,
        entry: dict[str, Any],
        status: str,
        message: str,
        detail: str = "",
    ) -> dict[str, Any]:
        return {
            "test": data.longname,
            "expectation": entry["id"],
            "status": status,
            "capability": entry["capability"],
            "issue": entry["issue"],
            "detail": detail,
            "message": message,
        }

