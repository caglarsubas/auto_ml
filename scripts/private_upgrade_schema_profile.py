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
