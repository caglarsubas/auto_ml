import copy, hashlib, json, os, signal, struct, subprocess, sys, tempfile, time, unittest
from pathlib import Path
import worker_guard as g

FIELDS = dict(
    repository="caglarsubas/auto_ml",
    repository_id="847772133",
    event_name="pull_request",
    run_id="123",
    run_attempt="1",
    sha="a" * 40,
    ref="refs/pull/261/merge",
    actor_id="37515097",
)
POLICY = {"github": FIELDS, "valid_until": time.time() + 600}


def message(github=None):
    return {
        "JobName": "postgresql-runtime",
        "JobDisplayName": "PostgreSQL runtime and metadata",
        "ContextData": {"github": github or FIELDS},
        "secret": "MUST_NEVER_BE_LOGGED",
    }


def body(v):
    return json.dumps(v).encode("utf-16-le")


def typed(d):
    return {"t": 2, "d": [{"k": k, "v": {"s": v}} for k, v in d.items()]}


class GuardTests(unittest.TestCase):
    def test_plain_and_vendor_typed_context(self):
        for v in [message(), message(typed(FIELDS))]:
            self.assertEqual(g.admit(body(v), POLICY)["jobname"], "postgresql-runtime")

    def test_each_authority_field_is_bound(self):
        for key in FIELDS:
            for fault in ["missing", "changed", "nonstring"]:
                d = copy.deepcopy(FIELDS)
                if fault == "missing":
                    d.pop(key)
                else:
                    d[key] = "unexpected" if fault == "changed" else 1
                with (
                    self.subTest(key=key, fault=fault),
                    self.assertRaises((ValueError, KeyError)),
                ):
                    g.admit(body(message(d)), POLICY)

    def test_job_name_expiry_and_unapproved_policy(self):
        for key in ["JobName", "JobDisplayName"]:
            v = message()
            v[key] = "untrusted"
            with self.assertRaises(ValueError):
                g.admit(body(v), POLICY)
        for key, value in [
            ("run_attempt", "2"),
            ("event_name", "workflow_dispatch"),
            ("repository", "other/repo"),
        ]:
            fields = copy.deepcopy(FIELDS)
            fields[key] = value
            p = {"github": fields, "valid_until": time.time() + 600}
            with self.assertRaises(ValueError):
                g.admit(body(message(fields)), p)
        with self.assertRaises(ValueError):
            g.admit(body(message()), {**POLICY, "valid_until": 0})

    def test_policy_cannot_omit_required_claim_or_expire_nonfinite(self):
        for key in FIELDS:
            expected = {**FIELDS, "server_url": "https://github.com"}
            expected.pop(key)
            msg = {**FIELDS, "server_url": "https://github.com"}
            with self.subTest(key=key), self.assertRaises(ValueError):
                g.admit(
                    body(message(msg)),
                    {"github": expected, "valid_until": time.time() + 600},
                )
        for expiry in [float("nan"), float("inf"), True]:
            with self.assertRaises(ValueError):
                g.admit(body(message()), {**POLICY, "valid_until": expiry})

    def test_job_environment_cannot_spoof_server_context(self):
        msg = message({**FIELDS, "repository": "foreign/repo"})
        msg["EnvironmentVariables"] = {
            "GITHUB_REPOSITORY": "caglarsubas/auto_ml",
            "GITHUB_SHA": "a" * 40,
        }
        with self.assertRaises(ValueError):
            g.admit(body(msg), POLICY)

    def test_duplicate_case_and_typed_keys(self):
        v = message()
        v["jobName"] = "other"
        with self.assertRaises(ValueError):
            g.admit(body(v), POLICY)
        v = typed(FIELDS)
        v["d"].append({"k": "Repository", "v": {"s": "other"}})
        with self.assertRaises(ValueError):
            g.admit(body(message(v)), POLICY)
        raw = '{"JobName":"postgresql-runtime","JobName":"other"}'.encode("utf-16-le")
        with self.assertRaises(ValueError):
            g.admit(raw, POLICY)

    def test_wire_fences(self):
        for size in [-1, g.MAX + 2, 1]:
            read, write = os.pipe()
            os.write(write, struct.pack("<ii", 1, size))
            os.close(write)
            with self.assertRaises(ValueError):
                g.frame(read)
            os.close(read)
        read, write = os.pipe()
        os.write(write, b"bad")
        os.close(write)
        with self.assertRaises(EOFError):
            g.frame(read)
        os.close(read)

    def test_invalid_job_never_starts_vendor(self):
        from unittest.mock import patch

        read, write = os.pipe()
        out, send = os.pipe()
        v = message()
        v["JobName"] = "untrusted"
        b = body(v)
        os.write(write, struct.pack("<ii", 1, len(b)) + b)
        with (
            patch.object(
                g.subprocess,
                "Popen",
                side_effect=AssertionError("vendor must not start"),
            ),
            self.assertRaises(ValueError),
        ):
            g.execute(
                ["guard", "spawnclient", str(read), str(send)], POLICY, "not-used"
            )
        for f in [read, write, out, send]:
            os.close(f)

    def test_pre_worker_byte_parity_and_single_use(self):
        with tempfile.TemporaryDirectory(prefix="p162-guard-") as d:
            root = Path(d)
            vendor = root / "vendor"
            vendor.write_text(
                "#!"
                + sys.executable
                + '\nimport os,struct,sys\nf=int(sys.argv[2]);h=os.read(f,8);n=struct.unpack("<ii",h)[1];b=b""\nwhile len(b)<n:b+=os.read(f,n-len(b))\nos.write(int(sys.argv[3]),h+b)\n'
            )
            vendor.chmod(0o700)
            policy = {
                **POLICY,
                "vendor_sha256": hashlib.sha256(vendor.read_bytes()).hexdigest(),
                "used_marker": str(root / "used"),
            }
            (root / "policy.json").write_text(json.dumps(policy))
            src = Path(g.__file__).resolve()
            b = body(message(typed(FIELDS)))
            packet = struct.pack("<ii", 1, len(b)) + b
            read, write = os.pipe()
            out, send = os.pipe()
            harness = (
                "import sys,json;sys.path.insert(0,"
                + repr(str(src.parent))
                + ');import worker_guard as g;raise SystemExit(g.execute(["guard","spawnclient",sys.argv[1],sys.argv[2]],json.load(open(sys.argv[3])),sys.argv[4]))'
            )
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    harness,
                    str(read),
                    str(send),
                    str(root / "policy.json"),
                    str(vendor),
                ],
                pass_fds=(read, send),
            )
            os.close(read)
            os.close(send)
            os.write(write, packet)
            result = b""
            while len(result) < len(packet):
                result += os.read(out, len(packet) - len(result))
            self.assertEqual(p.wait(timeout=10), 0)
            os.close(write)
            os.close(out)
            self.assertEqual(result, packet)
            self.assertTrue((root / "used").exists())
            # A second valid packet cannot start another vendor worker.
            from unittest.mock import patch
            read, write = os.pipe()
            out, send = os.pipe()
            os.write(write, packet)
            with patch.object(g.subprocess, "Popen", side_effect=AssertionError("second worker forbidden")), self.assertRaises(FileExistsError):
                g.execute(["guard", "spawnclient", str(read), str(send)], policy, str(vendor))
            for fd in [read, write, out, send]:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
