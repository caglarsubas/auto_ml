"""Private broker readiness must not accept an unauthenticated TLS endpoint."""

import traceback
from urllib.parse import unquote

import pytest
from django.core.exceptions import ImproperlyConfigured
from kombu import Connection

from execution_jobs.broker_transport import create_client
from execution_jobs.config import load_job_config
from tests.unit.test_private_broker_tls import broker_env  # noqa: F401
from tests.unit.test_private_cache import cache_env  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("credentials", [
    "", ":@", "sentinel-user@", ":%@", ":%GG@", ":%FF@", ":%00@", ":%0A@", ":%7f@",
    "%FF:sentinel-password@", "%xx:sentinel-password@",
])
@pytest.mark.parametrize("entrypoint", ["settings", "readiness"])
def test_private_rejects_missing_or_invalid_authentication_before_trust_or_network(monkeypatch, credentials, entrypoint):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid authentication reached trust capture or network setup")

    monkeypatch.setattr("execution_jobs.broker_transport.captured_tls", forbidden)
    monkeypatch.setattr("execution_jobs.broker_transport.redis.ConnectionPool", forbidden)
    env = {"DECLARAI_JOB_BROKER_URL": "rediss://" + credentials + "sentinel-host:6379/1"}
    with pytest.raises(ImproperlyConfigured) as caught:
        load_job_config("private", env) if entrypoint == "settings" else create_client(env)
    assert str(caught.value) == "private_broker_authentication_required"
    assert "sentinel" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("credentials", [
    ":synthetic-password", "worker:synthetic-password", ":reserved%40%3A%2F%25", ":utf8-%C3%A9", ":space%20inside",
])
def test_valid_credentials_agree_between_readiness_and_kombu(broker_env, credentials):
    env = {**broker_env, "DECLARAI_JOB_BROKER_URL": "rediss://" + credentials + "@job-broker:6379/1"}
    config = load_job_config("private", env)
    expected_user, expected_password = credentials.split(":", 1)
    client = create_client(env)
    try:
        options = client.connection_pool.connection_kwargs
        assert options["password"] == unquote(expected_password)
        assert options["username"] == (unquote(expected_user) or None)
        with Connection(config["CELERY_BROKER_URL"], transport=config["CELERY_BROKER_TRANSPORT"],
                        ssl=config["CELERY_BROKER_USE_SSL"]) as broker:
            assert broker.password == options["password"]
            assert (broker.userid or None) == options["username"]
    finally:
        client.close()


@pytest.mark.parametrize("value", ["redis://localhost/0", "redis://user@localhost/0", "redis://:@localhost/0"])
def test_development_unauthenticated_contract_is_preserved(value):
    assert load_job_config("development", {"DECLARAI_JOB_BROKER_URL": value})["CELERY_BROKER_URL"] == value


@pytest.mark.parametrize("credentials", ["", ":synthetic-password@"])
def test_protected_file_has_the_same_authentication_policy(broker_env, tmp_path, credentials):
    path = tmp_path / "broker-url"
    value = "rediss://" + credentials + "job-broker:6379/1"
    path.write_text(value)
    path.chmod(0o600)
    env = {"DECLARAI_JOB_BROKER_URL_FILE": str(path),
           "DECLARAI_JOB_BROKER_CA_FILE": broker_env["DECLARAI_JOB_BROKER_CA_FILE"]}
    if credentials:
        assert load_job_config("private", env)["CELERY_BROKER_URL"] == value
    else:
        with pytest.raises(ImproperlyConfigured, match="^private_broker_authentication_required$"):
            load_job_config("private", env)
