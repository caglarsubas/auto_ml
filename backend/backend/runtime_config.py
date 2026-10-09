"""Explicit runtime configuration. Invalid private settings stop before startup."""

import ipaddress
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

DEVELOPMENT_ORIGINS = "http://localhost:4200,http://localhost:4300,http://localhost:4301,http://127.0.0.1:4301"


def _error(name, message):
    # Never interpolate credential values, connection strings or secret paths.
    raise ImproperlyConfigured(f"{name}: {message}")


def _boolean(env, name, default=False):
    value = env.get(name)
    if value is None:
        return default
    if value.lower() not in ("true", "false"):
        _error(name, "use true or false")
    return value.lower() == "true"


def _integer(env, name, default, low, high):
    value = env.get(name, str(default))
    if not re.fullmatch(r"[0-9]+", value) or not low <= int(value) <= high:
        _error(name, f"use an integer between {low} and {high}")
    return int(value)


def _secret(env, name, default=None):
    direct, file_name = env.get(name), env.get(name + "_FILE")
    if direct is not None and file_name is not None:
        _error(name, "configure the value or its _FILE source, not both")
    if file_name is not None:
        try:
            descriptor = os.open(file_name, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 4096:
                    raise ValueError
                direct = stream.read(4097).decode("utf-8").rstrip("\r\n")
        except (OSError, ValueError, UnicodeError):
            _error(name, "use a readable regular UTF-8 secret file of at most 4096 bytes")
    value = default if direct is None else direct
    if not value or len(value) > 4096 or any(c in value for c in "\x00\r\n"):
        _error(name, "a nonempty single-line secret is required")
    return value


def _hosts(value, name):
    hosts = [item.strip() for item in value.split(",") if item.strip()]
    for host in hosts:
        # DNS, IPv4 and bracketed IPv6 literals; no URL, wildcard, port or credentials.
        try:
            if host.startswith("[") and host.endswith("]"):
                ipaddress.IPv6Address(host[1:-1])
            elif re.fullmatch(r"[0-9.]+", host):
                ipaddress.IPv4Address(host)
            elif len(host) > 253 or not all(
                re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in host.split(".")
            ):
                raise ValueError
        except ValueError:
            _error(name, "use explicit hostnames or IP literals without wildcards, schemes or ports")
    if not hosts:
        _error(name, "at least one explicit host is required")
    return list(dict.fromkeys(hosts))


def _origins(value, private):
    result = []
    for item in value.split(","):
        origin = item.strip()
        if not origin:
            continue
        try:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in (("https",) if private else ("http", "https"))
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or any(c.isspace() or c == "\x00" for c in origin)
                or parsed.port == 0
            ):
                raise ValueError
            _hosts(
                parsed.hostname if ":" not in parsed.hostname else "[" + parsed.hostname + "]",
                "DECLARAI_ALLOWED_ORIGINS",
            )
        except ValueError:
            _error(
                "DECLARAI_ALLOWED_ORIGINS",
                "use explicit HTTPS origins in private mode; no credentials, paths or wildcards",
            )
        result.append(origin.rstrip("/"))
    if not result:
        _error("DECLARAI_ALLOWED_ORIGINS", "at least one explicit origin is required")
    return list(dict.fromkeys(result))


def load_runtime(base_dir, development_secret, env=None):
    env = os.environ if env is None else env
    profile = env.get("DECLARAI_RUNTIME_PROFILE", "development")
    if profile not in ("development", "private"):
        _error("DECLARAI_RUNTIME_PROFILE", "select development or private explicitly")
    private = profile == "private"
    debug = _boolean(env, "DJANGO_DEBUG", not private)
    if private and debug:
        _error("DJANGO_DEBUG", "private mode requires false")
    secret = _secret(env, "DJANGO_SECRET_KEY", None if private else development_secret)
    if private and (
        len(secret) < 50
        or len(set(secret)) < 5
        or secret.startswith("django-insecure-")
        or secret == development_secret
    ):
        _error("DJANGO_SECRET_KEY", "private mode requires a distinct strong key of at least 50 characters")
    hosts = (
        _hosts(env.get("DJANGO_ALLOWED_HOSTS", ""), "DJANGO_ALLOWED_HOSTS")
        if private
        else [x.strip() for x in env.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if x.strip()]
    )
    origins = _origins(env.get("DECLARAI_ALLOWED_ORIGINS", "" if private else DEVELOPMENT_ORIGINS), private)
    media = Path(env.get("DECLARAI_MEDIA_ROOT", str(base_dir / "media") if not private else ""))
    if private and (not media.is_absolute() or media == Path("/") or not media.is_dir() or media.is_symlink()):
        _error(
            "DECLARAI_MEDIA_ROOT",
            "private mode requires an existing absolute artifact directory, not a root or symlink",
        )

    engine = env.get("DECLARAI_DB_ENGINE", "postgresql" if private else "sqlite")
    if engine not in ("sqlite", "postgresql") or private and engine != "postgresql":
        _error("DECLARAI_DB_ENGINE", "private mode requires postgresql; development permits sqlite or postgresql")
    if engine == "sqlite":
        if any(name.startswith("DECLARAI_DB_") and name != "DECLARAI_DB_ENGINE" for name in env):
            _error("DECLARAI_DB_ENGINE", "PostgreSQL fields cannot silently select SQLite; set postgresql explicitly")
        database = {"ENGINE": "django.db.backends.sqlite3", "NAME": base_dir / "db.sqlite3"}
    else:
        fields = {}
        for name in ("NAME", "USER", "HOST"):
            value = env.get("DECLARAI_DB_" + name, "")
            if not value or any(c in value for c in "\x00\r\n"):
                _error("DECLARAI_DB_" + name, "an explicit nonempty value is required")
            fields[name] = value
        validated_hosts = _hosts(fields["HOST"], "DECLARAI_DB_HOST")
        if len(validated_hosts) != 1 or validated_hosts[0] != fields["HOST"]:
            _error("DECLARAI_DB_HOST", "use one explicit PostgreSQL host")
        # libpq expects an unbracketed IPv6 literal, unlike Django ALLOWED_HOSTS.
        fields["HOST"] = fields["HOST"].removeprefix("[").removesuffix("]")
        sslmode = env.get("DECLARAI_DB_SSLMODE", "verify-full" if private else "disable")
        if sslmode not in ("disable", "require", "verify-ca", "verify-full") or private and sslmode != "verify-full":
            _error(
                "DECLARAI_DB_SSLMODE",
                "private mode requires verify-full; development permits disable, require, verify-ca or verify-full",
            )
        options = {"sslmode": sslmode, "connect_timeout": 10}
        if sslmode in ("verify-ca", "verify-full"):
            ca = Path(env.get("DECLARAI_DB_SSLROOTCERT", ""))
            if not ca.is_absolute() or not ca.is_file():
                _error("DECLARAI_DB_SSLROOTCERT", "use an existing absolute PostgreSQL CA certificate path")
            options["sslrootcert"] = str(ca)
        database = {
            "ENGINE": "django.db.backends.postgresql",
            **fields,
            "PASSWORD": _secret(env, "DECLARAI_DB_PASSWORD"),
            "PORT": _integer(env, "DECLARAI_DB_PORT", 5432, 1, 65535),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": options,
        }
    return {
        "DECLARAI_RUNTIME_PROFILE": profile,
        "DEBUG": debug,
        "SECRET_KEY": secret,
        "ALLOWED_HOSTS": hosts,
        "CORS_ALLOWED_ORIGINS": origins,
        "CSRF_TRUSTED_ORIGINS": origins,
        "MEDIA_ROOT": media,
        "DATABASES": {"default": database},
        "SESSION_COOKIE_SECURE": not debug,
        "CSRF_COOKIE_SECURE": not debug,
        "SECURE_SSL_REDIRECT": private,
        "SECURE_HSTS_SECONDS": _integer(env, "DJANGO_HSTS_SECONDS", 3600 if private else 0, 0, 31536000),
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": _boolean(env, "DJANGO_HSTS_INCLUDE_SUBDOMAINS"),
        "SECURE_HSTS_PRELOAD": _boolean(env, "DJANGO_HSTS_PRELOAD"),
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https")
        if _boolean(env, "DJANGO_TRUST_PROXY_TLS")
        else None,
    }
