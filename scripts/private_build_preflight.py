#!/usr/bin/env python3
"""Read-only checks before ONLINE dependency staging, never offline installation.

Uses the current Docker context and system network. Does not pull images,
change DNS/proxies, restart services or qualify an installation. Public response
bodies, exception text, addresses, Docker credentials and environment are omitted.
"""

import argparse
import concurrent.futures
import datetime
import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
from pathlib import Path

ENDPOINTS = {
    "registry-1.docker.io": ("HEAD", "/v2/", {401}),
    "auth.docker.io": ("GET", "/token?service=registry.docker.io", {200}),
    "dns.google": ("HEAD", "/resolve?name=registry-1.docker.io&type=A", {200}),
    "api.github.com": ("HEAD", "/", {200}),
}
PROBE_CAP_SECONDS = 12
SYNTHETIC = ipaddress.ip_network("198.18.0.0/15")


def probe(host):
    method, path, statuses = ENDPOINTS[host]  # Fixed public targets only.
    value = {"host": host, "passed": False, "synthetic_dns": False, "stage": "DNS"}
    client = None
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        value["synthetic_dns"] = any(ipaddress.ip_address(row[4][0]) in SYNTHETIC for row in addresses)
        value["stage"] = "TLS"
        context = ssl.create_default_context()
        client = http.client.HTTPSConnection(host, timeout=8, context=context)
        client.connect()
        value["stage"] = "HTTP"
        client.request(method, path, headers={"User-Agent": "DeclarAI-staging-preflight", "Connection": "close"})
        response = client.getresponse()
        value.update(stage="HTTP", http_status=response.status, passed=response.status in statuses)
    except ssl.SSLCertVerificationError:
        value["failure"] = "certificate_verification"
    except (ssl.SSLError, http.client.HTTPException, OSError, ValueError) as error:
        value["failure"] = "timeout" if isinstance(error, TimeoutError) else "dns" if isinstance(error, socket.gaierror) else "connection"
    finally:
        if client is not None:
            client.close()
    return value


def bounded_probe(host):
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--probe", host],
            capture_output=True, timeout=PROBE_CAP_SECONDS, check=False,
        )
        if result.returncode or len(result.stdout) > 2048:
            raise ValueError
        row = json.loads(result.stdout)
        if (type(row) is not dict or row.get("host") != host
                or type(row.get("passed")) is not bool or type(row.get("synthetic_dns")) is not bool
                or not set(row) <= {"host", "passed", "synthetic_dns", "stage", "http_status", "failure"}
                or row.get("stage") not in {"DNS", "TLS", "HTTP"}
                or row.get("failure") not in {None, "certificate_verification", "timeout", "dns", "connection"}
                or ("http_status" in row and (type(row["http_status"]) is not int or not 100 <= row["http_status"] <= 599))):
            raise ValueError
        return row
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"host": host, "passed": False, "synthetic_dns": False, "stage": "unobserved", "failure": "probe_unavailable"}


def docker_observation():
    try:
        result = subprocess.run(
            ["docker", "version", "--format", '{{json .Server}}'],
            capture_output=True, timeout=10, check=False,
        )
        if result.returncode or len(result.stdout) > 65536:
            raise ValueError
        server = json.loads(result.stdout)
        if (type(server) is not dict or server.get("Os") != "linux"
                or server.get("Arch") not in {"amd64", "arm64"}):
            raise ValueError
        return {"available": True, "os": "linux", "architecture": server["Arch"]}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"available": False, "failure": "docker_engine_unavailable"}


def assess(engine, network):
    if sorted(row["host"] for row in network) != sorted(ENDPOINTS):
        raise ValueError("preflight_endpoint_inventory_mismatch")
    failures = [row for row in network if not row["passed"]]
    hints = []
    if any(row["synthetic_dns"] and row.get("stage") == "TLS" for row in failures):
        hints.append("synthetic_dns_with_tls_failure_check_vpn")
    if not engine["available"]:
        hints.append("check_selected_docker_context_and_engine")
    if failures:
        hints.append("restore_public_https_before_staging")
    return {
        "schema": "private_online_staging_preflight_v1",
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "docker": engine, "public_https": network, "hints": hints,
        "ready_for_online_staging": engine["available"] and not failures,
        "read_only": True, "installation_qualified": False,
        "scope": "current_host_online_staging_only",
        "limitations": ["Does not prove guest, daemon or CDN blob connectivity.",
                        "Synthetic DNS alone is not a failure; some VPNs use it normally.",
                        "Offline installation does not require these public endpoints."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", choices=ENDPOINTS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe(args.probe)))
        return 0
    engine = docker_observation()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ENDPOINTS)) as pool:
        network = list(pool.map(bounded_probe, ENDPOINTS))
    result = assess(engine, network)
    print(json.dumps(result, indent=2))
    return 0 if result["ready_for_online_staging"] else 2


if __name__ == "__main__":
    sys.exit(main())
