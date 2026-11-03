"""Boundary tests for owned installation acceptance evidence."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify_private_installation_backup as backup
import qualify_private_installation_workflow as workflow
import qualify_private_installation_plan as installation


class BackupFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def rejected(self, code):
        with self.assertRaisesRegex(workflow.schema_init.checker.planner.PlanError, code):
            backup.artifact_bytes(self.root)

    def test_regular_nested_snapshot_preserves_bytes(self):
        (self.root / "nested").mkdir()
        (self.root / "nested" / "data.csv").write_bytes(b"x,y\n1,2\n")
        expected = {"nested/data.csv": b"x,y\n1,2\n"}
        self.assertEqual(backup.artifact_bytes(self.root), expected)
        self.assertEqual(backup.artifact_bytes(self.root), expected)

    def test_empty_snapshot_is_not_baseline_evidence(self):
        self.rejected("backup_artifacts_empty")

    def test_file_symlink_is_not_followed(self):
        (self.root / "link").symlink_to("/etc/passwd")
        self.rejected("backup_symlink")

    def test_directory_symlink_is_not_followed(self):
        (self.root / "link").symlink_to(self.root, target_is_directory=True)
        self.rejected("backup_symlink")

    def test_hardlinked_file_is_refused(self):
        path = self.root / "source"
        path.write_bytes(b"retained")
        os.link(path, self.root / "alias")
        self.rejected("backup_file")

    def test_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.root / "fifo")
        self.rejected("backup_file")

    def test_total_budget_is_enforced(self):
        for name in ("first", "second"):
            (self.root / name).write_bytes(b"1234")
        with patch.object(backup, "MAX_BYTES", 7):
            self.rejected("backup_budget")

    def test_missing_root_is_refused(self):
        with self.assertRaisesRegex(workflow.schema_init.checker.planner.PlanError, "backup_root"):
            backup.artifact_bytes(self.root / "missing")


class OwnedWorkflow(unittest.TestCase):
    def test_arbitrary_operator_root_is_refused_before_access(self):
        with self.assertRaisesRegex(workflow.schema_init.checker.planner.PlanError, "scope_required"):
            workflow.owned({"request": {"root": "/srv/operator/installation"}}, Path("/srv/operator"))

    def test_no_non_api_session_request(self):
        session = object.__new__(workflow.Session)
        with self.assertRaisesRegex(workflow.schema_init.checker.planner.PlanError, "path_invalid"):
            session.request("GET", "https://example.com/")


class NativeProfile(unittest.TestCase):
    def test_each_architecture_is_bound_to_its_own_bundle(self):
        for machine, image in (("x86_64", "amd64"), ("aarch64", "arm64")):
            with self.subTest(machine=machine):
                profile = {"architecture": machine, "os_release": {"ID": "ubuntu", "VERSION_ID": "24.04"}}
                self.assertTrue(installation.qualification_profile_matches(profile, image))

    def test_foreign_architecture_or_os_cannot_gain_qualification(self):
        for machine, image, system, release in (("x86_64", "arm64", "ubuntu", "24.04"),
                ("aarch64", "amd64", "ubuntu", "24.04"), ("unknown", "unknown", "ubuntu", "24.04"),
                ("aarch64", "arm64", "debian", "24.04"), ("aarch64", "arm64", "ubuntu", "22.04")):
            with self.subTest(machine=machine, image=image, system=system, release=release):
                profile = {"architecture": machine, "os_release": {"ID": system, "VERSION_ID": release}}
                self.assertFalse(installation.qualification_profile_matches(profile, image))


if __name__ == "__main__":
    unittest.main()
