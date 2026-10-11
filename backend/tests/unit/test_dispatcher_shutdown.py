"""Signals stop the pump after its current dispatch and restore caller handlers."""

import signal

import pytest
from django.core.management.base import CommandError
from django.db import DatabaseError
from execution_jobs.management.commands import dispatch_jobs
from execution_jobs.service import JobConflict

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('signum', [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize('database_failure', [False, True])
def test_signal_finishes_current_dispatch_without_starting_another(monkeypatch, signum, database_failure):
    handlers, restored, calls = {}, [], []
    original = object()

    def install(selected, handler):
        if handler is original:
            restored.append(selected)
        else:
            handlers[selected] = handler
        return original

    def dispatch():
        calls.append('entered')
        handlers[signum](signum, None)
        calls.append('finished')
        if database_failure:
            raise DatabaseError('private-credential-sentinel')
        return {'delivered': 1}

    monkeypatch.setattr(dispatch_jobs.signal, 'signal', install)
    monkeypatch.setattr(dispatch_jobs, 'dispatch_once', dispatch)
    command = dispatch_jobs.Command()
    command.handle(once=False)
    assert calls == ['entered', 'finished']
    assert set(restored) == {signal.SIGTERM, signal.SIGINT}


@pytest.mark.parametrize('failure', [DatabaseError('private-credential-sentinel'), JobConflict('job_scope_changed')])
def test_once_preserves_rejection_without_installing_signal_handlers(monkeypatch, failure):
    def unexpected(*args):
        raise AssertionError('Once mode changed signal ownership')

    def dispatch():
        raise failure

    monkeypatch.setattr(dispatch_jobs.signal, 'signal', unexpected)
    monkeypatch.setattr(dispatch_jobs, 'dispatch_once', dispatch)
    expected = 'job_storage_unavailable' if isinstance(failure, DatabaseError) else 'job_scope_changed'
    with pytest.raises(CommandError, match=expected):
        dispatch_jobs.Command().handle(once=True)


def test_continuous_fatal_rejection_restores_signal_ownership(monkeypatch):
    restored = []
    original = object()

    def install(signum, handler):
        if handler is original:
            restored.append(signum)
        return original

    def dispatch():
        raise JobConflict('job_scope_changed')

    monkeypatch.setattr(dispatch_jobs.signal, 'signal', install)
    monkeypatch.setattr(dispatch_jobs, 'dispatch_once', dispatch)
    with pytest.raises(CommandError, match='job_scope_changed'):
        dispatch_jobs.Command().handle(once=False)
    assert set(restored) == {signal.SIGTERM, signal.SIGINT}


def test_signal_during_idle_wait_returns_without_reentrant_lock(monkeypatch):
    handlers, calls, sleeps = {}, [], []
    original = object()

    def install(signum, handler):
        handlers[signum] = handler
        return original

    def dispatch():
        calls.append('dispatch')
        return {'delivered': 0}

    def idle(seconds):
        sleeps.append(seconds)
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(dispatch_jobs.signal, 'signal', install)
    monkeypatch.setattr(dispatch_jobs, 'dispatch_once', dispatch)
    monkeypatch.setattr(dispatch_jobs.time, 'sleep', idle)
    dispatch_jobs.Command().handle(once=False)
    assert calls == ['dispatch'] and len(sleeps) == 1 and 0 < sleeps[0] <= 0.1
