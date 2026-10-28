"""Native metadata keeps standard values, decoder faults and immutable inputs."""
import io
import json
import re
import random
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.db import connection, models

from execution_jobs import metadata_json, service
from execution_jobs.metadata_json import NativeJSONField
from execution_jobs.models import NativeJob
from tests.unit.test_durable_training_search import world, admission, queue  # noqa: F401

pytestmark = pytest.mark.unit

RAW = ['null', 'true', 'false', '0', '-0', '17', '-17', '.5', '0.1', '-0.0',
       '5e-324', '1.7976931348623157e308', '1e999', '-1e999', 'NaN', 'Infinity',
       '123456789012345678901234567890', '"\\ud800"', '"\\ud83d\\ude00"',
       '{"z":[1,0.1,null,"é"],"a":false}', '{"a":1,"b":2,"a":3}',
       '[1,[2,[3]]]', '{"broken":', '', '1 trailing',
       '[' * 2000 + '0' + ']' * 2000,
       '"' + 'x' * (metadata_json._MAX_FAST_CHARACTERS + 1) + '"',
       '9' * 5000, 'inf', 'nan', '-inf', '-nan', '+Infinity', '[1,]', '{"a":1,}', '\ufeff{"a":1}', '{"a":1}\x00', '"unescaped\x01"']


@pytest.mark.parametrize('raw', RAW, ids=[f'wire-{i}' for i in range(len(RAW))])
def test_read_value_or_error_matches_standard_jsonfield_exactly(raw):
    reference, actual = models.JSONField(), NativeJSONField()
    try:
        expected = reference.from_db_value(raw, None, connection)
    except Exception as error:
        with pytest.raises(type(error)) as caught:
            actual.from_db_value(raw, None, connection)
        assert str(caught.value) == str(error)
    else:
        result = actual.from_db_value(raw, None, connection)
        assert type(result) is type(expected)
        # Retain key order, negative zero, nonfinite legacy values and Unicode.
        assert json.dumps(result, ensure_ascii=True) == json.dumps(expected, ensure_ascii=True)


@pytest.mark.parametrize('value', [None, 1, [], {}, b'null'])
def test_non_text_values_retain_the_existing_conversion_boundary(value):
    reference, actual = models.JSONField(), NativeJSONField()
    try:
        expected = reference.from_db_value(value, None, connection)
    except Exception as error:
        with pytest.raises(type(error)):
            actual.from_db_value(value, None, connection)
    else:
        assert actual.from_db_value(value, None, connection) == expected


@pytest.mark.parametrize('custom', ['field', 'loads', 'decoder_instance', 'decode_method', 'raw_decode_method'])
def test_custom_conversion_and_standard_parser_instrumentation_are_never_bypassed(custom, monkeypatch):
    def forbidden(value):
        raise AssertionError('custom decoder bypassed')
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', forbidden)
    original_loads = json.loads
    if custom == 'field':
        monkeypatch.setattr(models.JSONField, 'from_db_value', lambda *args: {'custom': True})
        assert NativeJSONField().from_db_value('{}', None, connection) == {'custom': True}
    elif custom == 'loads':
        observed = Mock(wraps=original_loads)
        monkeypatch.setattr(json, 'loads', observed)
        assert NativeJSONField().from_db_value('{"fresh":1}', None, connection) == {'fresh': 1}
        assert observed.call_count == 1
    elif custom == 'decoder_instance':
        monkeypatch.setattr(json, '_default_decoder', json.JSONDecoder(object_hook=lambda value: {'custom': value}))
        assert NativeJSONField().from_db_value('{"fresh":1}', None, connection) == {'custom': {'fresh': 1}}
    else:
        name = 'decode' if custom == 'decode_method' else 'raw_decode'
        original = getattr(json.JSONDecoder, name)
        calls = []
        def observe(self, *args, **kwargs):
            calls.append(True)
            return original(self, *args, **kwargs)
        monkeypatch.setattr(json.JSONDecoder, name, observe)
        assert NativeJSONField().from_db_value('{"fresh":1}', None, connection) == {'fresh': 1}
        assert calls


def test_explicit_decoder_keeps_custom_semantics(monkeypatch):
    class Tagged(json.JSONDecoder):
        def decode(self, value, **kwargs):
            return {'tagged': super().decode(value, **kwargs)}
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', lambda value: pytest.fail('explicit decoder bypassed'))
    assert NativeJSONField(decoder=Tagged).from_db_value('[1,2]', None, connection) == {'tagged': [1, 2]}


def test_unavailable_accelerator_keeps_fresh_standard_reads(monkeypatch):
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', None)
    field = NativeJSONField()
    assert field.from_db_value('{"fresh":1}', None, connection) == {'fresh': 1}
    assert field.from_db_value('{"fresh":2}', None, connection) == {'fresh': 2}
    assert metadata_json.runtime_profile()['implementation'] == 'stdlib-json'


def test_accelerator_unexpected_failures_remain_failures(monkeypatch):
    def unavailable(value):
        raise MemoryError('owned decoder failure')
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', unavailable)
    with pytest.raises(MemoryError, match='owned decoder failure'):
        NativeJSONField().from_db_value('{}', None, connection)


def test_optional_backend_version_is_looked_up_fresh(monkeypatch):
    versions, calls = iter(['1.0', '2.0']), []
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', json.loads)
    def version(name):
        calls.append(name)
        return next(versions)
    monkeypatch.setattr(metadata_json, 'package_version', version)
    assert metadata_json.runtime_profile() == {'implementation': 'pydantic-core.from_json', 'version': '1.0'}
    assert metadata_json.runtime_profile() == {'implementation': 'pydantic-core.from_json', 'version': '2.0'}
    assert calls == ['pydantic-core', 'pydantic-core']


@pytest.mark.parametrize('options', [{}, {'default': dict}, {'null': True}, {'encoder': json.JSONEncoder}, {'decoder': json.JSONDecoder}])
def test_storage_type_and_migration_deconstruction_are_unchanged(options):
    field, reference = NativeJSONField(name='metadata', **options), models.JSONField(name='metadata', **options)
    assert field.deconstruct() == reference.deconstruct()
    assert field.get_internal_type() == reference.get_internal_type() == 'JSONField'
    assert field.db_type(connection) == reference.db_type(connection)


@pytest.mark.django_db(transaction=True)
def test_native_fields_require_no_storage_migration():
    output = io.StringIO()
    call_command('makemigrations', 'execution_jobs', check=True, dry_run=True, interactive=False, stdout=output)
    assert 'No changes detected' in output.getvalue()


@pytest.mark.django_db(transaction=True)
def test_actual_execution_persists_only_transition_outputs_and_keeps_exact_inputs(world):  # noqa: F811
    body, _ = admission(world)
    identifier = queue(world, body)
    before = NativeJob.objects.values().get(pk=identifier)
    updates = []
    def observe(execute, sql, params, many, context):
        if sql.startswith('UPDATE "execution_jobs_nativejob"'):
            updates.append(set(re.findall(r'"([a-z_0-9]+)"\s*=', sql.split(' WHERE ', 1)[0])))
        return execute(sql, params, many, context)
    with connection.execute_wrapper(observe):
        service.execute(identifier)
    after = NativeJob.objects.values().get(pk=identifier)
    assert after['state'] == 'succeeded' and after['attempts'] == 1
    assert updates == [
        {'state', 'revision', 'attempts', 'lease_token', 'lease_until'},
        {'state', 'revision', 'lease_token', 'lease_until', 'result', 'result_sha256', 'reason_code', 'finished_at'}]
    immutable = ['project_id', 'dataset_id', 'source_dataset_id', 'actor_id', 'actor_snapshot', 'authority',
                 'specification', 'request_sha256', 'created_at', 'expires_at', 'next_dispatch']
    assert {f: before[f] for f in immutable} == {f: after[f] for f in immutable}
    assert after['result_sha256'] == service.digest(after['result'])
    assert list(NativeJob.objects.get(pk=identifier).events.values_list('event_type', flat=True)) == ['submitted', 'started', 'succeeded']
    NativeJob.objects.filter(pk=identifier).update(result={'fresh': [1, 2**70 + 1, -0.0, 'é']})
    assert NativeJob.objects.get(pk=identifier).result == {'fresh': [1, 2**70 + 1, -0.0, 'é']}
    assert after['result'] != NativeJob.objects.get(pk=identifier).result


def test_long_numeric_string_values_do_not_disable_compatible_decoding(monkeypatch):
    raw = json.dumps({'source_sha256': '1' * 64, 'rows': 17})
    observed = Mock(wraps=json.loads)
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', observed)
    assert NativeJSONField().from_db_value(raw, None, connection) == {'source_sha256': '1' * 64, 'rows': 17}
    assert observed.call_count == 1


@pytest.mark.parametrize('raw', ['123456789012345678901', '[123456789012345678901]', '{"n":-123456789012345678901}'])
def test_large_integer_tokens_keep_arbitrary_precision_in_every_container(raw, monkeypatch):
    actual = NativeJSONField().from_db_value(raw, None, connection)
    assert actual == json.loads(raw)
    number = actual if type(actual) is int else (actual[0] if type(actual) is list else actual['n'])
    assert type(number) is int


def test_nondefault_integer_limit_keeps_standard_parser(monkeypatch):
    # Simulate caller-policy observation without changing any interpreter budget.
    monkeypatch.setattr(metadata_json.sys, 'get_int_max_str_digits', lambda: 640)
    monkeypatch.setattr(metadata_json, '_FAST_LOADS', lambda value: pytest.fail('caller integer policy bypassed'))
    assert NativeJSONField().from_db_value('{"n":17}', None, connection) == {'n': 17}


@pytest.mark.django_db(transaction=True)
def test_submission_receipt_does_not_rewrite_the_created_request(world):  # noqa: F811
    body, _ = admission(world)
    updates = []
    def observe(execute, sql, params, many, context):
        if sql.startswith('UPDATE "execution_jobs_nativejob"'):
            updates.append(set(re.findall(r'"([a-z_0-9]+)"\s*=', sql.split(' WHERE ', 1)[0])))
        return execute(sql, params, many, context)
    with connection.execute_wrapper(observe):
        identifier = queue(world, body)
    job = NativeJob.objects.get(pk=identifier)
    assert updates == [{'revision'}]
    assert job.state == 'queued' and job.revision == 1 and job.attempts == 0
    assert job.specification['training_sha256'] == body['training_sha256']
    assert list(job.events.values_list('event_type', flat=True)) == ['submitted']


def test_generated_float_tokens_preserve_exact_binary64_values():
    generator = random.Random(160)
    field = NativeJSONField()
    for _ in range(2048):
        raw = str(generator.randrange(-10**18, 10**18)) + 'e' + str(generator.randrange(-340, 290))
        assert field.from_db_value(raw, None, connection).hex() == json.loads(raw).hex()
