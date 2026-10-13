"""Private Redis/Kombu TLS: captured declared anchors, never ambient trust.

The transport is selected per Celery application, without changing Kombu's
shared Redis channel or the development transport registry.
"""

import os
import ssl
import stat
from pathlib import Path
from urllib.parse import unquote, urlsplit

import redis
from django.core.exceptions import ImproperlyConfigured
from kombu.transport.redis import Channel as RedisChannel, Transport as RedisTransport

TRANSPORT = "execution_jobs.broker_transport:Transport"


def captured_tls(path):
    """Capture bounded public CA bytes once; reconnect cannot reread a path."""
    try:
        path = Path(path)
        if not path.is_absolute():
            raise ValueError
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) & 0o022 or not 0 < before.st_size <= 65536):
                raise ValueError
            data = stream.read(65537)
            after = os.fstat(stream.fileno())
            if len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError
        ca = data.decode("utf-8")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=ca)
        return {"ssl_ca_data": ca, "ssl_cert_reqs": ssl.CERT_REQUIRED,
                "ssl_check_hostname": True, "ssl_min_version": ssl.TLSVersion.TLSv1_2}
    except (OSError, ValueError, UnicodeError, ssl.SSLError):
        raise ImproperlyConfigured("private_broker_ca_invalid") from None


class SelectedCAConnection(redis.connection.SSLConnection):
    def __init__(self, *args, ssl_ca_data=None, ssl_cert_reqs=ssl.CERT_REQUIRED,
                 ssl_check_hostname=True, ssl_min_version=ssl.TLSVersion.TLSv1_2,
                 ssl_ca_certs=None, ssl_certfile=None, ssl_keyfile=None, **kwargs):
        if (not isinstance(ssl_ca_data, str) or not ssl_ca_data
                or ssl_cert_reqs != ssl.CERT_REQUIRED or ssl_check_hostname is not True
                or ssl_min_version != ssl.TLSVersion.TLSv1_2
                or any(x is not None for x in (ssl_ca_certs, ssl_certfile, ssl_keyfile))):
            raise ImproperlyConfigured("private_broker_tls_required")
        super().__init__(*args, ssl_ca_data=ssl_ca_data, ssl_cert_reqs=ssl_cert_reqs,
                         ssl_check_hostname=ssl_check_hostname, ssl_min_version=ssl_min_version, **kwargs)

    def _wrap_socket_with_ssl(self, sock):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_verify_locations(cadata=self.ca_data)
        return context.wrap_socket(sock, server_hostname=self.host)


class Channel(RedisChannel):
    # Both paths fail closed if SSL options disappear. Kombu derives the
    # asynchronous consumer connection from these classes as well.
    connection_class = SelectedCAConnection
    connection_class_ssl = SelectedCAConnection


class Transport(RedisTransport):
    Channel = Channel


def create_client(env, *, socket_timeout=5, socket_connect_timeout=5):
    """Dependency readiness uses the same config and TLS class as Celery."""
    from execution_jobs.config import load_job_config

    config = load_job_config("private", env)
    if not config["DECLARAI_JOBS_ENABLED"]:
        raise ImproperlyConfigured("private_broker_configuration_required")
    parsed = urlsplit(config["CELERY_BROKER_URL"])
    pool = redis.ConnectionPool(
        connection_class=SelectedCAConnection, host=parsed.hostname, port=parsed.port or 6379,
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        db=int(parsed.path.removeprefix("/")), socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout, **config["CELERY_BROKER_USE_SSL"],
    )
    client = redis.Redis(connection_pool=pool)
    client.auto_close_connection_pool = True
    return client
