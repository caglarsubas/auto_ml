"""Application side of the owned RI-trigger qualifier; no administrator access.

Not collected by pytest. The controller runs it in a disposable, isolated
container. Only the initial TLS result and broker connection are response
fixtures; migration, role, schema, privilege, RLS and integrity checks are real.
"""

import contextlib
import hashlib
import io
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock


def main():
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    django.setup()
    from django.conf import settings
    from django.contrib.auth.models import User
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from django.db import DatabaseError, IntegrityError, connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.recorder import MigrationRecorder

    from access_control.models import Project, ProjectMembership
    from execution_jobs import preflight, schema_presence

    with contextlib.redirect_stdout(sys.stderr):
        call_command("migrate", verbosity=0, interactive=False)
    preflight.check_application_role()
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, session_user, current_setting('session_replication_role')")
        assert cursor.fetchone() == ("ri_application", "ri_application", "origin")
    actor = User.objects.create(username="ri-owner", password="retained-password")
    project = Project.objects.create(name="ri-fixture")
    membership = ProjectMembership.objects.create(project=project, actor=actor, role="developer")
    history = set(MigrationRecorder(connection).applied_migrations())
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    from backend.celery import app

    calls = [0]
    broker = MagicMock()

    @contextlib.contextmanager
    def startup_cursor():
        calls[0] += 1
        if calls[0] == 1:
            yield SimpleNamespace(execute=lambda *a: None, fetchone=lambda: (True,))
        else:
            with connection.cursor() as cursor:
                yield cursor

    preflight.connection = SimpleNamespace(vendor="postgresql", alias=connection.alias,
        ensure_connection=connection.ensure_connection, introspection=connection.introspection, cursor=startup_cursor)
    preflight.MigrationExecutor = lambda _: MigrationExecutor(connection)
    app.connection_for_write = lambda: broker

    def snapshot():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT t.oid,t.tgrelid::regclass::text,t.tgname,t.tgfoid,t.tgtype,t.tgenabled,
                    t.tgisinternal,t.tgconstrrelid,t.tgconstrindid,t.tgconstraint,
                    t.tgdeferrable,t.tginitdeferred,t.tgnargs,t.tgattr::text,t.tgqual::text,
                    t.tgargs::text,t.tgparentid,p.proname
                FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
                WHERE t.tgconstraint=(SELECT k.oid FROM pg_catalog.pg_constraint k
                    JOIN pg_catalog.pg_attribute a ON a.attrelid=k.conrelid
                    WHERE k.conrelid='public.access_control_projectmembership'::regclass
                    AND a.attname='actor_id' AND k.contype='f' AND k.conkey=ARRAY[a.attnum])
                ORDER BY t.oid
            """)
            triggers = cursor.fetchall()
            cursor.execute("SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgisinternal")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT oid,tgrelid::regclass::text,tgname FROM pg_catalog.pg_trigger WHERE tgisinternal ORDER BY oid")
            all_internal = cursor.fetchall()
            cursor.execute("""SELECT k.oid,k.conrelid,k.confrelid,k.conname,k.conkey::text,k.confkey::text,
                k.convalidated,k.condeferrable,k.condeferred,k.confmatchtype,k.confupdtype,k.confdeltype,k.conindid
                FROM pg_catalog.pg_constraint k WHERE k.connamespace='public'::regnamespace ORDER BY k.oid""")
            constraints = cursor.fetchall()
            cursor.execute("""SELECT a.attrelid,a.attnum,a.attname,a.atttypid,a.atttypmod,a.attnotnull,a.attgenerated,a.attidentity
                FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
                WHERE c.relnamespace='public'::regnamespace AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY a.attrelid,a.attnum""")
            storage = cursor.fetchall()
        assert User.objects.get(pk=actor.pk).password == "retained-password"
        assert ProjectMembership.objects.get(pk=membership.pk).actor_id == actor.pk
        assert set(MigrationRecorder(connection).applied_migrations()) == history
        return dict(triggers=triggers, internal_triggers=count, all_internal=all_internal, migrations=len(history),
                    constraint_hash=hashlib.sha256(json.dumps(constraints).encode()).hexdigest(),
                    storage_hash=hashlib.sha256(json.dumps(storage).encode()).hexdigest())

    def controls():
        q = connection.ops.quote_name
        triggers = snapshot()["triggers"]
        check = next(t for t in triggers if t[-1] == "RI_FKey_check_ins")
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("ALTER TABLE public.access_control_projectmembership DISABLE TRIGGER " + q(check[2]))
        except DatabaseError as exc:
            assert exc.__cause__.sqlstate == "42501"
        else:
            raise AssertionError("ordinary_owner_disabled_internal_trigger")
        pending = False
        try:
            with transaction.atomic():
                ProjectMembership.objects.create(project=project, actor_id=2147483000, role="reviewer")
                pending = True
        except IntegrityError:
            assert pending
        else:
            raise AssertionError("orphan_not_rejected_at_commit")
        try:
            with transaction.atomic():
                ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
        except IntegrityError:
            pass
        else:
            raise AssertionError("duplicate_not_rejected")
        return dict(ordinary_disable_sqlstate="42501", deferred_orphan_rejected=True, duplicate_rejected=True)

    def committed_orphan():
        assert connection.get_autocommit() and not connection.in_atomic_block
        orphan = ProjectMembership.objects.create(project=project, actor_id=2147483000, role="reviewer")
        try:
            db = connection.settings_dict
            observer = connection.Database.connect(host=db["HOST"], dbname=db["NAME"], user=db["USER"], password=db["PASSWORD"])
            try:
                observer.autocommit = True
                with observer.cursor() as cursor:
                    cursor.execute("SELECT current_user,actor_id FROM public.access_control_projectmembership WHERE id=%s", [orphan.pk])
                    assert cursor.fetchone() == ("ri_application", 2147483000)
            finally:
                observer.close()
            try:
                ProjectMembership.objects.get(pk=orphan.pk).actor
            except User.DoesNotExist:
                pass
            else:
                raise AssertionError("orphan_has_actor")
        finally:
            ProjectMembership.objects.filter(pk=orphan.pk).delete()
        return dict(committed_orphan_observed_by_independent_ordinary_connection=True, orphan_removed=True)

    def connection_state():
        # Attest the actual ordinary role; do not consume the TLS response fixture.
        transport = preflight.connection
        try:
            preflight.connection = connection
            preflight.check_application_role()
        finally:
            preflight.connection = transport
        with connection.cursor() as cursor:
            cursor.execute("""SELECT current_user,session_user,
                pg_catalog.current_setting('session_replication_role'),
                pg_catalog.has_parameter_privilege(current_user,'session_replication_role','SET'),
                r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls,r.rolconfig
                FROM pg_catalog.pg_roles r WHERE r.rolname OPERATOR(pg_catalog.=) current_user""")
            row = cursor.fetchone()
        assert row[:2] == ("ri_application", "ri_application")
        assert row[3:9] == (False, False, False, False, False, False)
        return dict(current_user=row[0],session_user=row[1],mode=row[2],can_set=row[3],
                    elevated_attributes=list(row[4:9]),login_default=row[9])

    def replication_controls():
        state = connection_state()
        assert state["mode"] == "origin" and state["login_default"] is None
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET session_replication_role TO replica")
        except DatabaseError as exc:
            assert exc.__cause__.sqlstate == "42501"
        else:
            raise AssertionError("ordinary_application_changed_replication_mode")
        return dict(state=state,ordinary_set_sqlstate="42501")

    def authority_state():
        with connection.cursor() as cursor:
            cursor.execute("""SELECT current_user,session_user,
                pg_catalog.current_setting('session_replication_role'),
                pg_catalog.has_parameter_privilege(current_user,'session_replication_role','SET'),
                pg_catalog.has_parameter_privilege(current_user,'session_replication_role','ALTER SYSTEM'),
                pg_catalog.has_parameter_privilege(session_user,'session_replication_role','SET'),
                pg_catalog.has_parameter_privilege(session_user,'session_replication_role','ALTER SYSTEM'),
                r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls,r.rolconfig
                FROM pg_catalog.pg_roles r WHERE r.rolname OPERATOR(pg_catalog.=) current_user""")
            row = cursor.fetchone()
        assert row[7:12] == (False,) * 5 and row[12] is None
        return dict(current_user=row[0],session_user=row[1],mode=row[2],current_set=row[3],
                    current_alter_system=row[4],session_set=row[5],session_alter_system=row[6],
                    elevated_attributes=list(row[7:12]),login_default=row[12])

    def checkpoint_state():
        state = authority_state()
        with connection.cursor() as cursor:
            cursor.execute("""SELECT
                pg_catalog.pg_has_role(current_user,'pg_checkpoint'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(current_user,'pg_checkpoint'::pg_catalog.name,'USAGE'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_checkpoint'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_checkpoint'::pg_catalog.name,'USAGE'::pg_catalog.text)
            """)
            row = cursor.fetchone()
        return dict(state=state,current_member=row[0],current_usage=row[1],session_member=row[2],session_usage=row[3])

    def checkpoint_operation():
        assert connection.get_autocommit() and not connection.in_atomic_block
        try:
            with connection.cursor() as cursor:
                cursor.execute("CHECKPOINT")
                assert cursor.statusmessage == "CHECKPOINT"
        except DatabaseError as exc:
            assert exc.__cause__.sqlstate == "42501"
            return dict(status=None,sqlstate="42501")
        return dict(status="CHECKPOINT",sqlstate=None)

    def maintain_state():
        state = authority_state()
        with connection.cursor() as cursor:
            cursor.execute("""SELECT
                pg_catalog.pg_has_role(current_user,'pg_maintain'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(current_user,'pg_maintain'::pg_catalog.name,'USAGE'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_maintain'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_maintain'::pg_catalog.name,'USAGE'::pg_catalog.text)
            """)
            row = cursor.fetchone()
        return dict(state=state,current_member=row[0],current_usage=row[1],session_member=row[2],session_usage=row[3])

    def maintain_lock():
        assert connection.get_autocommit() and not connection.in_atomic_block
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.pg_backend_pid()")
            pid = cursor.fetchone()[0]
        connection.set_autocommit(False)
        try:
            with connection.cursor() as cursor:
                cursor.execute("LOCK TABLE maintain_fixture.protected IN ACCESS EXCLUSIVE MODE NOWAIT")
                assert cursor.statusmessage == "LOCK TABLE"
        except DatabaseError as exc:
            connection.rollback()
            connection.set_autocommit(True)
            assert exc.__cause__.sqlstate == "42501"
            return dict(status=None,sqlstate="42501")
        # Deliberately hold the ordinary application's lock until the separate
        # host administrator observes it and attempts a conflicting lock.
        return dict(status="LOCK TABLE",sqlstate=None,backend_pid=pid)

    def maintain_unlock():
        assert not connection.get_autocommit() and not connection.in_atomic_block
        connection.rollback()
        connection.set_autocommit(True)
        return dict(released=True)

    def subscription_state():
        state = authority_state()
        with connection.cursor() as cursor:
            cursor.execute("""SELECT
                pg_catalog.pg_has_role(current_user,'pg_create_subscription'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(current_user,'pg_create_subscription'::pg_catalog.name,'USAGE'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_create_subscription'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_create_subscription'::pg_catalog.name,'USAGE'::pg_catalog.text),
                pg_catalog.has_database_privilege(current_user,pg_catalog.current_database(),'CREATE')
            """)
            row = cursor.fetchone()
        return dict(state=state,current_member=row[0],current_usage=row[1],session_member=row[2],session_usage=row[3],database_create=row[4])

    def subscription_create():
        assert connection.get_autocommit() and not connection.in_atomic_block
        try:
            with connection.cursor() as cursor:
                # No publisher connection, slot, worker or data copy. Even an
                # accidental connection would target an absent fixture socket.
                cursor.execute("""CREATE SUBSCRIPTION ri_subscription_fixture
                    CONNECTION 'host=/nonexistent-fixture-only dbname=fixture_never_connect user=fixture_unused password=fixture_unused connect_timeout=1'
                    PUBLICATION ri_never_connected
                    WITH (connect=false,enabled=false,create_slot=false,copy_data=false,slot_name=NONE)
                """)
                assert cursor.statusmessage == "CREATE SUBSCRIPTION"
        except DatabaseError as exc:
            assert exc.__cause__.sqlstate == "42501"
            return dict(status=None,sqlstate="42501")
        return dict(status="CREATE SUBSCRIPTION",sqlstate=None)

    def subscription_drop():
        assert connection.get_autocommit() and not connection.in_atomic_block
        with connection.cursor() as cursor:
            cursor.execute("DROP SUBSCRIPTION ri_subscription_fixture")
            assert cursor.statusmessage == "DROP SUBSCRIPTION"
        return dict(dropped=True)

    def statistics_state(observer_pid):
        assert type(observer_pid) is int and observer_pid > 0
        state = authority_state()
        with connection.cursor() as cursor:
            cursor.execute("""SELECT
                pg_catalog.pg_has_role(current_user,'pg_read_all_stats'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(current_user,'pg_read_all_stats'::pg_catalog.name,'USAGE'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_read_all_stats'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_read_all_stats'::pg_catalog.name,'USAGE'::pg_catalog.text)
            """)
            roles = cursor.fetchone()
            cursor.execute("SELECT pg_catalog.pg_stat_clear_snapshot()")
            cursor.execute("""SELECT usename,query FROM pg_catalog.pg_stat_activity
                WHERE pid OPERATOR(pg_catalog.=) %s""", [observer_pid])
            activity = cursor.fetchone()
        assert activity is not None and activity[0] == 'postgres'
        return dict(state=state,current_member=roles[0],current_usage=roles[1],
                    session_member=roles[2],session_usage=roles[3],
                    observer_user=activity[0],observer_query=activity[1])

    def settings_state():
        state = authority_state()
        with connection.cursor() as cursor:
            cursor.execute("""SELECT
                pg_catalog.pg_has_role(current_user,'pg_read_all_settings'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(current_user,'pg_read_all_settings'::pg_catalog.name,'USAGE'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_read_all_settings'::pg_catalog.name,'MEMBER'::pg_catalog.text),
                pg_catalog.pg_has_role(session_user,'pg_read_all_settings'::pg_catalog.name,'USAGE'::pg_catalog.text)
            """)
            roles = cursor.fetchone()
            cursor.execute("""SELECT name,setting FROM pg_catalog.pg_settings
                WHERE name OPERATOR(pg_catalog.=) ANY (ARRAY['data_directory','config_file','hba_file']::pg_catalog.text[])
                ORDER BY name""")
            rows = cursor.fetchall()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_catalog.current_setting('data_directory'::pg_catalog.text)")
                value = cursor.fetchone()[0]
        except DatabaseError as exc:
            assert exc.__cause__.sqlstate == '42501'
            direct = dict(value=None,sqlstate='42501')
        else:
            direct = dict(value=value,sqlstate=None)
        return dict(state=state,current_member=roles[0],current_usage=roles[1],
                    session_member=roles[2],session_usage=roles[3],settings=rows,direct=direct)

    def check(entry):
        calls[0] = 0
        broker.reset_mock()
        error = None
        try:
            if entry == "schema":
                schema_presence.check_schema()
            elif entry == "runtime":
                preflight.check_runtime()
            elif entry == "command":
                call_command("check_job_runtime", stdout=io.StringIO())
            elif entry == "role":
                transport = preflight.connection
                try:
                    preflight.connection = connection
                    preflight.check_application_role()
                finally:
                    preflight.connection = transport
            elif entry == "role_command":
                call_command("check_job_runtime", require_application_role=True, stdout=io.StringIO())
            else:
                raise AssertionError("unknown_entry")
        except schema_presence.SchemaMismatch:
            error = "job_schema_invalid"
        except DatabaseError:
            # Direct schema callers receive the actual database error. Runtime
            # and command entrypoints must use the product's redacted failure.
            assert entry == "schema"
            error = "database_error"
        except (preflight.RuntimeUnavailable, CommandError) as exc:
            error = str(exc)
        return dict(error=error, broker_calls=broker.__enter__.return_value.ensure_connection.call_count)

    print(json.dumps(dict(ready=True, snapshot=snapshot(), controls=controls())), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        try:
            if request["action"] == "snapshot":
                result = snapshot()
            elif request["action"] == "controls":
                result = controls()
            elif request["action"] == "orphan":
                result = committed_orphan()
            elif request["action"] == "reconnect":
                connection.close()
                connection.ensure_connection()
                result = connection_state()
            elif request["action"] == "state":
                result = connection_state()
            elif request["action"] == "replication_controls":
                result = replication_controls()
            elif request["action"] == "search_path":
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public,pg_catalog" if request["public_first"] else "RESET search_path")
                result = connection_state()
            elif request["action"] == "checkpoint_state":
                result = checkpoint_state()
            elif request["action"] == "checkpoint_operation":
                result = checkpoint_operation()
            elif request["action"] == "checkpoint_switch":
                assert request["role"] in {"ri_cap_carrier", "ri_cap_child", "reset"}
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE" if request["role"] == "reset" else "SET ROLE " + request["role"])
                result = checkpoint_state()
            elif request["action"] == "maintain_state":
                result = maintain_state()
            elif request["action"] == "maintain_lock":
                result = maintain_lock()
            elif request["action"] == "maintain_unlock":
                result = maintain_unlock()
            elif request["action"] == "maintain_switch":
                assert request["role"] in {"ri_cap_carrier", "ri_cap_child", "reset"}
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE" if request["role"] == "reset" else "SET ROLE " + request["role"])
                result = maintain_state()
            elif request["action"] == "subscription_state":
                result = subscription_state()
            elif request["action"] == "subscription_create":
                result = subscription_create()
            elif request["action"] == "subscription_drop":
                result = subscription_drop()
            elif request["action"] == "subscription_switch":
                assert request["role"] in {"ri_cap_carrier", "ri_cap_child", "reset"}
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE" if request["role"] == "reset" else "SET ROLE " + request["role"])
                result = subscription_state()
            elif request["action"] == "statistics_state":
                result = statistics_state(request["observer_pid"])
            elif request["action"] == "statistics_switch":
                assert request["role"] in {"ri_cap_carrier", "ri_cap_child", "reset"}
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE" if request["role"] == "reset" else "SET ROLE " + request["role"])
                result = statistics_state(request["observer_pid"])
            elif request["action"] == "settings_state":
                result = settings_state()
            elif request["action"] == "settings_switch":
                assert request["role"] in {"ri_cap_carrier", "ri_cap_child", "reset"}
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE" if request["role"] == "reset" else "SET ROLE " + request["role"])
                result = settings_state()
            elif request["action"] == "authority_state":
                result = authority_state()
            elif request["action"] == "authority_switch":
                assert request["role"] in {"ri_cap_child", "reset"}
                with connection.cursor() as cursor:
                    cursor.execute("SET ROLE ri_cap_child" if request["role"] == "ri_cap_child" else "RESET ROLE")
                result = authority_state()
            elif request["action"] == "authority_search_path":
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public,pg_catalog" if request["public_first"] else "RESET search_path")
                result = authority_state()
            else:
                result = check(request["entry"])
            print(json.dumps(dict(ok=True, result=result)), flush=True)
        except Exception as exc:
            import traceback

            traceback.print_exc(file=sys.stderr)
            print(json.dumps(dict(ok=False, error=type(exc).__name__)), flush=True)


if __name__ == "__main__":
    main()
