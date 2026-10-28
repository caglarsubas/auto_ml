"""Profile initialization reads every pin afresh and refuses drift safely."""
import hashlib
import importlib.metadata as metadata
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
path = Path(__file__).resolve().parents[3] / 'scripts/verify_private_dependency_profile.py'
spec = importlib.util.spec_from_file_location('private_profile', path)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def test_exact_pins_normalize_names_and_bind_original_bytes(tmp_path):
    lock = tmp_path / 'runtime.lock'
    raw = b'# profile\nSome_Package==1.2.3\nother==2.0rc1\n'
    lock.write_bytes(raw)
    calls = []
    def lookup(name):
        calls.append(name)
        return {'some-package': '1.2.3', 'other': '2.0rc1'}[name]
    result = profile.verify([lock], lookup)
    assert result['verified'] and calls == ['other', 'some-package']
    assert result['lock_sha256'] == {lock.name: hashlib.sha256(raw).hexdigest()}
    assert result['packages'] == {'other': '2.0rc1', 'some-package': '1.2.3'}


@pytest.mark.parametrize('text', ['foo>=1', 'foo', '-r other.lock', '--index-url https://example.test',
                                   'foo==1; unknown_marker=="x"', 'foo==1 --hash=sha256:a',
                                   'foo==1\nFOO==1', 'some_package==1\nsome-package==1', '# only comments'])
def test_ranges_directives_duplicates_and_empty_profiles_refused(tmp_path, text):
    lock = tmp_path / 'runtime.lock'
    lock.write_text(text)
    with pytest.raises(profile.DependencyProfileError):
        profile.verify([lock], lambda name: '1')


def test_duplicate_names_across_runtime_and_test_overlay_refused(tmp_path):
    paths = [tmp_path / 'runtime.lock', tmp_path / 'tests.lock']
    for path in paths:
        path.write_text('foo==1')
    with pytest.raises(profile.DependencyProfileError, match='duplicate'):
        profile.verify(paths, lambda name: '1')


@pytest.mark.parametrize('failure', ['changed', 'missing', 'unreadable'])
def test_previous_success_never_hides_new_drift_or_lookup_failures(tmp_path, failure):
    lock = tmp_path / 'runtime.lock'
    lock.write_text('foo==1')
    state = ['1']
    calls = []
    def lookup(name):
        calls.append(name)
        if isinstance(state[0], Exception):
            raise state[0]
        return state[0]
    assert profile.verify([lock], lookup)['verified']
    state[0] = {'changed': '2', 'missing': metadata.PackageNotFoundError('foo'),
                'unreadable': PermissionError('secret marker')}[failure]
    with pytest.raises(profile.DependencyProfileError) as result:
        profile.verify([lock], lookup)
    assert 'secret marker' not in str(result.value) and calls == ['foo', 'foo']


def test_changed_lock_is_reparsed_after_success(tmp_path):
    lock = tmp_path / 'runtime.lock'
    lock.write_text('foo==1')
    original = profile.verify([lock], lambda name: '1')
    lock.write_text('foo==2')
    changed = profile.verify([lock], lambda name: '2')
    assert changed['lock_sha256'] != original['lock_sha256']


def test_missing_and_empty_profile_paths_refused(tmp_path):
    with pytest.raises(OSError):
        profile.verify([tmp_path / 'absent'])
    with pytest.raises(profile.DependencyProfileError, match='empty'):
        profile.verify([])


@pytest.mark.parametrize('machine,expected', [('x86_64', ['foo', 'gpu']), ('aarch64', ['foo'])])
def test_exact_conditional_pin_uses_selected_platform_without_silent_drift(tmp_path, machine, expected):
    lock = tmp_path / 'runtime.lock'
    lock.write_text('foo==1\ngpu==2; platform_system == "Linux" and platform_machine == "x86_64"\n')
    calls = []
    def lookup(name):
        calls.append(name)
        return {'foo': '1', 'gpu': '2'}[name]
    result = profile.verify([lock], lookup, environment={'platform_system': 'Linux', 'platform_machine': machine})
    assert calls == expected and result['verified']
    assert ('gpu' in result['inactive_markers']) == (machine == 'aarch64')
