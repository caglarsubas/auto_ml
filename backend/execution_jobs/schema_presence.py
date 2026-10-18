"""Read-only physical-column checks for sealed private PostgreSQL.

Migration records alone do not establish that required physical relations still
exist with their declared storage types, modifiers, nullability, ordinary
writable storage, identity modes, immediate primary keys and field uniqueness. Other constraints
and complete schema/restore equivalence remain outside this check.
"""

import json

from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder


class SchemaMismatch(Exception):
    pass


STORAGE_TYPES = {
    "AutoField": "int4", "IntegerField": "int4", "PositiveIntegerField": "int4",
    "BigAutoField": "int8", "BigIntegerField": "int8", "PositiveBigIntegerField": "int8",
    "SmallAutoField": "int2", "SmallIntegerField": "int2", "PositiveSmallIntegerField": "int2",
    "BooleanField": "bool", "CharField": "varchar", "FileField": "varchar",
    "TextField": "text", "DateTimeField": "timestamptz", "UUIDField": "uuid", "JSONField": "jsonb",
}


def required_storage_contract():
    # Use the sealed migration graph's final storage declarations. Runtime
    # auto-created auth through-model IDs can differ from their historical DDL.
    # Loading the graph with no connection executes no migrations or data reads.
    loader = MigrationLoader(None)
    if loader.replacements:
        raise SchemaMismatch
    models = [m for m in loader.project_state().apps.get_models(include_auto_created=True)
              if m._meta.managed and not m._meta.proxy]
    models.append(MigrationRecorder.Migration)
    expected = {}
    for model in models:
        # Composite/absent primary-key declarations need a separately qualified
        # contract; a virtual CompositePrimaryKey is not a concrete column.
        if sum(field.primary_key for field in model._meta.local_concrete_fields) != 1:
            raise SchemaMismatch
        expected[model._meta.db_table] = {}
        for field in model._meta.local_concrete_fields:
            # This profile supports ordinary writable fields, including
            # identity-backed keys. GeneratedField reports its output's plain
            # internal type, so type mapping alone cannot reject generation.
            if field.generated:
                raise SchemaMismatch
            target = field.target_field if field.is_relation else field
            try:
                datatype = STORAGE_TYPES[target.get_internal_type()]
            except KeyError:
                raise SchemaMismatch from None
            modifier = -1
            if datatype == "varchar" and target.max_length is not None:
                if type(target.max_length) is not int or target.max_length <= 0:
                    raise SchemaMismatch
                # PostgreSQL stores varchar(n) as n plus its four-byte header.
                modifier = target.max_length + 4
            expected[model._meta.db_table][field.column] = {
                "type": datatype, "modifier": modifier,
                # A nullable FK still points to a non-null primary key. Its
                # local declaration, not its target, governs this column.
                "not_null": field.primary_key or not field.null,
                "primary_key": field.primary_key,
                # A primary key implies uniqueness but needs no second UNIQUE
                # constraint. Ordinary FKs must not inherit target uniqueness.
                "unique_field": field.unique and not field.primary_key,
                # Django 5.2's selected PostgreSQL backend emits BY DEFAULT
                # identity for these local auto fields. A foreign key targets
                # an auto key but must not inherit its generation behavior.
                "identity": "d" if not field.is_relation and field.get_internal_type() in {
                    "AutoField", "BigAutoField", "SmallAutoField",
                } else "",
            }
    required = required_schema()
    if any(not columns <= expected.get(table, {}).keys() for table, columns in required.items()):
        raise SchemaMismatch
    return {table: {column: expected[table][column] for column in columns} for table, columns in required.items()}


def required_schema():
    models = [m for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy]
    models.append(MigrationRecorder.Migration)
    return {m._meta.db_table: {f.column for f in m._meta.local_concrete_fields} for m in models}


def check_schema():
    required = required_schema()
    with connection.cursor() as cursor:
        # Catalog-only evidence: visible ordinary public relations and exact
        # pg_catalog storage OIDs, modifiers, nullability and non-generated
        # storage, identity, immediate primary-key and field-unique semantics. A same-named
        # domain or array is not the sealed plain type. Extra columns remain permitted.
        # Bind every catalog/operator/type so namespaces cannot forge evidence.
        cursor.execute("""
            WITH required_relations AS (
                SELECT c.relname,c.relkind,c.oid
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace
                WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name
                    AND c.relname OPERATOR(pg_catalog.=) ANY(%s::pg_catalog.name[])
            ), profile AS (SELECT %s::pg_catalog.jsonb AS types)
            SELECT c.relname, c.relkind,
                pg_catalog.pg_table_is_visible(c.oid)
                    AND (wanted.name IS NULL OR (
                        a.atttypid OPERATOR(pg_catalog.=) t.oid
                        AND a.atttypmod OPERATOR(pg_catalog.=) wanted.modifier
                        AND a.attnotnull OPERATOR(pg_catalog.=) wanted.not_null
                        AND a.attgenerated OPERATOR(pg_catalog.=) ''::pg_catalog."char"
                        AND a.attidentity OPERATOR(pg_catalog.=) wanted.identity
                        AND (NOT wanted.primary_key OR EXISTS (
                            SELECT 1 FROM pg_catalog.pg_constraint k
                            JOIN pg_catalog.pg_index i
                                ON i.indexrelid OPERATOR(pg_catalog.=) k.conindid
                                AND i.indrelid OPERATOR(pg_catalog.=) c.oid
                            WHERE k.conrelid OPERATOR(pg_catalog.=) c.oid
                                AND k.contype OPERATOR(pg_catalog.=) 'p'::pg_catalog."char"
                                AND k.conkey OPERATOR(pg_catalog.=) ARRAY[a.attnum]::pg_catalog.int2[]
                                AND k.convalidated AND NOT k.condeferrable AND NOT k.condeferred
                                AND i.indisprimary AND i.indisunique AND i.indisvalid
                                AND i.indisready AND i.indislive AND i.indimmediate
                                AND i.indnkeyatts OPERATOR(pg_catalog.=) 1::pg_catalog.int2
                                AND i.indpred IS NULL AND i.indexprs IS NULL
                        ))
                        AND (NOT wanted.unique_field OR EXISTS (
                            SELECT 1 FROM pg_catalog.pg_constraint k
                            JOIN pg_catalog.pg_index i
                                ON i.indexrelid OPERATOR(pg_catalog.=) k.conindid
                                AND i.indrelid OPERATOR(pg_catalog.=) c.oid
                            WHERE k.conrelid OPERATOR(pg_catalog.=) c.oid
                                AND k.contype OPERATOR(pg_catalog.=) 'u'::pg_catalog."char"
                                AND k.conkey OPERATOR(pg_catalog.=) ARRAY[a.attnum]::pg_catalog.int2[]
                                AND k.convalidated AND NOT k.condeferrable AND NOT k.condeferred
                                AND i.indisunique AND i.indisvalid AND i.indisready
                                AND i.indislive AND i.indimmediate
                                AND i.indnkeyatts OPERATOR(pg_catalog.=) 1::pg_catalog.int2
                                AND i.indpred IS NULL AND i.indexprs IS NULL
                                -- Field.unique permits multiple NULLs by default.
                                -- NULL modes are equivalent for a non-null field.
                                AND (wanted.not_null OR NOT i.indnullsnotdistinct)
                        )))), a.attname
            FROM required_relations c CROSS JOIN profile p
            LEFT JOIN pg_catalog.pg_attribute a
                ON a.attrelid OPERATOR(pg_catalog.=) c.oid
                AND a.attnum OPERATOR(pg_catalog.>) 0 AND NOT a.attisdropped
            LEFT JOIN LATERAL (
                SELECT (((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'type'::pg_catalog.text)::pg_catalog.name AS name,
                    (((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'modifier'::pg_catalog.text)::pg_catalog.int4 AS modifier,
                    (((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'not_null'::pg_catalog.text)::pg_catalog.bool AS not_null,
                    (((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'identity'::pg_catalog.text)::pg_catalog."char" AS identity,
                    (((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'primary_key'::pg_catalog.text)::pg_catalog.bool AS primary_key,
                    (((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'unique_field'::pg_catalog.text)::pg_catalog.bool AS unique_field
            ) wanted ON true
            LEFT JOIN pg_catalog.pg_type t
                ON t.typnamespace OPERATOR(pg_catalog.=) 'pg_catalog'::pg_catalog.regnamespace::pg_catalog.oid
                    AND t.typname OPERATOR(pg_catalog.=) wanted.name
        """, [list(required), json.dumps(required_storage_contract())])
        present = {}
        for table, kind, compatible, column in cursor.fetchall():
            if kind != "r" or compatible is not True:
                raise SchemaMismatch
            present.setdefault(table, set()).add(column)
    if any(not columns <= present.get(table, set()) for table, columns in required.items()):
        raise SchemaMismatch
