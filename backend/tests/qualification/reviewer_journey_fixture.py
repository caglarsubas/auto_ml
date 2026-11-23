"""Disposable loopback installation for the independent reviewer's terminal journey."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid
from wsgiref.simple_server import make_server

import pytest


BACKEND = Path(__file__).resolve().parents[2]
MODULE = "tests.qualification.reviewer_journey_fixture"
MARKER = ".synthetic-review-fixture"
READINESS = "ready.json"


def _environment(root):
    # Qualified CI images mount their test-only packages here.
    paths = [str(BACKEND)]
    overlay = Path("/opt/declarai-qualification")
    if overlay.is_dir():
        paths.append(str(overlay))
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(root),
        "PYTHONPATH": os.pathsep.join(paths),
        "DJANGO_SETTINGS_MODULE": "backend.settings",
        "DECLARAI_RUNTIME_PROFILE": "development",
        "DECLARAI_DB_ENGINE": "sqlite",
        "DECLARAI_MEDIA_ROOT": str(root / "media"),
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,testserver",
        "OPENBLAS_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PROMETA_DISABLE": "1",
    }


def _configure(root, *, creating):
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("synthetic_fixture_root_required")
    marker = root / MARKER
    if marker.is_symlink() or marker.read_text() != MARKER:
        raise ValueError("synthetic_fixture_marker_required")
    db = root / "fixture.sqlite3"
    if db.is_symlink() or (db.exists() if creating else not db.is_file()):
        raise ValueError("synthetic_fixture_database_unavailable")
    env = _environment(root)
    os.environ.clear()
    os.environ.update(env)
    import django
    from django.conf import settings

    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.sqlite3" or Path(settings.MEDIA_ROOT) != root / "media":
        raise ValueError("synthetic_fixture_scope_changed")
    database["NAME"] = str(db)
    settings.DECLARAI_JOBS_ENABLED = True
    django.setup()


def _input_rows(task, *, protected):
    count = 60 if protected else 80
    rows = ["x,z,outcome"]
    for i in range(count):
        x = (10 if protected else 0) + i / count
        outcome = i % 4 if task == "regression" else ("bad" if i % 2 else "good")
        rows.append(f"{x},{i % 7},{outcome}")
    return ("\n".join(rows) + "\n").encode("ascii")


def _seed(root):
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.test import Client

    from access_control import projects
    from access_control.models import Project, ProjectMembership, ProjectPolicy
    from declaration.models import Declaration
    from deployment import native_candidate
    from execution_jobs import service
    from execution_jobs.models import NativeJob
    from modeling.native_assessment_replay import CHUNK_SIZE
    from modeling.native_training_replay import parsed_frame
    from tests.unit.test_durable_training_search import admission, queue
    from tests.unit.test_governed_foundation import declaration
    from tests.unit.test_native_protected_assessment import proposal

    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Synthetic terminal review exercise")
    developer = get_user_model().objects.create_user(username="synthetic-handoff-developer")
    ProjectMembership.objects.create(project=project, actor=developer, role="developer")
    session = Client()
    session.force_login(developer)

    cases = []
    for task in ("classification", "regression"):
        custody = root / "synthetic-inputs" / task
        custody.mkdir(parents=True)
        development = custody / "development.csv"
        outcomes = custody / "outcomes.csv"
        development.write_bytes(_input_rows(task, protected=False))
        outcomes.write_bytes(_input_rows(task, protected=True))

        dataset = Declaration.objects.create(name=f"Synthetic {task}", original_name=development.name)
        dataset.file.save(f"journey-{task}.csv", ContentFile(development.read_bytes()))
        projects.bind_dataset(dataset, project.pk, source="reviewer_journey_fixture")
        world = SimpleNamespace(file_id=dataset.pk, clients={"developer": session})
        options = {
            "data_role": "development_only",
            "business_understanding": declaration(task, positive="bad" if task == "classification" else None),
            "features": ["x", "z"],
            "validation": {"strategy": "random", "n_splits": 2},
        }
        request, _ = admission(world, options)
        identifier = queue(world, request)
        service.execute(identifier)
        world.trained = NativeJob.objects.get(pk=identifier)
        assert world.trained.state == "succeeded", world.trained.reason_code
        adoption = proposal(world)
        (custody / "proposal.json").write_text(json.dumps(adoption))
        # Pin the expected scores before any participant action. Only the synthetic
        # feature columns enter the frozen candidate's offline scoring function.
        trained = world.trained
        export = native_candidate.export_candidate(
            trained.pk, dataset.pk, project.pk, trained.result, trained.result_sha256
        )
        features = parsed_frame(outcomes.read_bytes())[trained.result["features"]].to_csv(index=False).encode()
        scored = native_candidate.score(export, native_candidate.sha(export), features, chunk_size=CHUNK_SIZE)
        cases.append(
            {
                "task": task,
                "file_id": dataset.pk,
                "training_job_id": str(identifier),
                "training_result_sha256": world.trained.result_sha256,
                "adoption_id": adoption["id"],
                "proposal_file": str(custody / "proposal.json"),
                "proposal_sha256": adoption["proposal_sha256"],
                "model_sha256": scored["model_sha256"],
                "scores_sha256": native_candidate.sha(native_candidate.canonical(scored["scores"])),
                "development_file": str(development),
                "outcome_file": str(outcomes),
            }
        )
    return {
        "project_id": str(project.pk),
        "reviewer_username": "synthetic-reviewer-" + uuid.uuid4().hex[:12],
        "cases": cases,
    }


def _serve(root):
    _configure(root, creating=True)
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from execution_jobs import service
    from execution_jobs.models import NativeJob

    (root / "media").mkdir(exist_ok=True)
    call_command("migrate", verbosity=0, interactive=False)
    bindings = _seed(root)
    with make_server("127.0.0.1", 0, get_wsgi_application()) as server:
        bindings["api"] = f"http://127.0.0.1:{server.server_port}/api/"
        temporary = root / "starting.json"
        temporary.write_text(json.dumps(bindings))
        temporary.replace(root / READINESS)
        while True:
            server.handle_request()
            # A subsequent status request observes the real worker result.
            for job_id in list(NativeJob.objects.filter(state="queued").values_list("pk", flat=True)):
                service.execute(str(job_id))


def _enroll(root):
    _configure(root, creating=False)
    from access_control.enrollment import EnrollmentDenied, enroll, specification

    data = json.load(sys.stdin)
    bindings = json.loads((root / READINESS).read_text())
    if data["project"] != bindings["project_id"] or data["username"] != bindings["reviewer_username"]:
        raise ValueError("synthetic_fixture_enrollment_scope")
    spec = specification(data["username"], "synthetic-terminal-exercise", "reviewer", project_id=data["project"])
    try:
        event, replayed = enroll(spec, data["request"], data["password"])
    except EnrollmentDenied as exc:
        code = str(exc)
        print(code if re.fullmatch(r"enrollment_[a-z_]+", code) else "enrollment_denied", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "event_id": str(event.pk),
                "subject_user_id": event.subject_snapshot["id"],
                "project_id": event.details["project_id"],
                "role": event.details["scope"]["role"],
                "authority_source": event.authority_source,
                "replayed_receipt": replayed,
                "global_privileges_granted": False,
                "model_use_approved": False,
            }
        )
    )
    return 0


@pytest.fixture
def reviewer_journey(tmp_path):
    """Provide a child installation independent of the parent suite's database and service environment."""
    root = tmp_path / "reviewer-installation"
    root.mkdir(mode=0o700)
    (root / MARKER).write_text(MARKER)
    env = _environment(root)
    command = [sys.executable, "-m", MODULE, "serve", str(root)]
    log = root / "installation.log"
    with log.open("wb") as output:
        process = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            ready = root / READINESS
            while not ready.is_file():
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("Disposable installation failed to start.\n" + log.read_text(errors="replace")[-4000:])
                time.sleep(0.05)
            configuration = json.loads(ready.read_text())
            for case in configuration["cases"]:
                for key in ("development_file", "outcome_file"):
                    case[key] = Path(case[key])
            yield dict(configuration, root=root, env=env)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "enroll"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.command == "serve":
        _serve(args.root)
    else:
        try:
            result = _enroll(args.root)
        except Exception:
            print("enrollment_transaction_unavailable", file=sys.stderr)
            result = 1
        sys.exit(result)
