"""Pure declaration rendering must never substitute for fresh schema evidence."""

import copy

import pytest
from django.db.migrations.loader import MigrationLoader

from execution_jobs import schema_presence as schema

pytestmark = pytest.mark.unit


def test_identical_fresh_states_reuse_only_rendering(monkeypatch):
    monkeypatch.setattr(schema, '_rendered_declarations', None)
    first = schema.required_storage_contract()
    entry = schema._rendered_declarations
    assert entry is not None
    second = schema.required_storage_contract()
    assert schema._rendered_declarations is entry
    assert first == second and first is not second
    first['auth_user']['username']['modifier'] = -100
    assert schema.required_storage_contract()['auth_user']['username']['modifier'] == 154
    # Required runtime declarations are still looked up on a cache hit.
    required = schema.required_schema()
    required['auth_user'].add('new_required_column')
    monkeypatch.setattr(schema, 'required_schema', lambda: required)
    with pytest.raises(schema.SchemaMismatch):
        schema.required_storage_contract()


def test_fresh_field_changes_invalidate_rendering(monkeypatch):
    monkeypatch.setattr(schema, '_rendered_declarations', None)
    state = MigrationLoader(None).project_state()
    before = list(schema._declaration_models(state))
    entry = schema._rendered_declarations
    changed = MigrationLoader(None).project_state()
    # ModelState.clone shares field objects: replace, never mutate an operation.
    field = copy.deepcopy(changed.models['auth', 'user'].fields['username'])
    field.null = True
    changed.models['auth', 'user'].fields['username'] = field
    after = list(schema._declaration_models(changed))
    assert schema._rendered_declarations is not entry
    assert next(m for m in before if m._meta.db_table == 'auth_user')._meta.get_field('username').null is False
    assert next(m for m in after if m._meta.db_table == 'auth_user')._meta.get_field('username').null is True


def test_pre_rendered_and_custom_states_are_not_cached(monkeypatch):
    monkeypatch.setattr(schema, '_rendered_declarations', None)
    schema.required_storage_contract()
    entry = schema._rendered_declarations
    state = MigrationLoader(None).project_state()
    user = state.apps.get_model('auth', 'user')
    user._meta.get_field('username').null = True
    assert user in list(schema._declaration_models(state))
    assert schema._rendered_declarations is entry

    def altered_loader(database):
        loader = MigrationLoader(database)
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema, 'MigrationLoader', altered_loader)
    assert schema.required_storage_contract()['auth_user']['username']['not_null'] is False
    # Unsupported generated declarations must still be refused after warmup.
    user._meta.get_field('username').generated = True
    with pytest.raises(schema.SchemaMismatch):
        schema.required_storage_contract()
    assert schema._rendered_declarations is entry


def test_unserializable_declarations_fall_back_without_caching(monkeypatch):
    monkeypatch.setattr(schema, '_rendered_declarations', None)
    before = schema.required_storage_contract()
    entry = schema._rendered_declarations
    monkeypatch.setattr(schema.pickle, 'dumps', lambda *args, **kwargs: (_ for _ in ()).throw(TypeError()))
    assert schema.required_storage_contract() == before
    assert schema._rendered_declarations is entry


def test_live_catalog_is_rechecked_after_rendering_reuse(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    monkeypatch.setattr(schema, '_rendered_declarations', None)
    rows = [(table, 'r', True, column) for table, columns in schema.required_schema().items() for column in columns]
    calls = []

    @contextmanager
    def cursor():
        calls.append('fresh_cursor')
        yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

    monkeypatch.setattr(schema, 'connection', SimpleNamespace(cursor=cursor))
    schema.check_schema()
    entry = schema._rendered_declarations
    rows[0] = (*rows[0][:2], False, rows[0][3])
    with pytest.raises(schema.SchemaMismatch):
        schema.check_schema()
    assert schema._rendered_declarations is entry
    assert calls == ['fresh_cursor', 'fresh_cursor']


def test_rendering_settings_invalidate_implicit_schema(monkeypatch, settings):
    monkeypatch.setattr(schema, '_rendered_declarations', None)
    # These IDs are supplied when rendering implicit M2M models, not stored
    # among the migration state's explicit fields. Warm reuse must track them.
    for value, expected in [('AutoField', 'int4'), ('BigAutoField', 'int8'), ('SmallAutoField', 'int2')]:
        settings.DEFAULT_AUTO_FIELD = 'django.db.models.' + value
        entry = schema._rendered_declarations
        contract = schema.required_storage_contract()
        assert contract['auth_user_groups']['id']['type'] == expected
        assert schema._rendered_declarations is not entry
        assert schema.required_storage_contract() == contract

    from django.db.models import BigAutoField
    from django.db.migrations.state import ModelState

    state = MigrationLoader(None).project_state()
    name = 'LongImplicitTableNameWhoseDefaultIdentifierRequiresTruncation'
    state.models['execution_jobs', name.lower()] = ModelState(
        'execution_jobs', name, fields=[('id', BigAutoField(primary_key=True))],
    )
    tables = []
    for limit in [63, 30]:
        monkeypatch.setattr(schema.model_connection.ops, 'max_name_length', lambda: limit)
        entry = schema._rendered_declarations
        models = list(schema._declaration_models(state.clone()))
        assert schema._rendered_declarations is not entry
        tables.append(next(m._meta.db_table for m in models if m.__name__ == name))
        assert len(tables[-1]) <= limit
    assert tables[0] != tables[1]
