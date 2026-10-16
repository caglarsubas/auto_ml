"""Reserved service DNS identities cannot be borrowed by another container."""

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401
from tests.unit.test_private_dependency_start import startup, context, container, probe_container  # noqa: F401
from tests.unit.test_private_installation_adopt import adopter, profile, application  # noqa: F401

pytestmark = pytest.mark.unit


def inspection(startup, context, adopter, profile, role):
    if role in {"postgres", "cache", "job-broker"}:
        value, spec, receipt, image = context
        info = container(startup, context, role)
        return info, lambda: startup.validate(info, role, spec, startup.labels(value, receipt),
                                             image, startup.names(value)[role], True)
    if role == "dependency-check":
        value, spec, receipt, image = context
        info = probe_container(startup, context)
        return info, lambda: startup.validate_probe(info, value, spec, receipt, image)
    value, composition, digest, binding, image = profile
    if role in {"api", "worker", "dispatcher", "ingress"}:
        info = application(role, profile)
        return info, lambda: adopter.validate_application(info, role, composition["services"][role],
                                                        composition, digest, binding, image)
    info = application("api", profile)
    info["Name"] = "/declarai-" + role + "-fixture"
    info["Config"].update(Cmd=["preflight"], Labels={**binding, adopter.resources.LABEL + "role": role})
    info["HostConfig"].update(PidsLimit=64, NanoCpus=1_000_000_000, Memory=1024**3)
    info["Mounts"] = [m for m in info["Mounts"] if m["Type"] == "bind"]
    for mount in info["Mounts"]:
        mount["RW"] = False
    return info, lambda: adopter.validate_preflight(info, value, composition["services"]["api"]["environment"],
                                                   binding, image, role=role)


ROLES = ["postgres", "cache", "job-broker", "api", "worker", "dispatcher", "ingress",
         "dependency-check", "preflight", "schema", "accounts"]
CONFLICTS = [
    ("cache", "job-broker"), ("job-broker", "cache"), ("postgres", "cache"),
    ("api", "cache"), ("worker", "job-broker"), ("dispatcher", "postgres"),
    ("ingress", "api"), ("dependency-check", "postgres"), ("preflight", "cache"),
    ("schema", "job-broker"), ("accounts", "api"),
]


@pytest.mark.parametrize("role,borrowed", CONFLICTS)
@pytest.mark.parametrize("field", ["Aliases", "DNSNames"])
def test_cross_role_dns_identity_stops_inspection(startup, context, adopter, profile, role, borrowed, field):
    info, validate = inspection(startup, context, adopter, profile, role)
    validate()  # All unrelated profile controls are satisfied before mutation.
    endpoint = next(iter(info["NetworkSettings"]["Networks"].values()))
    endpoint[field] = [*(endpoint.get(field) or []), borrowed]
    with pytest.raises(adopter.checker.planner.PlanError, match="^installation_service_dns_conflict$"):
        validate()


@pytest.mark.parametrize("role", ROLES)
def test_own_and_generated_names_remain_usable(startup, context, adopter, profile, role):
    info, validate = inspection(startup, context, adopter, profile, role)
    for endpoint in info["NetworkSettings"]["Networks"].values():
        endpoint.update(Aliases=[role, "declarai-instance-" + role],
                        DNSNames=[role, "declarai-instance-" + role, "ab12cd34ef56"])
    validate()


@pytest.mark.parametrize("name", ["CACHE", "cache.", "CaChE."])
@pytest.mark.parametrize("field", ["Aliases", "DNSNames"])
def test_reserved_dns_comparison_normalizes_case_and_root_dot(startup, context, adopter, profile, name, field):
    info, validate = inspection(startup, context, adopter, profile, "api")
    next(iter(info["NetworkSettings"]["Networks"].values()))[field] = [name]
    with pytest.raises(adopter.checker.planner.PlanError, match="^installation_service_dns_conflict$"):
        validate()


@pytest.mark.parametrize("role", ["api", "preflight"])
def test_implicit_container_dns_name_also_cannot_borrow_a_role(startup, context, adopter, profile, role):
    info, validate = inspection(startup, context, adopter, profile, role)
    info["Name"] = "/cache"
    with pytest.raises(adopter.checker.planner.PlanError, match="^installation_service_dns_conflict$"):
        validate()


@pytest.mark.parametrize("field", ["Aliases", "DNSNames"])
@pytest.mark.parametrize("invalid", ["cache", [None], {"cache": True}])
def test_malformed_dns_metadata_stops_with_static_diagnostic(startup, context, adopter, profile, field, invalid):
    info, validate = inspection(startup, context, adopter, profile, "api")
    next(iter(info["NetworkSettings"]["Networks"].values()))[field] = invalid
    with pytest.raises(adopter.checker.planner.PlanError, match="^installation_service_dns_conflict$"):
        validate()
