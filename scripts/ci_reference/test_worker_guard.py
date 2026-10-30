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
IDENTITY = dict(schema='declarai_verified_workflow_job_identity_v1',workflow_sha256='475f23a91669b7a590c285e19f914ddd9f2be27234a1a36a694e707490c9cc7b',job_key='postgresql-runtime',display_name='PostgreSQL runtime and metadata',declared_jobs=6,API_job_id=1,source_head='a'*40,run_id='123',unique_display_verified=True)
POLICY = {"github": FIELDS, "valid_until": time.time() + 600, "job_identity": IDENTITY}


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
    def test_internal_job_name_is_opaque_under_verified_unique_identity(self):
        for value in ['opaque-server-label',None,'postgresql_runtime']:
            v=message();v['JobName']=value
            self.assertEqual(g.admit(body(v),POLICY)['jobdisplayname'],IDENTITY['display_name'])
        v=message();del v['JobName']
        self.assertEqual(g.admit(body(v),POLICY)['jobdisplayname'],IDENTITY['display_name'])

    def test_missing_or_forged_identity_proof_is_refused(self):
        for key in IDENTITY:
            proof=dict(IDENTITY);proof.pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):
                g.admit(body(message()),{**POLICY,'job_identity':proof})
        for key,value in [('workflow_sha256','b'*64),('unique_display_verified',1),('API_job_id',True),('API_job_id',0),('declared_jobs',True),('run_id','999'),('source_head','not-a-sha'),('job_key','other'),('display_name','other'),('schema','other')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                g.admit(body(message()),{**POLICY,'job_identity':{**IDENTITY,key:value}})
        with self.assertRaises(ValueError):g.admit(body(message()),{k:v for k,v in POLICY.items() if k!='job_identity'})
    def test_claim_diagnostics_emit_only_fixed_names_and_results(self):
        secret='PRIVATE_JOB_VALUE_NEVER_LOG'
        github={**FIELDS,'sha':secret,'actor_id':{'t':4,'n':secret},'extra_secret':secret}
        del github['ref']
        checks=g.claim_checks(body(message(github)),POLICY)
        self.assertEqual(checks['sha'],'mismatch')
        self.assertEqual(checks['actor_id'],'invalid_type')
        self.assertEqual(checks['ref'],'absent')
        self.assertNotIn(secret,json.dumps(checks))
        self.assertNotIn('extra_secret',checks)
        self.assertEqual(g.claim_checks(b'bad',POLICY),{'context_structure':'invalid'})

    def test_main_diagnostic_never_logs_exception_text_or_payload(self):
        import contextlib,io
        from unittest.mock import patch
        for error in [ValueError('PRIVATE_SECRET'),OSError(9,'PRIVATE_SECRET'),RuntimeError('PRIVATE_SECRET')]:
            out=io.StringIO()
            def fail(*a,**kw):
                kw['report'](stage='frame')
                raise error
            with patch.object(g,'load_policy',return_value=POLICY),patch.object(g,'execute',side_effect=fail),contextlib.redirect_stderr(out):
                self.assertEqual(g.main(),78)
            self.assertNotIn('PRIVATE_SECRET',out.getvalue())
            record=json.loads(out.getvalue().splitlines()[0].removeprefix('P162_ADMISSION_DIAGNOSTIC '))
            self.assertEqual(record['stage'],'frame')

    def test_invalid_authority_reports_scope_then_refuses_vendor(self):
        from unittest.mock import patch
        read,write=os.pipe();out,send=os.pipe()
        b=body(message({**FIELDS,'sha':'UNAPPROVED_SECRET_REVISION'}));os.write(write,struct.pack('<ii',1,len(b))+b)
        reports=[]
        try:
            with patch.object(g.subprocess,'Popen',side_effect=AssertionError('must not start')),self.assertRaises(ValueError):
                g.execute(['guard','spawnclient',str(read),str(send)],POLICY,'unused',report=lambda **v:reports.append(v))
        finally:
            for fd in [read,write,out,send]:os.close(fd)
        self.assertEqual(reports[-1]['claims']['sha'],'mismatch')
        self.assertNotIn('UNAPPROVED_SECRET_REVISION',json.dumps(reports))

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
        for key in ["JobDisplayName"]:
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
            p = {"github": fields, "valid_until": time.time() + 600, "job_identity": IDENTITY}
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
                    {"github": expected, "valid_until": time.time() + 600, "job_identity": IDENTITY},
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
        v["JobDisplayName"] = "untrusted"
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
