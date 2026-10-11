"""Daemon-reported isolation and fixture ownership for packaged job checks."""

import copy
import importlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
IMAGE = 'sha256:' + 'a' * 64
NETWORK = 'declarai-fixture-test-net'


@pytest.fixture
def qualifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'scripts'))
    return importlib.import_module('qualify_private_image_jobs')


def info(role='worker'):
    return {
        'Image': IMAGE,
        'Config': {'User': '10001:10001', 'Cmd': [role], 'Entrypoint': ['python', '/app/scripts/private_service.py']},
        'HostConfig': {
            'ReadonlyRootfs': True, 'Privileged': False, 'PortBindings': {}, 'CapDrop': ['ALL'], 'CapAdd': [],
            'SecurityOpt': ['no-new-privileges'], 'NanoCpus': 2_000_000_000, 'Memory': 2 * 1024**3,
            'PidsLimit': 256, 'NetworkMode': NETWORK, 'Tmpfs': {'/tmp': 'bounded'},
        },
        'NetworkSettings': {'Ports': {}},
        'Mounts': [{'Type': 'volume', 'Destination': '/installation', 'RW': False},
                   {'Type': 'volume', 'Destination': '/artifacts', 'RW': True}],
        'State': {'Running': role == 'worker', 'OOMKilled': False, 'ExitCode': 0},
    }


@pytest.mark.parametrize('path,value', [
    (['Image'], 'sha256:' + 'b' * 64), (['Config', 'User'], '0:0'), (['Config', 'Cmd'], ['api']),
    (['Config', 'Entrypoint'], ['sh']), (['HostConfig', 'ReadonlyRootfs'], False),
    (['HostConfig', 'Privileged'], True), (['HostConfig', 'PortBindings'], {'8001/tcp': [{}]}),
    (['HostConfig', 'CapDrop'], []), (['HostConfig', 'CapAdd'], ['SYS_ADMIN']),
    (['HostConfig', 'SecurityOpt'], []), (['HostConfig', 'NanoCpus'], 0), (['HostConfig', 'Memory'], 0),
    (['HostConfig', 'PidsLimit'], 0), (['HostConfig', 'NetworkMode'], 'host'),
    (['HostConfig', 'Tmpfs'], {'/app': 'rw'}), (['NetworkSettings', 'Ports'], {'8001/tcp': [{}]}),
])
def test_actual_daemon_configuration_must_preserve_isolation(qualifier, path, value):
    original = info();target = original
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError, match='configuration rejected'):
        qualifier.verify_role(original, IMAGE, 'worker', NETWORK)


@pytest.mark.parametrize('fault', ['source_bind', 'secret_write', 'artifact_readonly', 'fixture_state', 'duplicate', 'socket'])
def test_worker_cannot_receive_source_secrets_write_or_observer_state(qualifier, fault):
    original = info()
    if fault == 'source_bind':
        original['Mounts'][1]['Type'] = 'bind'
    elif fault == 'secret_write':
        original['Mounts'][0]['RW'] = True
    elif fault == 'artifact_readonly':
        original['Mounts'][1]['RW'] = False
    else:
        original['Mounts'].append(copy.deepcopy(original['Mounts'][0]))
        original['Mounts'][-1]['Destination'] = {
            'fixture_state': '/fixture', 'socket': '/run/declarai', 'duplicate': '/installation',
        }[fault]
    with pytest.raises(RuntimeError, match='mounts rejected'):
        qualifier.verify_role(original, IMAGE, 'worker', NETWORK)


@pytest.mark.parametrize('image,network,installation,artifacts', [
    ('declarai:latest', NETWORK, 'declarai-fixed-api-test-installation', 'declarai-fixed-api-test-artifacts'),
    (IMAGE, 'customer-network', 'declarai-fixed-api-test-installation', 'declarai-fixed-api-test-artifacts'),
    (IMAGE, NETWORK, 'customer-secrets', 'declarai-fixed-api-test-artifacts'),
    (IMAGE, NETWORK, 'declarai-fixed-api-test-installation', 'customer-artifacts'),
])
def test_unowned_fixture_rejected_before_docker(qualifier, monkeypatch, tmp_path, image, network, installation, artifacts):
    def unexpected(*args, **kwargs):
        raise AssertionError('Unowned fixture reached Docker')
    monkeypatch.setattr(qualifier, 'command', unexpected)
    with pytest.raises(RuntimeError, match='owning disposable'):
        qualifier.qualify_jobs(image, network, installation, artifacts, tmp_path / 'env', tmp_path)


@pytest.mark.parametrize('fault', [None, 'seed', 'worker_mount', 'verify', 'dispatcher_stop', 'duplicates', 'worker_exit'])
def test_qualification_fails_closed_and_cleans_only_created_resources(qualifier, monkeypatch, tmp_path, fault):
    calls, cleanup, phase_order = [], [], []

    def run(argv, **kwargs):
        calls.append(argv)
        if 'PROBE_SENTINEL' in argv:
            phase = json.loads(kwargs['data'])['phase'];phase_order.append(phase)
            if phase == fault:
                raise RuntimeError('injected observer failure')
            return json.dumps({'phase': phase}).encode()
        if 'inspect' in argv:
            role = 'dispatcher' if argv[-1].endswith('-dispatcher') else 'worker'
            result = info(role)
            if fault == 'worker_mount' and role == 'worker':
                result['Mounts'][1]['Type'] = 'bind'
            if fault == 'dispatcher_stop' and role == 'dispatcher':
                result['State']['ExitCode'] = 137
            if fault == 'worker_exit' and role == 'worker' and 'duplicates' in phase_order:
                result['State']['ExitCode'] = 137
            if 'duplicates' in phase_order:
                result['State']['Running'] = False
            return json.dumps([result]).encode()
        return b'created'

    monkeypatch.setattr(qualifier, 'PROBE', 'PROBE_SENTINEL')
    monkeypatch.setattr(qualifier, 'command', run)
    monkeypatch.setattr(qualifier.subprocess, 'run', lambda argv, **kwargs: cleanup.append(argv))
    args = (IMAGE, NETWORK, 'declarai-fixed-api-test-installation', 'declarai-fixed-api-test-artifacts', tmp_path / 'env', tmp_path)
    if fault:
        with pytest.raises(RuntimeError):
            qualifier.qualify_jobs(*args)
        assert not (tmp_path / 'fixed-jobs.json').exists()
    else:
        result = qualifier.qualify_jobs(*args)
        assert phase_order == ['seed', 'verify', 'duplicates', 'settled']
        assert not result['expert_isolation_qualified'] and not result['production_recovery_qualified']
        stop = next(i for i, argv in enumerate(calls) if 'stop' in argv)
        duplicate = next(i for i, argv in enumerate(calls) if 'PROBE_SENTINEL' in argv and i > stop)
        assert stop < duplicate
    for argv in calls:
        if 'create' in argv and '--name' in argv:
            assert '--entrypoint' not in argv and '--pull' in argv and argv[-2] == IMAGE
            assert not any('/fixture' in arg for arg in argv)
    owned = {argv[argv.index('--name') + 1] for argv in calls if '--name' in argv}
    owned |= {argv[-1] for argv in calls if argv[:3] == ['docker', 'volume', 'create']}
    assert cleanup and all(argv[-1] in owned and argv[-1].startswith('declarai-fixed-jobs-') for argv in cleanup)


def test_observer_code_compiles_and_stays_outside_runtime_inventory(qualifier):
    compile(qualifier.PROBE, '<fixed-image-job-observer>', 'exec')
    package = importlib.import_module('private_api_package')
    assert 'scripts/qualify_private_image_jobs.py' not in package.RUNTIME_FILES
