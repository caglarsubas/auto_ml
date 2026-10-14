"""A read-then-write transaction cannot lose its reservation to another writer."""

import sqlite3
import threading

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_atomic_metadata_write_reserves_before_reading_and_both_writers_commit(tmp_path):
    from django.db import connections
    from django.db.backends.sqlite3.base import DatabaseWrapper
    from backend.runtime_config import load_runtime

    configured = load_runtime(tmp_path, "synthetic-development-key", env={})["DATABASES"]["default"]
    config = {**connections.databases["default"], **configured, "OPTIONS": configured.get("OPTIONS", {})}
    connection = DatabaseWrapper(config, alias="owned-reservation-fixture")
    acquired, attempted, finished = threading.Event(), threading.Event(), threading.Event()
    errors = []
    worker = None

    def other_writer():
        other = sqlite3.connect(config["NAME"])
        try:
            attempted.set()
            other.execute("BEGIN IMMEDIATE")
            acquired.set()
            other.execute("INSERT INTO metadata VALUES (2)")
            other.commit()
        except Exception as error:
            errors.append(error)
        finally:
            other.close()
            finished.set()

    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE metadata (id INTEGER PRIMARY KEY)")
        connection.set_autocommit(False, force_begin_transaction_with_broken_autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM metadata")
            assert cursor.fetchone()[0] == 0
        worker = threading.Thread(target=other_writer)
        worker.start()
        assert attempted.wait(1)
        assert not acquired.wait(0.1), "another writer acquired the reservation after our read"
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO metadata VALUES (1)")
        connection.commit()
        connection.set_autocommit(True)
        assert finished.wait(2)
        assert not errors
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM metadata ORDER BY id")
            assert cursor.fetchall() == [(1,), (2,)]
    finally:
        connection.close()
        if worker:
            worker.join(timeout=5)
            assert not worker.is_alive()
