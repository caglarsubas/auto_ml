"""Versioned private cache transport; values and driver errors never enter logs.

New installations select the protected file contract explicitly. Historical
REDIS_URL deployments retain their existing configuration until reprovisioned.
"""

import os
import re
import ssl
import stat
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlsplit

from django.core.exceptions import ImproperlyConfigured


def _capture(path, limit):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)
                or not 0 < before.st_size <= limit):
            raise ValueError
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError
        return data.decode("utf-8")


def connection_options(env=None):
    env = os.environ if env is None else env
    name = "DECLARAI_CACHE_URL"
    selected = any(key in env for key in (name, name + "_FILE", "DECLARAI_CACHE_CA_FILE"))
    if not selected:
        return env.get("REDIS_URL", "redis://localhost:6379/0"), {}
    try:
        if "REDIS_URL" in env or name in env or name + "_FILE" not in env:
            raise ValueError
        value = _capture(env[name + "_FILE"], 4096).rstrip("\r\n")
        url = urlsplit(value)
        if (url.scheme != "rediss" or url.hostname != "cache" or url.port != 6379
                or url.username not in (None, "") or not url.password or url.path != "/0"
                or url.query or url.fragment or any(c.isspace() for c in value)
                or re.search(r"%(?![a-fA-F0-9]{2})", url.password)):
            raise ValueError
        password = unquote_to_bytes(url.password).decode("utf-8")
        if len(password) < 32 or len(set(password)) < 5 or any(ord(c) < 32 or ord(c) == 127 for c in password):
            raise ValueError
        ca = _capture(env.get("DECLARAI_CACHE_CA_FILE", ""), 65536)
        # Validate the selected CA locally; Redis performs the live chain and
        # hostname verification. URL query overrides are rejected above.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=ca)
        return value, {"ssl_ca_data": ca, "ssl_cert_reqs": ssl.CERT_REQUIRED, "ssl_check_hostname": True, "ssl_min_version": ssl.TLSVersion.TLSv1_2}
    except (OSError, ValueError, UnicodeError, ssl.SSLError, ImproperlyConfigured):
        raise ImproperlyConfigured("private_cache_configuration_invalid") from None
