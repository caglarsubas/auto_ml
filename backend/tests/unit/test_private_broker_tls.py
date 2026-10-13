"""Captured broker trust and private-only Kombu channel compatibility."""

import os
import ssl
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ImproperlyConfigured
from kombu import Connection
from kombu.transport.redis import Channel as UpstreamChannel

from execution_jobs.broker_transport import Channel, SelectedCAConnection, Transport, captured_tls, create_client
from execution_jobs.config import load_job_config
from tests.unit.test_private_cache import cache_env  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def broker_env(cache_env):
    return {"DECLARAI_JOB_BROKER_URL": "rediss://:Synthetic-Password-0123456789@job-broker:6379/1",
            "DECLARAI_JOB_BROKER_CA_FILE": cache_env["DECLARAI_CACHE_CA_FILE"]}


def test_private_captures_ca_and_development_keeps_existing_transport(broker_env):
    private = load_job_config("private", broker_env)
    assert private["CELERY_BROKER_TRANSPORT"] == "execution_jobs.broker_transport:Transport"
    assert private["CELERY_BROKER_USE_SSL"]["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert "ssl_ca_data" in private["CELERY_BROKER_USE_SSL"]
    assert "ssl_ca_certs" not in private["CELERY_BROKER_USE_SSL"]
    development = load_job_config("development", broker_env)
    assert "CELERY_BROKER_TRANSPORT" not in development
    assert development["CELERY_BROKER_USE_SSL"]["ssl_ca_certs"] == broker_env["DECLARAI_JOB_BROKER_CA_FILE"]
    assert UpstreamChannel.connection_class_ssl is not SelectedCAConnection


def test_declared_snapshot_survives_path_replacement(broker_env):
    from pathlib import Path

    config = load_job_config("private", broker_env)
    path = Path(broker_env["DECLARAI_JOB_BROKER_CA_FILE"])
    path.chmod(0o600)
    path.write_text("replacement cannot change captured trust")
    client = SelectedCAConnection(host="job-broker", **config["CELERY_BROKER_USE_SSL"])
    assert "BEGIN CERTIFICATE" in client.ca_data
    with pytest.raises(ImproperlyConfigured, match="private_broker_ca_invalid"):
        load_job_config("private", broker_env)


@pytest.mark.parametrize("fault", ["empty", "oversized", "invalid", "group_write", "symlink", "hardlink", "fifo", "directory", "relative"])
def test_invalid_ca_delivery_fails_before_network(cache_env, fault, tmp_path):
    from pathlib import Path

    path = Path(cache_env["DECLARAI_CACHE_CA_FILE"])
    path.chmod(0o600)
    if fault in {"empty", "oversized", "invalid"}:
        path.write_text({"empty": "", "oversized": "x" * 65537, "invalid": "not a CA"}[fault])
    elif fault == "group_write":
        path.chmod(0o620)
    elif fault == "hardlink":
        os.link(path, tmp_path / "second-ca")
    elif fault != "relative":
        path.unlink()
        if fault == "symlink":
            path.symlink_to(tmp_path / "cache-url")
        elif fault == "fifo":
            os.mkfifo(path)
        else:
            path.mkdir()
    with pytest.raises(ImproperlyConfigured, match="^private_broker_ca_invalid$"):
        captured_tls("relative.crt" if fault == "relative" else path)


@pytest.mark.parametrize("override", [
    {"ssl_ca_data": None}, {"ssl_cert_reqs": ssl.CERT_NONE}, {"ssl_cert_reqs": ssl.CERT_OPTIONAL},
    {"ssl_check_hostname": False}, {"ssl_min_version": ssl.TLSVersion.TLSv1},
    {"ssl_ca_certs": "/ambient.pem"}, {"ssl_certfile": "/client.pem"}, {"ssl_keyfile": "/client.key"},
])
def test_tls_downgrade_is_rejected(broker_env, override):
    options = load_job_config("private", broker_env)["CELERY_BROKER_USE_SSL"]
    with pytest.raises(ImproperlyConfigured, match="^private_broker_tls_required$"):
        SelectedCAConnection(host="job-broker", **{**options, **override})


def test_context_uses_only_captured_roots_and_hostname(monkeypatch, broker_env):
    options = load_job_config("private", broker_env)["CELERY_BROKER_USE_SSL"]
    context = MagicMock()
    monkeypatch.setattr(ssl, "create_default_context", lambda *a, **k: pytest.fail("ambient trust loaded"))
    constructor = MagicMock(return_value=context)
    monkeypatch.setattr(ssl, "SSLContext", constructor)
    sock = object()
    SelectedCAConnection(host="job-broker", **options)._wrap_socket_with_ssl(sock)
    constructor.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations.assert_called_once_with(cadata=options["ssl_ca_data"])
    context.wrap_socket.assert_called_once_with(sock, server_hostname="job-broker")
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


@pytest.mark.parametrize("asynchronous", [False, True])
def test_kombu_producer_and_async_consumer_use_selected_connection(broker_env, asynchronous):
    config = load_job_config("private", broker_env)
    with Connection(config["CELERY_BROKER_URL"], transport=config["CELERY_BROKER_TRANSPORT"],
                    ssl=config["CELERY_BROKER_USE_SSL"]) as connection:
        assert connection.get_transport_cls() is Transport
        channel = object.__new__(Channel)
        channel.connection = SimpleNamespace(client=connection, default_port=6379)
        channel._registered = False
        params = channel._connparams(asynchronous=asynchronous)
        assert issubclass(params.pop("connection_class"), SelectedCAConnection)
        assert params["db"] == 1 and params["host"] == "job-broker"
        import redis

        pool = redis.ConnectionPool(connection_class=SelectedCAConnection, **params)
        try:
            client = pool.make_connection()
            assert client.ca_data == config["CELERY_BROKER_USE_SSL"]["ssl_ca_data"]
        finally:
            pool.disconnect()


def test_dependency_probe_uses_same_config_and_tls_pool(broker_env):
    client = create_client(broker_env)
    try:
        assert client.connection_pool.connection_class is SelectedCAConnection
        assert client.connection_pool.connection_kwargs["db"] == 1
        assert client.auto_close_connection_pool is True
    finally:
        client.close()


def test_plaintext_or_multi_endpoint_cannot_select_private_transport(broker_env):
    for value in ("redis://host/1", "rediss://host/1;rediss://other/1"):
        with pytest.raises(ImproperlyConfigured):
            load_job_config("private", {**broker_env, "DECLARAI_JOB_BROKER_URL": value})
    with pytest.raises(ImproperlyConfigured, match="private_broker_tls_required"):
        SelectedCAConnection(host="job-broker")
