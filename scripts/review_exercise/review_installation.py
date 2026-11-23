"""Bindings for an operator-prepared D09 exercise directory on the Mac pilot."""

import hashlib
import json
import re
import subprocess
from types import SimpleNamespace

from case_inputs import (
    API as api_url,
    EXPECTED as expected,
    INSTALLATION,
    REPLAY_SHA,
    ROOT as root,
    payload,
)
from clean_guest import binding as replay_binding, run as replay

replay_description = (
    "The clean reviewer runs on a separate Linux virtual machine. "
    "Only the three approved files enter the network-disabled runner."
)


def verify_runtime(image):
    if not re.fullmatch(r"https://127\.0\.0\.1:[0-9]+/api/", api_url):
        raise RuntimeError("The pilot requires its loopback TLS endpoint.")
    raw = subprocess.check_output(["docker", "image", "inspect", image], stderr=subprocess.DEVNULL, timeout=20)
    (info,) = json.loads(raw)
    source = root / "source/backend/deployment/offline_reproduce.py"
    if (
        info["Id"] != image
        or (info["Architecture"], info["Os"]) != ("amd64", "linux")
        or hashlib.sha256(source.read_bytes()).hexdigest() != REPLAY_SHA
    ):
        raise RuntimeError("Exercise runtime binding changed.")


site = SimpleNamespace(
    api_url=api_url,
    expected=expected,
    root=root,
    payload=payload,
    replay_binding=replay_binding,
    replay=replay,
    replay_description=replay_description,
    verify_runtime=verify_runtime,
    enrollment_command=["docker", "exec", "-i", INSTALLATION, "python", "/tmp/d09-named-reviewer.py"],
)
