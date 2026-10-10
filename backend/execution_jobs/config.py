"""Explicit dedicated broker; no cache/local fallback or eager execution."""

import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured
from backend.runtime_config import _secret


def load_job_config(profile, env=None):
    env = os.environ if env is None else env
    name = "DECLARAI_JOB_BROKER_URL"
    if name not in env and name + "_FILE" not in env:
        return {"DECLARAI_JOBS_ENABLED": False, "CELERY_BROKER_URL": None}
    value = _secret(env, name)
    try:
        url = urlsplit(value)
        if (
            url.scheme not in {"redis", "rediss"}
            or not url.hostname
            or url.query
            or url.fragment
            or not url.path.removeprefix("/").isdigit()
            or url.port == 0
            or any(c.isspace() for c in value)
        ):
            raise ValueError
        if profile == "private" and url.scheme != "rediss":
            raise ValueError
    except ValueError:
        raise ImproperlyConfigured(
            "DECLARAI_JOB_BROKER_URL: use an explicit Redis database URL; private mode requires TLS"
        ) from None
    tls = None
    if url.scheme == "rediss":
        ca = Path(env.get("DECLARAI_JOB_BROKER_CA_FILE", ""))
        if not ca.is_absolute() or not ca.is_file() or ca.is_symlink():
            raise ImproperlyConfigured("DECLARAI_JOB_BROKER_CA_FILE: use an existing absolute CA certificate file")
        tls = {"ssl_cert_reqs": ssl.CERT_REQUIRED, "ssl_ca_certs": str(ca), "ssl_check_hostname": True}
    return {"DECLARAI_JOBS_ENABLED": True, "CELERY_BROKER_URL": value, "CELERY_BROKER_USE_SSL": tls}
