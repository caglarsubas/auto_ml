import copy, json, subprocess, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import verify_profile as p


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p162-profile-test-")
        self.root = Path(self.tmp.name)
        self.key = self.root / "key"
        self.pub = self.root / "pub"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.key), "-pubout", "-out", str(self.pub)],
            check=True,
            capture_output=True,
        )
        self.scope = {
            "repository": "caglarsubas/auto_ml",
            "run_id": 123,
            "run_attempt": 1,
            "event": "pull_request",
            "execution_sha": "a" * 40,
            "job": "postgresql-runtime",
        }
        self.value = {
            "schema": p.SCHEMA,
            "scope": self.scope,
            "issued_at": time.time() - 5,
            "expires_at": time.time() + 600,
            "execution": {
                "instruction_set_emulation": True,
                "native_amd64_hardware_qualified": False,
                "pytest_workers": 2,
                "native_child_cap_seconds": 900,
            },
            "guest": {
                "system": "Linux",
                "os_version": "24.04",
                "architecture": "x86_64",
                "vCPUs": 4,
                "memory_MiB": 16384,
                "free_disk_bytes": 120 * 10**9,
            },
            "physical_host": {"system": "Darwin", "architecture": "arm64"},
            "isolation": {
                "host_workspace_shares": False,
                "host_Docker_socket": False,
                "routed_guest_network": False,
                "disposable_VM": True,
                "pre_worker_admission": True,
            },
        }

    def tearDown(self):
        self.tmp.cleanup()

    def sign(self, value):
        raw = p.canonical(value)
        (self.root / "data").write_bytes(raw)
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.key),
                "-rawin",
                "-in",
                str(self.root / "data"),
                "-out",
                str(self.root / "sig"),
            ],
            check=True,
            capture_output=True,
        )
        return raw, (self.root / "sig").read_bytes()

    def test_real_signature_and_scope(self):
        raw, sig = self.sign(self.value)
        self.assertEqual(p.verify(raw, sig, self.pub, self.scope), self.value)

    def test_tampering_and_wrong_run_rejected(self):
        raw, sig = self.sign(self.value)
        wrong = copy.deepcopy(self.value)
        wrong["scope"]["run_id"] = 999
        with self.assertRaises(ValueError):
            p.verify(p.canonical(wrong), sig, self.pub, self.scope)
        with self.assertRaises(ValueError):
            p.verify(raw, sig, self.pub, {**self.scope, "execution_sha": "b" * 40})

    def test_even_validly_signed_relaxed_controls_are_rejected(self):
        for k, v in [
            ("native_child_cap_seconds", 901),
            ("pytest_workers", 3),
            ("native_amd64_hardware_qualified", True),
            ("instruction_set_emulation", False),
        ]:
            wrong = copy.deepcopy(self.value)
            wrong["execution"][k] = v
            raw, sig = self.sign(wrong)
            with self.subTest(k=k), self.assertRaises(ValueError):
                p.verify(raw, sig, self.pub, self.scope)

    def test_signed_private_shares_and_wrong_platform_rejected(self):
        for group, key, value in [
            ("isolation", "host_workspace_shares", True),
            ("isolation", "host_Docker_socket", True),
            ("isolation", "routed_guest_network", True),
            ("guest", "architecture", "arm64"),
            ("guest", "free_disk_bytes", 99 * 10**9),
        ]:
            wrong = copy.deepcopy(self.value)
            wrong[group][key] = value
            raw, sig = self.sign(wrong)
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.verify(raw, sig, self.pub, self.scope)

    def test_expired_or_unbounded_lease_rejected(self):
        for delta in [-10, 10000]:
            wrong = copy.deepcopy(self.value)
            wrong["expires_at"] = time.time() + delta
            raw, sig = self.sign(wrong)
            with self.assertRaises(ValueError):
                p.verify(raw, sig, self.pub, self.scope)


if __name__ == "__main__":
    unittest.main()
