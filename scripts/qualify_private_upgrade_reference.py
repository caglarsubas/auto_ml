"""Qualify the unchanged index recipe on a same-application previous-schema image.

This is a disclosed qualification fixture, not a historical/customer image.
"""

import contextlib
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

import private_api_package as api
import private_installation_plan as planner

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "backend/execution_jobs/migrations/0004_project_history_index.py"
def previous_schema_reference(source, image, migration_sha256):
    """Same verified application, with only the approved index migration absent."""
    import copy
    import re

    if (source.get("schema") != "private_api_source_v1"
            or not api.DIGEST.fullmatch(image)
            or not re.fullmatch("[0-9a-f]{40}", source.get("git_commit", ""))
            or not isinstance(source.get("source_sha256"), dict)
            or source["source_sha256"].get(MIGRATION) != migration_sha256
            or not re.fullmatch("[0-9a-f]{64}", migration_sha256)):
        raise planner.PlanError("upgrade_reference_current_source_binding")
    files = copy.deepcopy(source["source_sha256"])
    del files[MIGRATION]
    return {
        "schema": "private_reference_source_v1",
        "qualification_reconstruction_only": True,
        "customer_release_qualified": False,
        "fixture_basis": "same_current_application_previous_index_schema",
        "source_commit": source["git_commit"],
        "current_image": image,
        "removed_migration": {"path": MIGRATION, "sha256": migration_sha256},
        "source_sha256": files,
    }


def current_source(image):
    inventory = api.native_manifest(image)
    raw = api.run([
        "docker", "run", "--rm", "--pull", "never", "--network", "none",
        "--read-only", "--user", "10001:10001", "--cpus", "1", "--memory", "128m",
        "--pids-limit", "64", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--entrypoint", "python", image, "-I", "-c",
        "import sys;from pathlib import Path;sys.stdout.buffer.write(Path('/app/source-manifest.json').read_bytes())",
    ])
    if (not 0 < len(raw) <= api.MAX_METADATA_BYTES
            or hashlib.sha256(raw).hexdigest() != inventory["source_sha256"].get("source-manifest.json")):
        raise planner.PlanError("upgrade_reference_current_inventory_binding")
    source = json.loads(raw)
    if source.get("source_sha256") != {k: v for k, v in inventory["source_sha256"].items() if k != "source-manifest.json"}:
        raise planner.PlanError("upgrade_reference_current_inventory_binding")
    return source


RECONSTRUCT = r"""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify,snapshot
root=Path('/app');verify(root)
reference=json.loads(Path('/tmp/reference.json').read_bytes())
assert reference['schema']=='private_reference_source_v1'
assert reference['qualification_reconstruction_only'] is True and reference['customer_release_qualified'] is False
assert reference['fixture_basis']=='same_current_application_previous_index_schema'
source=json.loads((root/'source-manifest.json').read_bytes())
path='backend/execution_jobs/migrations/0004_project_history_index.py'
assert reference['removed_migration']=={'path':path,'sha256':source['source_sha256'][path]}
assert source['git_commit']==reference['source_commit']
assert {k:v for k,v in source['source_sha256'].items() if k!=path}==reference['source_sha256']
for name,digest in reference['source_sha256'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
(root/path).unlink()
# This is a synthetic variant of current code, not a historical Git tree.
source.update(source_sha256=reference['source_sha256'],working_tree_changes=True)
(root/'source-manifest.json').write_text(json.dumps(source,sort_keys=True,indent=2)+'\n')
(root/'runtime-manifest.json').unlink()
(root/'runtime-manifest.json').write_text(json.dumps(snapshot(root),sort_keys=True,indent=2)+'\n')
verify(root)
"""


def restore_original_api(directory, expected, current_image):
    """Leave the exact original tag-free input available after owned cleanup.

    On the classic Docker store removing the last temporary base/reference tags
    can delete an untagged parent image. Reconstitute its content-addressed
    identity from the same verified offline handoff, without pulls or tag writes.
    """
    raw = (directory / "manifest.json").read_bytes()
    if len(raw) > api.MAX_METADATA_BYTES or hashlib.sha256(raw).hexdigest() != expected:
        raise planner.PlanError("upgrade_reference_image_set_binding")
    pin = json.loads(raw)["components"]["api"]
    if set(pin) != {"image_id", "manifest_sha256"} or pin["image_id"] != current_image:
        raise planner.PlanError("upgrade_reference_original_image_binding")
    result = api.load(directory / "api", pin["manifest_sha256"])
    if (
        result["image_id"] != current_image
        or result["offline_image_verified"] is not True
    ):
        raise planner.PlanError("upgrade_reference_original_image_not_restored")
    return result


@contextlib.contextmanager
def reference_plan(directory, expected, current_image):
    """Remove only the approved index migration; export an exact offline fixture."""
    tag = "declarai-private-api:upgrade-reference-" + uuid.uuid4().hex
    identifier = None
    base = "declarai-upgrade-base:" + uuid.uuid4().hex
    base_tagged = False
    try:
        if api.run(["docker", "image", "ls", "--quiet", tag]).strip():
            raise api.PackageError("package_build_tag_exists")
        api.run(["docker", "image", "tag", current_image, base])
        base_tagged = True
        with tempfile.TemporaryDirectory(prefix="declarai-upgrade-reference-") as temp:
            temp = Path(temp)
            # Retain and verify the historical archive as historical evidence.
            # It cannot be substituted into an index-only compatibility recipe.
            from private_reference_source import sources
            sources(
                (ROOT / "docs/evidence/p167-previous-source.tar.gz").read_bytes(),
                (ROOT / "docs/evidence/p165-reference-source.json").read_bytes(),
                json.loads((ROOT / "docs/evidence/p167-previous-source.json").read_bytes()),
            )
            reference = previous_schema_reference(
                current_source(current_image), current_image,
                hashlib.sha256((ROOT / MIGRATION).read_bytes()).hexdigest(),
            )
            (temp / "reference.json").write_text(json.dumps(reference, sort_keys=True))
            (temp / "reconstruct.py").write_text(RECONSTRUCT)
            (temp / "Dockerfile").write_text(
                "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\nUSER 0:0\nCOPY reference.json reconstruct.py /tmp/\nRUN python -I -B /tmp/reconstruct.py && rm /tmp/reference.json /tmp/reconstruct.py\nUSER 10001:10001\n"
            )
            api.run(
                [
                    "docker",
                    "build",
                    "--provenance=false",
                    "--pull=false",
                    "--network=none",
                    "--build-arg",
                    "BASE_IMAGE=" + base,
                    "--tag",
                    tag,
                    str(temp),
                ],
                timeout=120,
            )
            identifier = api.inspect_image(tag)["Id"]
            api.native_manifest(identifier)
            bundle = temp / "bundle"
            bundle.mkdir()
            component = api.export(identifier, bundle / "api")
            # The normal planner verifies every archive against these pins.
            metadata = json.loads((directory / "manifest.json").read_bytes())
            if api.sha(directory / "manifest.json") != expected:
                raise planner.PlanError("upgrade_reference_image_set_binding")
            for role in ("ingress", "postgres", "redis"):
                (bundle / role).mkdir()
                for name in ("manifest.json", "image.tar"):
                    os.link(directory / role / name, bundle / role / name)
            metadata["components"]["api"] = {
                "image_id": identifier,
                "manifest_sha256": component["manifest_sha256"],
            }
            (bundle / "manifest.json").write_bytes(planner.encoded(metadata))
            request = {
                "schema": planner.SCHEMA,
                "installation_id": "qualification",
                "root": "/srv/declarai/qualification",
                "authority": "api.private.test:8443",
                "body_mib": 1,
                "bind_ip": "127.0.0.1",
                "database": {"name": "declarai_qualification", "user": "declarai_app"},
            }
            (temp / "request.json").write_bytes(planner.encoded(request))
            rendered = planner.render(
                temp / "request.json",
                bundle,
                api.sha(bundle / "manifest.json"),
                temp / "plan",
            )
            yield temp / "plan", rendered["plan_manifest_sha256"], identifier
    finally:
        try:
            if base_tagged and api.inspect_image(base)["Id"] == current_image:
                api.run(["docker", "image", "rm", "--no-prune", base])
            if identifier is not None and api.inspect_image(tag)["Id"] == identifier:
                api.run(["docker", "image", "rm", "--no-prune", tag])
        finally:
            restore_original_api(directory, expected, current_image)
