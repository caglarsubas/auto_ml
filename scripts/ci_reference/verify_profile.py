"""Verify the host controller's signed, revision-bound experimental CI profile."""

import argparse, datetime, hashlib, json, math, os, platform, subprocess, tempfile, time
from pathlib import Path

SCHEMA = "declarai_mac_ci_reference_profile_v1"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def verify(raw, signature, pub, expected, at=None):
    value = json.loads(raw)
    assert canonical(value) == raw
    with tempfile.TemporaryDirectory(prefix="p162-profile-") as folder:
        f = Path(folder)
        (f / "profile").write_bytes(raw)
        (f / "signature").write_bytes(signature)
        checked = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(pub),
                "-rawin",
                "-in",
                str(f / "profile"),
                "-sigfile",
                str(f / "signature"),
            ],
            capture_output=True,
            timeout=10,
        )
        if checked.returncode:
            raise ValueError("profile_signature_invalid")
    if value["schema"] != SCHEMA or canonical(value["scope"]) != canonical(expected):
        raise ValueError("profile_scope_invalid")
    now = time.time() if at is None else at
    if not all(
        type(value[k]) in (int, float) and math.isfinite(value[k])
        for k in ["issued_at", "expires_at"]
    ):
        raise ValueError("profile_time_invalid")
    if (
        not value["issued_at"] <= now <= value["expires_at"]
        or value["expires_at"] - value["issued_at"] > 7200
    ):
        raise ValueError("profile_expired")
    e = value["execution"]
    g = value["guest"]
    h = value["physical_host"]
    i = value["isolation"]
    if e != {
        "instruction_set_emulation": True,
        "native_amd64_hardware_qualified": False,
        "pytest_workers": 2,
        "native_child_cap_seconds": 900,
    }:
        raise ValueError("profile_controls_invalid")
    if (
        h["system"] != "Darwin"
        or h["architecture"] != "arm64"
        or g["system"] != "Linux"
        or g["os_version"] != "24.04"
        or g["architecture"] != "x86_64"
        or g["vCPUs"] != 4
        or g["memory_MiB"] != 16384
        or g["free_disk_bytes"] < 100 * 10**9
    ):
        raise ValueError("profile_platform_invalid")
    if (
        any(
            i[k] is not False
            for k in [
                "host_workspace_shares",
                "host_Docker_socket",
                "routed_guest_network",
            ]
        )
        or i["disposable_VM"] is not True
        or i["pre_worker_admission"] is not True
    ):
        raise ValueError("profile_isolation_invalid")
    return value


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--output", required=True)
    args = a.parse_args()
    scope = {
        "repository": os.environ["GITHUB_REPOSITORY"],
        "run_id": int(os.environ["GITHUB_RUN_ID"]),
        "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "event": os.environ["GITHUB_EVENT_NAME"],
        "execution_sha": os.environ["GITHUB_SHA"],
        "job": os.environ["GITHUB_JOB"],
    }
    pub = Path(__file__).with_name("pilot-public.pem")
    root = Path("/opt/declarai-pilot")
    raw = (root / "execution-profile.json").read_bytes()
    v = verify(raw, (root / "execution-profile.sig").read_bytes(), pub, scope)
    if (
        platform.system() != "Linux"
        or platform.machine() != "x86_64"
        or os.cpu_count() != 4
        or 'VERSION_ID="24.04"' not in Path("/etc/os-release").read_text()
    ):
        raise ValueError("observed_platform_invalid")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for source in ["execution-profile.json", "execution-profile.sig"]:
        (out / source).write_bytes((root / source).read_bytes())
    (out / "profile-verification.json").write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "controller_signature_verified": True,
                "scope": scope,
                "verified_at": time.time(),
                "public_key_sha256": hashlib.sha256(pub.read_bytes()).hexdigest(),
                "profile_sha256": hashlib.sha256(raw).hexdigest(),
                "emulated": True,
                "native_amd64_hardware_qualified": False,
                "pytest_workers": 2,
                "native_child_cap_seconds": 900,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "P162 Mac-hosted Ubuntu 24.04 amd64 profile verified; emulated execution, not native amd64 hardware."
    )


if __name__ == "__main__":
    main()
