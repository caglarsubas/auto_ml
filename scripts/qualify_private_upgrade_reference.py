"""Reconstruct exact previous source bytes on the current locked dependency image.

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
RECONSTRUCT = r"""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify,snapshot
sys.path.insert(0,'/tmp')
from reference_reader import sources
root=Path('/app');verify(root)
reference,files=sources(Path('/tmp/previous.tar.gz').read_bytes(),Path('/tmp/reference.json').read_bytes(),json.loads(Path('/tmp/archive.json').read_bytes()))
source=json.loads((root/'source-manifest.json').read_bytes())
# The current image may evolve. The previous source stays exact: no current
# application file survives unless its bytes are in the frozen old inventory.
for name in source['source_sha256']:
    path=Path(name)
    assert not path.is_absolute() and '..' not in path.parts and str(path)==name
    if name not in files:(root/path).unlink()
for name,data in files.items():
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==reference['source_sha256'][name]
source.update(source_sha256=reference['source_sha256'],git_commit=reference['source_commit'],working_tree_changes=False)
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
    """Verify all old source bytes; export and verify a genuine offline image set."""
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
            (temp / "reference.json").write_bytes(
                (ROOT / "docs/evidence/p165-reference-source.json").read_bytes()
            )
            from private_reference_source import sources
            archive = (ROOT / "docs/evidence/p167-previous-source.tar.gz").read_bytes()
            pin = (ROOT / "docs/evidence/p167-previous-source.json").read_bytes()
            sources(archive, (temp / "reference.json").read_bytes(), json.loads(pin))
            (temp / "previous.tar.gz").write_bytes(archive)
            (temp / "archive.json").write_bytes(pin)
            (temp / "reference_reader.py").write_bytes((ROOT / "scripts/private_reference_source.py").read_bytes())
            (temp / "reconstruct.py").write_text(RECONSTRUCT)
            (temp / "Dockerfile").write_text(
                "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\nUSER 0:0\nCOPY reference.json reconstruct.py reference_reader.py previous.tar.gz archive.json /tmp/\nRUN python -I -B /tmp/reconstruct.py && rm /tmp/reference.json /tmp/reconstruct.py /tmp/reference_reader.py /tmp/previous.tar.gz /tmp/archive.json\nUSER 10001:10001\n"
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
