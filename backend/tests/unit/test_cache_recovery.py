import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def reconnect(monkeypatch):
    from ai_assistant import cache as module

    monkeypatch.setattr(module, "_redis_initialized", False)
    monkeypatch.setattr(module, "_redis_client", None)
    monkeypatch.setattr(module, "_redis_retry_after", 0.0)
    clock = {"now": 100.0}
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    monkeypatch.setattr(module, "create_client", Mock())
    return module, clock


def test_cooldown_suppresses_attempts_then_recovers(reconnect, monkeypatch):
    module, clock = reconnect
    bad, good = Mock(), Mock()
    bad.ping.side_effect = RuntimeError("synthetic-secret")
    good.ping.return_value = True
    factory = Mock(side_effect=[bad, good])
    monkeypatch.setattr(module, "create_client", factory)
    assert module._get_redis() is None
    for t in [100.0, 104.999]:
        clock["now"] = t
        assert module._get_redis() is None
    assert factory.call_count == 1
    bad.close.assert_called_once()
    clock["now"] = 105.0
    assert module._get_redis() is good
    assert module._get_redis() is good and factory.call_count == 2
    assert factory.call_args.kwargs["decode_responses"] is True


def test_continued_failures_remain_bounded(reconnect, monkeypatch):
    module, clock = reconnect
    factory = Mock(side_effect=RuntimeError("synthetic-secret"))
    monkeypatch.setattr(module, "create_client", factory)
    for t in [100.0, 100.0, 104.0, 105.0, 105.0, 109.99, 110.0]:
        clock["now"] = t
        assert module._get_redis() is None
    assert factory.call_count == 3


def test_concurrent_failed_initialization_has_one_attempt(reconnect, monkeypatch):
    module, clock = reconnect
    entered, release = threading.Event(), threading.Event()

    def ping():
        entered.set()
        assert release.wait(2)
        raise RuntimeError("synthetic-secret")

    bad = Mock()
    bad.ping.side_effect = ping
    factory = Mock(return_value=bad)
    monkeypatch.setattr(module, "create_client", factory)
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(module._get_redis) for _ in range(20)]
        assert entered.wait(2)
        release.set()
        assert all(f.result(timeout=2) is None for f in futures)
    assert factory.call_count == 1


def test_retry_revalidates_configuration_and_cannot_downgrade(reconnect, monkeypatch):
    module, clock = reconnect
    config = Mock(side_effect=[RuntimeError("bad configured trust"), RuntimeError("changed insecure config")])
    monkeypatch.setattr(module, "create_client", config)
    import redis

    factory = Mock()
    monkeypatch.setattr(redis, "from_url", factory)
    assert module._get_redis() is None
    clock["now"] = 105.0
    assert module._get_redis() is None
    assert config.call_count == 2 and factory.call_count == 0


from tests.unit.test_private_cache import cache_env  # noqa: F401


def test_private_factory_deterministically_closes_owned_pool(cache_env, monkeypatch):
    from ai_assistant import cache_connection as module

    client = module.create_client(cache_env)
    disconnect = Mock(wraps=client.connection_pool.disconnect)
    monkeypatch.setattr(client.connection_pool, "disconnect", disconnect)
    assert client.auto_close_connection_pool is True
    client.close()
    disconnect.assert_called_once()
