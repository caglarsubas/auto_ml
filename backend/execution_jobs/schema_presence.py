"""Read-only physical-column checks for sealed private PostgreSQL.

Migration records alone do not establish that required physical relations still
exist with their declared storage types, modifiers, nullability, ordinary
writable storage, identity modes, immediate primary keys, declared uniqueness
and the selected foreign-key/RI-trigger profile in an origin/local connection.
Historical row integrity and complete schema/restore equivalence remain outside
this check.
"""

import json

from django.apps import apps
from django.db import connection
from django.db.models import ForeignKey, UniqueConstraint
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
            if field.is_relation and (not isinstance(field, ForeignKey) or not field.db_constraint):
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
                "unique_groups": [],
                "foreign_key": {
                    "table": target.model._meta.db_table, "column": target.column,
                } if field.is_relation else None,
                # Django 5.2's selected PostgreSQL backend emits BY DEFAULT
                # identity for these local auto fields. A foreign key targets
                # an auto key but must not inherit its generation behavior.
                "identity": "d" if not field.is_relation and field.get_internal_type() in {
                    "AutoField", "BigAutoField", "SmallAutoField",
                } else "",
            }
        groups = list(model._meta.unique_together)
        for constraint in model._meta.constraints:
            if not isinstance(constraint, UniqueConstraint):
                continue
            # These forms need separately qualified contracts rather than
            # silently losing their declarations at startup.
            if (not constraint.fields or constraint.expressions or constraint.condition is not None
                    or constraint.deferrable is not None or constraint.include or constraint.opclasses
                    or constraint.nulls_distinct is not None):
                raise SchemaMismatch
            groups.append(constraint.fields)
        local = {f.name: f for f in model._meta.local_concrete_fields}
        for fields in groups:
            if not fields or len(set(fields)) != len(fields) or any(f not in local for f in fields):
                raise SchemaMismatch
            columns = [local[f].column for f in fields]
            expected[model._meta.db_table][columns[0]]["unique_groups"].append({
                "columns": columns,
                "not_null": all(local[f].primary_key or not local[f].null for f in fields),
            })
    required = required_schema()
    if any(not columns <= expected.get(table, {}).keys() for table, columns in required.items()):
        raise SchemaMismatch
    if any(not set(group["columns"]) <= required.get(table, set())
           for table, columns in expected.items() for field in columns.values() for group in field["unique_groups"]):
        raise SchemaMismatch
    if any(field["foreign_key"]["column"] not in required.get(field["foreign_key"]["table"], set())
           for columns in expected.values() for field in columns.values() if field["foreign_key"] is not None):
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
                SELECT c.relname,c.relkind,c.oid,c.relhastriggers
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace
                WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name
                    AND c.relname OPERATOR(pg_catalog.=) ANY(%s::pg_catalog.name[])
            ), profile AS (SELECT %s::pg_catalog.jsonb AS types)
            SELECT c.relname, c.relkind,
                pg_catalog.pg_table_is_visible(c.oid)
                    -- Login-default repairs do not change an already-open
                    -- connection. Normal RI triggers fire in origin/local;
                    -- replica is outside the sealed metadata profile.
                    AND pg_catalog.current_setting('session_replication_role')
                        OPERATOR(pg_catalog.=) ANY(ARRAY['origin','local']::pg_catalog.text[])
                    AND (wanted.name IS NULL OR (
                        a.atttypid OPERATOR(pg_catalog.=) t.oid
                        AND a.atttypmod OPERATOR(pg_catalog.=) wanted.modifier
                        AND a.attnotnull OPERATOR(pg_catalog.=) wanted.not_null
                        AND a.attgenerated OPERATOR(pg_catalog.=) ''::pg_catalog."char"
                        AND a.attidentity OPERATOR(pg_catalog.=) wanted.identity
                        AND (wanted.foreign_table IS NULL OR EXISTS (
                            SELECT 1 FROM pg_catalog.pg_constraint k
                            JOIN pg_catalog.pg_class target ON target.oid OPERATOR(pg_catalog.=) k.confrelid
                            JOIN pg_catalog.pg_namespace target_namespace
                                ON target_namespace.oid OPERATOR(pg_catalog.=) target.relnamespace
                            JOIN pg_catalog.pg_attribute target_column
                                ON target_column.attrelid OPERATOR(pg_catalog.=) target.oid
                                AND target_column.attnum OPERATOR(pg_catalog.>) 0 AND NOT target_column.attisdropped
                            WHERE k.conrelid OPERATOR(pg_catalog.=) c.oid
                                AND k.contype OPERATOR(pg_catalog.=) 'f'::pg_catalog."char"
                                AND k.conkey OPERATOR(pg_catalog.=) ARRAY[a.attnum]::pg_catalog.int2[]
                                AND k.confkey OPERATOR(pg_catalog.=) ARRAY[target_column.attnum]::pg_catalog.int2[]
                                AND target_namespace.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name
                                AND target.relname OPERATOR(pg_catalog.=) wanted.foreign_table
                                AND target.relkind OPERATOR(pg_catalog.=) 'r'::pg_catalog."char"
                                AND target_column.attname OPERATOR(pg_catalog.=) wanted.foreign_column
                                AND k.convalidated AND k.condeferrable AND k.condeferred
                                AND c.relhastriggers AND target.relhastriggers
                                -- Selected Django PostgreSQL DDL defers checks.
                                -- ORM on_delete is separate from database actions.
                                AND k.confmatchtype OPERATOR(pg_catalog.=) 's'::pg_catalog."char"
                                AND k.confupdtype OPERATOR(pg_catalog.=) 'a'::pg_catalog."char"
                                AND k.confdeltype OPERATOR(pg_catalog.=) 'a'::pg_catalog."char"
                                -- Four internal AFTER ROW roles enforce this
                                -- selected NO ACTION, initially deferred profile.
                                -- Names are not evidence; bind exact built-in
                                -- functions, constraint/index and both relations.
                                AND NOT EXISTS (
                                    SELECT 1 FROM (VALUES
                                        ('pg_catalog."RI_FKey_check_ins"()'::pg_catalog.regprocedure::pg_catalog.oid, 5, true),
                                        ('pg_catalog."RI_FKey_check_upd"()'::pg_catalog.regprocedure::pg_catalog.oid, 17, true),
                                        ('pg_catalog."RI_FKey_noaction_del"()'::pg_catalog.regprocedure::pg_catalog.oid, 9, false),
                                        ('pg_catalog."RI_FKey_noaction_upd"()'::pg_catalog.regprocedure::pg_catalog.oid, 17, false)
                                    ) AS role(function_oid, event_type, child)
                                    WHERE NOT EXISTS (
                                        SELECT 1 FROM pg_catalog.pg_trigger tr
                                        WHERE tr.tgconstraint OPERATOR(pg_catalog.=) k.oid
                                            AND tr.tgisinternal
                                            AND tr.tgfoid OPERATOR(pg_catalog.=) role.function_oid
                                            AND tr.tgtype::pg_catalog.int4 OPERATOR(pg_catalog.=) role.event_type
                                            AND tr.tgrelid OPERATOR(pg_catalog.=)
                                                CASE WHEN role.child THEN k.conrelid ELSE k.confrelid END
                                            AND tr.tgconstrrelid OPERATOR(pg_catalog.=)
                                                CASE WHEN role.child THEN k.confrelid ELSE k.conrelid END
                                            AND tr.tgconstrindid OPERATOR(pg_catalog.=) k.conindid
                                            AND tr.tgparentid OPERATOR(pg_catalog.=) 0::pg_catalog.oid
                                            AND tr.tgenabled OPERATOR(pg_catalog.=) ANY(ARRAY['O','A']::pg_catalog."char"[])
                                            AND tr.tgdeferrable AND tr.tginitdeferred
                                            AND tr.tgnargs OPERATOR(pg_catalog.=) 0::pg_catalog.int2
                                            AND tr.tgargs OPERATOR(pg_catalog.=) ''::pg_catalog.bytea
                                            AND tr.tgattr::pg_catalog.text OPERATOR(pg_catalog.=) ''::pg_catalog.text
                                            AND tr.tgqual IS NULL
                                    )
                                )
                        ))
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
                        ))
                        AND NOT EXISTS (
                            SELECT 1 FROM pg_catalog.jsonb_array_elements(
                                COALESCE(wanted.unique_groups, '[]'::pg_catalog.jsonb)
                            ) AS g(value)
                            WHERE NOT EXISTS (
                                SELECT 1 FROM pg_catalog.pg_constraint k
                                JOIN pg_catalog.pg_index i
                                    ON i.indexrelid OPERATOR(pg_catalog.=) k.conindid
                                    AND i.indrelid OPERATOR(pg_catalog.=) c.oid
                                WHERE k.conrelid OPERATOR(pg_catalog.=) c.oid
                                    AND k.contype OPERATOR(pg_catalog.=) 'u'::pg_catalog."char"
                                    AND k.convalidated AND NOT k.condeferrable AND NOT k.condeferred
                                    AND i.indisunique AND i.indisvalid AND i.indisready
                                    AND i.indislive AND i.indimmediate
                                    AND i.indpred IS NULL AND i.indexprs IS NULL
                                    AND i.indnkeyatts::pg_catalog.int4 OPERATOR(pg_catalog.=)
                                        pg_catalog.jsonb_array_length(g.value OPERATOR(pg_catalog.->) 'columns'::pg_catalog.text)
                                    -- Membership governs uniqueness; key order and
                                    -- non-key INCLUDE columns do not change it.
                                    AND ARRAY(SELECT members.number FROM pg_catalog.unnest(k.conkey) AS members(number)
                                        ORDER BY members.number USING OPERATOR(pg_catalog.<)) OPERATOR(pg_catalog.=)
                                        ARRAY(SELECT ga.attnum FROM pg_catalog.pg_attribute ga
                                            WHERE ga.attrelid OPERATOR(pg_catalog.=) c.oid
                                                AND ga.attnum OPERATOR(pg_catalog.>) 0 AND NOT ga.attisdropped
                                                AND ga.attname OPERATOR(pg_catalog.=) ANY(ARRAY(
                                                    SELECT names.name::pg_catalog.name FROM pg_catalog.jsonb_array_elements_text(
                                                        g.value OPERATOR(pg_catalog.->) 'columns'::pg_catalog.text
                                                    ) AS names(name)))
                                            ORDER BY ga.attnum USING OPERATOR(pg_catalog.<))
                                    AND ((g.value OPERATOR(pg_catalog.->>) 'not_null'::pg_catalog.text)::pg_catalog.bool
                                        OR NOT i.indnullsnotdistinct)
                            )
                        ))), a.attname
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
                    OPERATOR(pg_catalog.->>) 'unique_field'::pg_catalog.text)::pg_catalog.bool AS unique_field,
                    ((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) 'unique_groups'::pg_catalog.text AS unique_groups,
                    ((((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) 'foreign_key'::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'table'::pg_catalog.text)::pg_catalog.name AS foreign_table,
                    ((((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) a.attname::pg_catalog.text)
                    OPERATOR(pg_catalog.->) 'foreign_key'::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) 'column'::pg_catalog.text)::pg_catalog.name AS foreign_column
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
