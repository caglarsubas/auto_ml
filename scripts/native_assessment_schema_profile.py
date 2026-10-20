"""Exact additive RI-fixture profile for the protected native schema migration.

The controller keeps its original legacy bootstrap assertion and entire fault
matrix. This profile requires the old per-table inventory plus all twelve new
trigger roles; the controller subsequently tests every role in the full schema.
"""

from collections import Counter

LEGACY_ROLES = {
    "access_control_assistantactionapproval": 2,
    "access_control_authenticationevent": 2,
    "access_control_mcpaccessevent": 4,
    "access_control_mcpdatasetgrant": 6,
    "access_control_project": 14,
    "access_control_projectartifact": 4,
    "access_control_projectauthorityevent": 4,
    "access_control_projectdataset": 4,
    "access_control_projectmembership": 4,
    "access_control_projectpipeline": 4,
    "access_control_sessionauthority": 2,
    "auth_group": 4,
    "auth_group_permissions": 4,
    "auth_permission": 6,
    "auth_user": 26,
    "auth_user_groups": 4,
    "auth_user_user_permissions": 4,
    "declaration_datadictionary": 2,
    "declaration_declaration": 14,
    "deployment_packagereview": 6,
    "deployment_packagereviewevent": 6,
    "django_admin_log": 4,
    "django_content_type": 4,
    "execution_jobs_jobevent": 2,
    "execution_jobs_nativejob": 12,
    "modeling_holdoutaccess": 2,
    "modeling_pipelinerun": 2,
}
ADDED_ROLES = {
    "execution_jobs_nativejob": 2,
    "execution_jobs_nativeadoption": 6,
    "execution_jobs_nativeadoptionevent": 2,
    "execution_jobs_nativeprotectedinput": 2,
}


def qualify_native_assessment_schema(snapshot):
    rows = snapshot["all_internal"]
    expected = Counter(LEGACY_ROLES) + Counter(ADDED_ROLES)
    if (
        snapshot["migrations"] != 32
        or snapshot["internal_triggers"] != 164
        or len(rows) != 164
        or len({row[0] for row in rows}) != 164
        or Counter(row[1] for row in rows) != expected
    ):
        raise ValueError("native_assessment_fixture_schema_profile_changed")
    return {
        "schema": "native_assessment_schema_profile_v1",
        "migrations": 32,
        "internal_triggers": 164,
        "legacy_migrations": 31,
        "legacy_internal_triggers": 152,
        "legacy_roles_by_table": LEGACY_ROLES,
        "additional_roles_by_table": ADDED_ROLES,
        "all_roles_require_fault_testing": True,
    }
