"""Run trusted qualification tests with the already-verified application image.

The two pure-Python qualification tools are an explicit, hashed overlay. No
application dependency, test inventory, numerical workload or timeout changes.
This is a disposable test controller, not an installed service or expert sandbox.
"""

import hashlib
import importlib.metadata as metadata
import json
import os
import platform
from pathlib import Path

from private_api_package import allowed_source, inspect_image, native_manifest, read_source

TOOLS = {"execnet": ("execnet", "2.1.2"), "pytest-xdist": ("xdist", "3.8.0")}
PREFIXES = ("DECLARAI_", "DJANGO_", "LLM_ENGINE_", "OPENAI_", "REDIS_", "PROMETA_", "OMP_", "OPENBLAS_", "MKL_")


def stage_tools(destination, lookup=None):
    """Copy only the two installed tool distributions; never a host site directory."""
    destination.mkdir(mode=0o700, exist_ok=False)
    hashes, versions, total = {}, {}, 0
    for name, (package, version) in TOOLS.items():
        distribution = (lookup or metadata.distribution)(name)
        if distribution.version != version or not distribution.files:
            raise ValueError("native_suite_tool_version")
        versions[name] = version
        selected = []
        for member in distribution.files:
            path = Path(str(member))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("native_suite_tool_path")
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.parts[0] != package and not path.parts[0].startswith(name.replace("-", "_") + "-"):
                raise ValueError("native_suite_tool_path")
            if path.parts[0] != package and not path.parts[0].endswith(".dist-info"):
                raise ValueError("native_suite_tool_path")
            source = Path(distribution.locate_file(member))
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024**2:
                raise ValueError("native_suite_tool_file")
            raw = source.read_bytes()
            total += len(raw)
            if total > 16 * 1024**2 or len(hashes) >= 1024 or path.as_posix() in hashes:
                raise ValueError("native_suite_tool_budget")
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o444)
            hashes[path.as_posix()] = hashlib.sha256(raw).hexdigest()
            selected.append(path)
        if not any(path.parts[0] == package for path in selected):
            raise ValueError("native_suite_tool_package")
        if not any(path.name == "METADATA" and path.parts[0].endswith(".dist-info") for path in selected):
            raise ValueError("native_suite_tool_metadata")
    return {"versions": versions, "files_sha256": dict(sorted(hashes.items()))}


def prepare(image, *, root, fixture, name, environment):
    if platform.system() != "Linux":
        raise ValueError("native_suite_linux_required")
    info = inspect_image(image)
    if image != info["Id"] or info["Config"]["User"] != "10001:10001":
        raise ValueError("native_suite_exact_application_image_required")
    runtime = native_manifest(image)
    if runtime["machine"] != platform.machine() or runtime["implementation"] != "CPython":
        raise ValueError("native_suite_native_runtime_required")
    sources = {path: checksum for path, checksum in runtime["source_sha256"].items() if path != "source-manifest.json"}
    if not sources or any(not allowed_source(path) or hashlib.sha256(read_source(root, path)).hexdigest() != checksum
                          for path, checksum in sources.items()):
        raise ValueError("native_suite_application_source_changed")
    overlay = fixture / "native-suite-tools"
    tools = stage_tools(overlay)
    selected = {k: str(v) for k, v in environment.items() if k.startswith(PREFIXES)}
    selected["PYTHONPATH"] = "/opt/declarai-qualification"
    if any("\n" in k + v or "\r" in k + v or "\x00" in k + v for k, v in selected.items()):
        raise ValueError("native_suite_environment")
    env_file = fixture / "native-suite.env"
    env_file.write_text("".join(f"{key}={value}\n" for key, value in sorted(selected.items())))
    env_file.chmod(0o600)
    affinity = sorted(os.sched_getaffinity(0))
    if not affinity:
        raise ValueError("native_suite_cpu_affinity")
    argv = [
        "docker", "run", "--rm", "--pull", "never", "--name", name,
        "--network", "host", "--user", f"{os.getuid()}:{os.getgid()}",
        "--cpuset-cpus", ",".join(map(str, affinity)),
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--env-file", str(env_file),
        "--mount", f"type=bind,src={root},dst={root}",
        "--mount", f"type=bind,src={fixture},dst={fixture}",
        "--mount", f"type=bind,src={overlay},dst=/opt/declarai-qualification,readonly",
        "--workdir", str(root / "backend"), "--entrypoint", "python", image,
    ]
    receipt = {
        "schema": "private_native_suite_runtime_v1", "application_image_id": image,
        "python": runtime["python"], "implementation": runtime["implementation"],
        "machine": runtime["machine"], "system": runtime["system"],
        "application_runtime_manifest_sha256": hashlib.sha256(json.dumps(runtime, sort_keys=True).encode()).hexdigest(),
        "qualification_tools": tools, "cpu_affinity": affinity,
        "workers": 2, "scheduling": "loadfile", "worker_restarts": 0,
        "timeout_seconds": 900, "application_dependencies_replaced": False,
        "host_site_packages_mounted": False, "credentials_in_receipt": False,
        "application_source_files_verified": len(sources),
        "application_source_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
        "installed_service_or_customer_qualification": False,
    }
    return argv, receipt
