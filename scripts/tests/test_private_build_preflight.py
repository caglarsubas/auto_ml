"""Staging diagnostics must distinguish VPN/engine failures without mutations."""
import importlib.util
import io
import json
import socket
import ssl
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "private_build_preflight.py"
spec = importlib.util.spec_from_file_location("private_build_preflight", SCRIPT)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class StagingPreflightTests(unittest.TestCase):
    def rows(self):
        return [dict(host=h, passed=True, synthetic_dns=False, stage="HTTP", http_status=200) for h in p.ENDPOINTS]

    def test_healthy_engine_does_not_clear_broken_vpn(self):
        rows = self.rows()
        rows[0].update(passed=False, synthetic_dns=True, stage="TLS", failure="connection")
        result = p.assess(dict(available=True), rows)
        self.assertFalse(result["ready_for_online_staging"])
        self.assertIn("synthetic_dns_with_tls_failure_check_vpn", result["hints"])
        self.assertNotIn("check_selected_docker_context_and_engine", result["hints"])
        self.assertFalse(result["installation_qualified"])

    def test_synthetic_dns_with_working_tls_is_valid(self):
        rows = self.rows()
        for row in rows:
            row["synthetic_dns"] = True
        result = p.assess(dict(available=True), rows)
        self.assertTrue(result["ready_for_online_staging"])
        self.assertEqual(result["hints"], [])

    def test_missing_engine_stays_separate_from_network(self):
        result = p.assess(dict(available=False), self.rows())
        self.assertFalse(result["ready_for_online_staging"])
        self.assertEqual(result["hints"], ["check_selected_docker_context_and_engine"])

    def test_incomplete_or_duplicate_endpoint_inventory_refused(self):
        for rows in [[], self.rows()[:-1], self.rows() + self.rows()[:1]]:
            with self.assertRaises(ValueError):
                p.assess(dict(available=True), rows)

    def test_http_failure_does_not_claim_tls_failure(self):
        rows = self.rows()
        rows[0].update(passed=False, synthetic_dns=True, stage="HTTP", http_status=503)
        self.assertEqual(p.assess(dict(available=True), rows)["hints"], ["restore_public_https_before_staging"])

    def test_docker_check_only_reads_selected_daemon_metadata(self):
        data = json.dumps(dict(Os="linux", Arch="arm64", Secret="sentinel")).encode()
        with patch.object(p.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, data)) as run:
            result = p.docker_observation()
        self.assertEqual(result, dict(available=True, os="linux", architecture="arm64"))
        self.assertEqual(run.call_args.args[0], ["docker", "version", "--format", '{{json .Server}}'])
        self.assertEqual(run.call_args.kwargs["timeout"], 10)
        self.assertNotIn("sentinel", json.dumps(result))

    def test_missing_invalid_and_timed_out_daemon_never_pass(self):
        for effect in [OSError("sentinel"), subprocess.TimeoutExpired("docker", 10),
                       subprocess.CompletedProcess([], 1, b"sentinel"),
                       subprocess.CompletedProcess([], 0, b"null"),
                       subprocess.CompletedProcess([], 0, b'{"Os":"windows","Arch":"amd64"}')]:
            options = dict(side_effect=effect) if isinstance(effect, Exception) else dict(return_value=effect)
            with self.subTest(effect=type(effect).__name__), patch.object(p.subprocess, "run", **options):
                self.assertEqual(p.docker_observation(), dict(available=False, failure="docker_engine_unavailable"))

    def test_registry_401_expected_and_no_response_body_or_redirect_read(self):
        client = Mock()
        client.getresponse.return_value.status = 401
        with patch.object(p.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("198.18.1.3", 443))]), patch.object(p.http.client, "HTTPSConnection", return_value=client) as connect:
            result = p.probe("registry-1.docker.io")
        self.assertTrue(result["passed"])
        context = connect.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(connect.call_args.args, ("registry-1.docker.io",))
        client.connect.assert_called_once_with()
        self.assertEqual(client.request.call_args.args, ("HEAD", "/v2/"))
        client.getresponse.return_value.read.assert_not_called()
        client.close.assert_called_once_with()

    def test_tls_errors_retain_stage_and_fixed_reason_without_exception_text(self):
        for error in [ssl.SSLCertVerificationError("sentinel"), ssl.SSLError("sentinel"), TimeoutError("sentinel")]:
            client = Mock()
            client.connect.side_effect = error
            with patch.object(p.socket, "getaddrinfo", return_value=[]), patch.object(p.http.client, "HTTPSConnection", return_value=client):
                result = p.probe("api.github.com")
            self.assertFalse(result["passed"])
            self.assertEqual(result["stage"], "TLS")
            self.assertNotIn("sentinel", json.dumps(result))
            client.request.assert_not_called()
            client.close.assert_called_once_with()

    def test_token_endpoint_uses_get_without_reading_or_retaining_token(self):
        client = Mock()
        client.getresponse.return_value.status = 200
        with patch.object(p.socket, "getaddrinfo", return_value=[]), patch.object(p.http.client, "HTTPSConnection", return_value=client):
            result = p.probe("auth.docker.io")
        self.assertTrue(result["passed"])
        self.assertEqual(client.request.call_args.args, ("GET", "/token?service=registry.docker.io"))
        client.getresponse.return_value.read.assert_not_called()

    def test_dns_failure_suppresses_addresses_and_does_not_connect(self):
        with patch.object(p.socket, "getaddrinfo", side_effect=socket.gaierror("sentinel")), patch.object(p.http.client, "HTTPSConnection") as connect:
            result = p.probe("api.github.com")
        self.assertEqual(result["stage"], "DNS")
        self.assertEqual(result["failure"], "dns")
        self.assertNotIn("sentinel", json.dumps(result))
        connect.assert_not_called()

    def test_unknown_target_refused_before_dns(self):
        with patch.object(p.socket, "getaddrinfo") as dns:
            with self.assertRaises(KeyError):
                p.probe("private.invalid")
        dns.assert_not_called()

    def test_probe_child_timeout_no_retry_or_raw_output(self):
        with patch.object(p.subprocess, "run", side_effect=subprocess.TimeoutExpired("sentinel", 12)) as run:
            result = p.bounded_probe("api.github.com")
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], 12)
        self.assertFalse(result["passed"])
        self.assertNotIn("sentinel", json.dumps(result))

    def test_child_report_malformed_or_extra_fields_refused(self):
        valid = self.rows()[-1]
        for value in [[], {**valid, "host": "private.invalid"}, {**valid, "passed": 1},
                      {**valid, "headers": "sentinel"}, {**valid, "failure": "sentinel"}]:
            with patch.object(p.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(value).encode())):
                result = p.bounded_probe("api.github.com")
            self.assertFalse(result["passed"])
            self.assertNotIn("sentinel", json.dumps(result))

    def test_main_runs_only_read_only_observations_and_nonzero_on_failure(self):
        rows = self.rows()
        rows[0]["passed"] = False
        with patch.object(p.sys, "argv", [str(SCRIPT)]), patch.object(p, "docker_observation", return_value=dict(available=True)), patch.object(p, "bounded_probe", side_effect=rows) as probe, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(p.main(), 2)
        self.assertEqual(probe.call_count, len(p.ENDPOINTS))
        result = json.loads(output.getvalue())
        self.assertTrue(result["read_only"])
        self.assertFalse(result["ready_for_online_staging"])


if __name__ == "__main__":
    unittest.main()
