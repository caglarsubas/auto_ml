"""Explicit PostgreSQL qualification plugin; original test fixtures stay intact."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest


def pytest_addoption(parser):
    parser.addoption("--postgresql-isolation-report", required=True)


def pytest_configure(config):
    config._postgresql_workers = {}
    if not hasattr(config, "workerinput"):
        return
    worker = config.workerinput["workerid"]
    if worker not in {"gw0", "gw1"}:
        raise pytest.UsageError("PostgreSQL qualification requires exactly two workers")
    url = urlsplit(os.environ.get("REDIS_URL", ""))
    if url.scheme != "redis" or not url.hostname or url.path != "/0" or url.query or url.fragment:
        raise pytest.UsageError("PostgreSQL qualification requires the owned Redis fixture")
    database = 2 + int(worker[-1])  # Keep fixture cache 0 and job broker 1 untouched.
    os.environ["REDIS_URL"] = urlunsplit(url._replace(path=f"/{database}"))
    from redis import Redis

    with Redis.from_url(os.environ["REDIS_URL"], socket_timeout=5, socket_connect_timeout=5) as client:
        client.ping()
        if client.client_info()["db"] != database:
            raise pytest.UsageError("PostgreSQL worker cache isolation failed")
    config._postgresql_identity = {"worker": worker, "cache_database": database}


def pytest_runtest_call(item):
    identity = item.config._postgresql_identity
    if "database" not in identity:
        from django.db import connection

        if connection.connection is not None:
            database = connection.connection.info.dbname
            if not database.endswith("_" + identity["worker"]):
                raise RuntimeError("PostgreSQL worker database isolation failed")
            identity["database"] = database


def pytest_testnodedown(node, error):
    identity = node.workeroutput.get("postgresql_isolation")
    if identity is not None:
        node.config._postgresql_workers[node.gateway.id] = identity


def pytest_sessionfinish(session):
    config = session.config
    if hasattr(config, "workerinput"):
        config.workeroutput["postgresql_isolation"] = config._postgresql_identity
        return
    workers = config._postgresql_workers
    valid = (set(workers) == {"gw0", "gw1"}
             and {w.get("cache_database") for w in workers.values()} == {2, 3}
             and len({w.get("database") for w in workers.values()}) == 2
             and all(w.get("database", "").endswith("_" + worker) for worker, w in workers.items()))
    Path(config.getoption("--postgresql-isolation-report")).write_text(
        json.dumps({"workers": workers, "isolated": valid}, indent=2) + "\n"
    )
    if not valid:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
