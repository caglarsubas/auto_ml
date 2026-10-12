"""Credential-safe cache configuration and observable TLS failure behavior."""
import logging
import os
import ssl
import subprocess
from urllib.parse import quote

import pytest
from django.core.exceptions import ImproperlyConfigured
from ai_assistant.cache_connection import connection_options
from tests.unit.test_job_preflight import checks  # noqa: F401

pytestmark = pytest.mark.unit
SECRET = 'Cache-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789"\\#'


@pytest.fixture
def cache_env(tmp_path):
    cert, key = tmp_path / 'ca.crt', tmp_path / 'key.pem'
    result = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=cache', '-addext', 'subjectAltName=DNS:cache'], capture_output=True, timeout=15)
    assert result.returncode == 0
    cert.chmod(0o400)
    url = tmp_path / 'cache-url'
    url.write_text('rediss://:' + quote(SECRET, safe='') + '@cache:6379/0')
    url.chmod(0o400)
    return {'DECLARAI_CACHE_URL_FILE': str(url), 'DECLARAI_CACHE_CA_FILE': str(cert)}


def test_selected_transport_captures_trust_and_requires_hostname(cache_env):
    url, options = connection_options(cache_env)
    assert '@cache:6379/0' in url
    assert options['ssl_cert_reqs'] == ssl.CERT_REQUIRED
    assert options['ssl_check_hostname'] is True
    assert options['ssl_min_version'] == ssl.TLSVersion.TLSv1_2
    assert 'BEGIN CERTIFICATE' in options['ssl_ca_data']
    assert 'ssl_ca_certs' not in options  # No later path replacement can change trust.


@pytest.mark.parametrize('fault', ['plaintext', 'external', 'port', 'database', 'query', 'fragment', 'user', 'weak', 'controls', 'bad_percent', 'raw_url', 'direct', 'missing_url', 'missing_ca', 'bad_ca', 'world_read', 'link', 'hardlink', 'directory', 'empty', 'oversized', 'fifo', 'ca_mode', 'ca_link', 'ca_hardlink'])
def test_selected_transport_rejects_unsafe_or_contradictory_input(cache_env, fault, tmp_path):
    path = tmp_path / 'cache-url'
    ca = tmp_path / 'ca.crt'
    # The fixture owner may mutate its own delivery, then production validation
    # still checks the explicitly selected protected modes.
    path.chmod(0o600)
    ca.chmod(0o600)
    if fault in {'plaintext', 'external', 'port', 'database', 'query', 'fragment', 'user', 'weak', 'controls', 'bad_percent'}:
        mutations = {'plaintext': ('rediss:', 'redis:'), 'external': ('@cache:', '@external:'), 'port': (':6379/', ':6380/'), 'database': ('/0', '/1'), 'query': ('/0', '/0?ssl_cert_reqs=none'), 'fragment': ('/0', '/0#ignored'), 'user': ('//:', '//user:'), 'weak': (quote(SECRET, safe=''), 'weak'), 'controls': (quote(SECRET, safe=''), quote(SECRET + '\x00', safe='')), 'bad_percent': ('/0', '/0')}
        before, after = mutations[fault]
        value = path.read_text().replace(before, after)
        if fault == 'bad_percent':
            value = value.replace('@cache', '%xx@cache')
        path.write_text(value)
    elif fault == 'raw_url':
        cache_env['REDIS_URL'] = 'redis://external:6379/0'
    elif fault == 'direct':
        cache_env['DECLARAI_CACHE_URL'] = path.read_text()
    elif fault == 'missing_url':
        del cache_env['DECLARAI_CACHE_URL_FILE']
    elif fault == 'missing_ca':
        del cache_env['DECLARAI_CACHE_CA_FILE']
    elif fault == 'bad_ca':
        ca.write_text('invalid synthetic CA')
    elif fault == 'world_read':
        path.chmod(0o644)
    elif fault in {'link', 'directory', 'fifo'}:
        path.unlink()
        if fault == 'link':
            path.symlink_to(ca)
        elif fault == 'directory':
            path.mkdir()
        else:
            os.mkfifo(path)
    elif fault == 'hardlink':
        os.link(path, tmp_path / 'other')
    elif fault == 'empty':
        path.write_text('')
    elif fault == 'oversized':
        path.write_text('x' * 4097)
    elif fault == 'ca_mode':
        ca.chmod(0o644)
    elif fault == 'ca_link':
        ca.unlink(); ca.symlink_to(path)
    elif fault == 'ca_hardlink':
        os.link(ca, tmp_path / 'other')
    with pytest.raises(ImproperlyConfigured, match='^private_cache_configuration_invalid$'):
        connection_options(cache_env)


def test_historical_endpoint_remains_explicit():
    assert connection_options({'REDIS_URL': 'redis://local.test:6379/2'}) == ('redis://local.test:6379/2', {})


def test_unavailable_client_does_not_log_url_or_driver_error(monkeypatch, caplog):
    import ai_assistant.cache as cache
    import redis
    monkeypatch.setattr(cache, '_redis_initialized', False)
    monkeypatch.setattr(cache, '_redis_client', None)
    monkeypatch.setenv('REDIS_URL', 'redis://:' + SECRET + '@secret.test:6379/0')
    monkeypatch.setattr(redis, 'from_url', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('driver leaked ' + SECRET)))
    with caplog.at_level(logging.WARNING):
        assert cache._get_redis() is None
    assert SECRET not in caplog.text and 'secret.test' not in caplog.text and 'driver leaked' not in caplog.text
    assert 'cache disabled' in caplog.text


@pytest.mark.parametrize('operation', ['cache_put', 'cache_get', 'cache_put_bulk', 'cache_delete', 'cache_list_artifacts'])
def test_failed_cache_operations_emit_static_diagnostics(monkeypatch, caplog, operation):
    import ai_assistant.cache as cache
    attrs = {}
    class Failed:
        def __getattr__(self, name):
            raise RuntimeError('payload and credential ' + SECRET)
    monkeypatch.setattr(cache, '_get_redis', lambda: Failed())
    monkeypatch.setattr(cache, 'set_span_attr', lambda k, v: attrs.update({k: v}))
    args = {'cache_put': (1, 'data', {}), 'cache_get': (1, 'data'), 'cache_put_bulk': (1, {'data': {}}), 'cache_delete': (1, 'data'), 'cache_list_artifacts': (1,)}[operation]
    with caplog.at_level(logging.WARNING):
        getattr(cache, operation)(*args)
    assert SECRET not in caplog.text and SECRET not in str(attrs)
    assert attrs['declarai.cache.reason'] == 'cache-operation-failed'


@pytest.mark.parametrize('fault', [None, 'ping_false', 'driver_error', 'bad_config'])
def test_selected_cache_preflight_blocks_launch_on_failure(checks, cache_env, monkeypatch, fault):
    from unittest.mock import MagicMock, patch
    from execution_jobs.preflight import check_runtime, RuntimeUnavailable
    monkeypatch.delenv('REDIS_URL', raising=False)
    for key, value in cache_env.items():
        monkeypatch.setenv(key, value)
    client = MagicMock()
    client.ping.return_value = True
    if fault == 'ping_false':
        client.ping.return_value = False
    elif fault == 'driver_error':
        client.ping.side_effect = RuntimeError('credential ' + SECRET)
    elif fault == 'bad_config':
        monkeypatch.setenv('REDIS_URL', 'redis://external:6379/0')
    with patch('redis.Redis', return_value=client) as connect:
        if fault is None:
            result = check_runtime()
            assert result['cache_connection'] == 'authenticated_tls_verified'
            pool = connect.call_args.kwargs['connection_pool']
            from ai_assistant.cache_connection import SelectedCAConnection
            assert pool.connection_class is SelectedCAConnection
            assert pool.connection_kwargs['ssl_check_hostname'] is True
            assert pool.connection_kwargs['ssl_cert_reqs'] == ssl.CERT_REQUIRED
        else:
            with pytest.raises(RuntimeUnavailable, match='^job_cache_unavailable$'):
                check_runtime()
        if fault == 'bad_config':
            connect.assert_not_called()
            client.close.assert_not_called()
        else:
            client.close.assert_called_once()


def test_private_factory_uses_exclusive_ca_pool(cache_env):
    from ai_assistant.cache_connection import create_client, SelectedCAConnection
    client = create_client(cache_env)
    try:
        pool = client.connection_pool
        assert pool.connection_class is SelectedCAConnection
        assert pool.connection_kwargs['host'] == 'cache' and pool.connection_kwargs['db'] == 0
        assert pool.connection_kwargs['password'] == SECRET
        assert pool.connection_kwargs['ssl_ca_data'] == (open(cache_env['DECLARAI_CACHE_CA_FILE']).read())
    finally:
        client.close()


def test_private_ssl_context_never_loads_system_trust(monkeypatch):
    from unittest.mock import Mock
    from ai_assistant.cache_connection import SelectedCAConnection
    ctx = Mock()
    monkeypatch.setattr(ssl, 'SSLContext', Mock(return_value=ctx))
    monkeypatch.setattr(ssl, 'create_default_context', lambda *a, **k: pytest.fail('system trust must not be loaded'))
    connection = SelectedCAConnection(host='cache', ssl_ca_data='captured-trust')
    sock = object()
    assert connection._wrap_socket_with_ssl(sock) is ctx.wrap_socket.return_value
    ctx.load_verify_locations.assert_called_once_with(cadata='captured-trust')
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2 and ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    ctx.wrap_socket.assert_called_once_with(sock, server_hostname='cache')
