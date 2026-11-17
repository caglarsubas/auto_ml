"""Exact additive RI-fixture profile for the reversible project-history index.

Retain the complete prior 164-role inventory and all original fault cases. The
new count is admitted only with the exact applied migration set and index proof.
"""

import copy
from native_assessment_schema_profile import qualify_native_assessment_schema

PREVIOUS_MIGRATIONS = [
    ("access_control", "0001_initial"),
    ("access_control", "0002_assistantactionapproval"),
    ("access_control", "0003_loginthrottlebucket_sessionauthority_and_more"),
    ("access_control", "0004_project_projectpolicy_projectartifact_and_more"),
    ("admin", "0001_initial"),
    ("admin", "0002_logentry_remove_auto_add"),
    ("admin", "0003_logentry_add_action_flag_choices"),
    ("auth", "0001_initial"),
    ("auth", "0002_alter_permission_name_max_length"),
    ("auth", "0003_alter_user_email_max_length"),
    ("auth", "0004_alter_user_username_opts"),
    ("auth", "0005_alter_user_last_login_null"),
    ("auth", "0006_require_contenttypes_0002"),
    ("auth", "0007_alter_validators_add_error_messages"),
    ("auth", "0008_alter_user_username_max_length"),
    ("auth", "0009_alter_user_last_name_max_length"),
    ("auth", "0010_alter_group_name_max_length"),
    ("auth", "0011_update_proxy_permissions"),
    ("auth", "0012_alter_user_first_name_max_length"),
    ("contenttypes", "0001_initial"),
    ("contenttypes", "0002_remove_content_type_name"),
    ("declaration", "0001_initial"),
    ("declaration", "0002_add_has_header"),
    ("deployment", "0001_initial"),
    ("deployment", "0002_packagereviewevent_evidence_and_more"),
    ("execution_jobs", "0001_initial"),
    ("execution_jobs", "0002_nativejob_source_dataset"),
    ("execution_jobs", "0003_nativeadoption_nativeprotectedinput_and_more"),
    ("modeling", "0001_initial"),
    ("modeling", "0002_holdoutaccess"),
    ("modeling", "0003_holdout_identity"),
    ("sessions", "0001_initial"),
]
MIGRATION = ("execution_jobs", "0004_project_history_index")
INDEX = [
    "native_job_project_history_idx",
    False,
    True,
    True,
    False,
    True,
    "CREATE INDEX native_job_project_history_idx ON public.execution_jobs_nativejob USING btree (project_id, created_at DESC, id DESC)",
]
REVIEW_MIGRATION = ("deployment", "0003_native_assessment_review")
REVIEW_FK_PROOF_SQL = """
    WITH foreign_key AS (
        SELECT k.*, local.attnotnull
        FROM pg_catalog.pg_constraint k
        JOIN pg_catalog.pg_attribute local ON local.attrelid = k.conrelid AND k.conkey = ARRAY[local.attnum]
        JOIN pg_catalog.pg_attribute target ON target.attrelid = k.confrelid AND k.confkey = ARRAY[target.attnum]
        WHERE k.contype = 'f'
            AND k.conrelid = 'public.deployment_packagereview'::regclass AND local.attname = 'native_assessment_id'
            AND k.confrelid = 'public.execution_jobs_nativejob'::regclass AND target.attname = 'id'
    )
    SELECT json_build_object(
        'constraints', (SELECT json_agg(json_build_array(
            convalidated, condeferrable, condeferred, confmatchtype, confupdtype, confdeltype, attnotnull))
            FROM foreign_key),
        'roles', (SELECT json_agg(json_build_array(t.oid::bigint, t.tgrelid::regclass::text, p.proname) ORDER BY t.oid)
            FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
            JOIN foreign_key k ON k.oid = t.tgconstraint WHERE t.tgisinternal)
    )
"""
REVIEW_FK_ROLES = {
    ("deployment_packagereview", "RI_FKey_check_ins"),
    ("deployment_packagereview", "RI_FKey_check_upd"),
    ("execution_jobs_nativejob", "RI_FKey_noaction_del"),
    ("execution_jobs_nativejob", "RI_FKey_noaction_upd"),
}


def qualify_project_history_schema(snapshot, proof):
    expected = sorted([list(row) for row in PREVIOUS_MIGRATIONS] + [list(MIGRATION)])
    if (
        snapshot["migrations"] != 33
        or set(proof) != {"migrations", "indexes"}
        or proof["migrations"] != expected
        or proof["indexes"] != [INDEX]
    ):
        raise ValueError("project_history_fixture_schema_profile_changed")
    previous = copy.deepcopy(snapshot)
    previous["migrations"] = 32
    old = qualify_native_assessment_schema(previous)
    return {
        "schema": "project_history_schema_profile_v1",
        "migrations": 33,
        "internal_triggers": 164,
        "previous_profile": old,
        "added_migration": list(MIGRATION),
        "physical_index": INDEX,
        "all_roles_require_fault_testing": True,
    }


def qualify_independent_review_schema(snapshot, proof):
    """Require the exact independent-review FK plus every predecessor role."""
    migrations = proof["migrations"]
    foreign_key = proof["review_fk"]
    roles = foreign_key["roles"] or ()
    migration = list(REVIEW_MIGRATION)
    rows = snapshot["all_internal"]
    new_ids = {row[0]: row[1] for row in roles}
    if (
        snapshot["migrations"] != 34
        or snapshot["internal_triggers"] != 168
        or len(rows) != 168
        or len({row[0] for row in rows}) != 168
        or set(proof) != {"migrations", "indexes", "review_fk"}
        or migrations.count(migration) != 1
        or foreign_key["constraints"] != [[True, True, True, "s", "a", "a", False]]
        or len(roles) != 4
        or len(new_ids) != 4
        or {tuple(row[1:]) for row in roles} != REVIEW_FK_ROLES
        or {row[0]: row[1] for row in rows if row[0] in new_ids} != new_ids
    ):
        raise ValueError("independent_review_fixture_schema_profile_changed")
    previous = {"migrations": 33, "internal_triggers": 164,
                "all_internal": [row for row in rows if row[0] not in new_ids]}
    old = qualify_project_history_schema(previous, {
        "migrations": [row for row in migrations if row != migration], "indexes": proof["indexes"],
    })
    return {
        "schema": "independent_review_schema_profile_v1",
        "migrations": 34,
        "internal_triggers": 168,
        "previous_profile": old,
        "added_migration": migration,
        "native_assessment_foreign_key": foreign_key,
        "all_roles_require_fault_testing": True,
    }
