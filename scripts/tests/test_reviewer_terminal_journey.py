"""Regressions for the independent reviewer's two-case terminal session and saved assessments."""

import json
from pathlib import Path
import secrets
import shutil
import sqlite3
from contextlib import closing
import sys
import uuid
from unittest.mock import Mock

import pytest

from tests.qualification.reviewer_journey_fixture import reviewer_journey  # noqa: F401
from tests.qualification.reviewer_journey_runtime import BACKEND, digest
from tests.qualification.reviewer_terminal import Terminal

pytestmark = [pytest.mark.uat, pytest.mark.regression]


def save(path, value):
    path.write_text(json.dumps(value))


def read(path):
    return json.loads(path.read_bytes())


def prepare_exercise(installation):
    root = installation["root"] / "exercise"
    root.mkdir(mode=0o700)
    source = BACKEND.parent / "scripts/review_exercise"
    for name in ("Start Review.command", "participant.py"):
        shutil.copy2(source / name, root / name)
    # Only the installation adapter differs from the operator-provisioned Mac bundle.
    (root / "review_installation.py").write_text(
        "from pathlib import Path\n"
        "from tests.qualification.reviewer_journey_runtime import TestInstallation\n"
        "site = TestInstallation(Path(__file__).resolve().parent)\n"
    )
    save(root / "scope.json", {"reviewer_username": installation["reviewer_username"]})
    save(root / "project.json", {"project_id": installation["project_id"]})
    (root / "runtime-id").write_text(digest(BACKEND / "deployment/offline_reproduce.py"))
    cases = []
    for case in installation["cases"]:
        folder = root / case["task"]
        folder.mkdir()
        shutil.copyfile(case["proposal_file"], folder / "proposal.json")
        save(
            folder / "request-ids.json",
            {step: str(uuid.uuid4()) for step in ("adoption", "assessment", "seal", "review")},
        )
        cases.append(
            {
                **case,
                "development_file": str(case["development_file"]),
                "outcome_file": str(case["outcome_file"]),
                "development_sha256": digest(case["development_file"]),
                "outcomes_sha256": digest(case["outcome_file"]),
            }
        )
    save(root / "fixture.json", {"api": installation["api"], "cases": cases})
    return root


def enrolled_accounts(installation):
    db = (installation["root"] / "fixture.sqlite3").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(db, uri=True)) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM auth_user WHERE username = ?", (installation["reviewer_username"],)
        ).fetchone()[0]


def choice(tty, question, answer):
    tty.expect(question)
    tty.expect("Choice: ")
    tty.reply(answer)


def rationale(tty, question, value):
    tty.expect(question)
    tty.expect("> ")
    tty.reply(value)


def authorize_assessment(tty, root, case):
    task = case["task"]
    tty.expect(f"{task.upper()} • protected assessment only")
    evidence = tty.expect("Your candidate decision")
    assert case["proposal_sha256"] in evidence and case["training_result_sha256"] in evidence
    assert "80 development rows" in evidence and "12 months" in evidence
    metric, positive = ("roc_auc", "bad") if task == "classification" else ("rmse", "not applicable")
    proposal = read(root / task / "proposal.json")
    assert proposal["proposal"]["prediction_contract"]["task"] == task
    assert proposal["proposal"]["metric"]["primary_metric"] == metric
    assert str(root / task / "proposal.json") in evidence
    assert f"Selection metric: {metric}" in evidence and f"positive class: {positive}" in evidence
    tty.expect("Choice: ")
    tty.reply("a")
    rationale(tty, "Why do you accept this exact candidate", "Synthetic candidate accepted for assessment only.")
    choice(tty, "Can you attest this synthetic population", "y")
    rationale(
        tty, "Record your population and maturity rationale.", "Reserved synthetic outcomes have complete follow-up."
    )
    choice(tty, "Authorize computing this exact exploratory assessment?", "y")


def expect_replay_prompt(tty, case):
    metric = "roc_auc" if case["task"] == "classification" else "rmse"
    tty.expect("Assessment outcome:", timeout=45)
    displayed = tty.expect("Countersign these exact inputs")
    assert metric in displayed and "60 rows" in displayed and "Evidence limitation:" in displayed
    assert case["scores_sha256"] in displayed and case["model_sha256"] in displayed
    tty.expect("Choice: ")


def complete_review(tty, root, case):
    task = case["task"]
    tty.reply("y")
    tty.expect("Exact model, assessment and ordered scores reproduced on 60 rows.", timeout=60)
    action = "a" if task == "classification" else "f"
    choice(tty, "What does the evidence justify?", action)
    if action == "f":
        choice(tty, "Finding severity", "minor")
    rationale(tty, "Record your own finding or disposition", f"Synthetic {task} review: limited to this sample.")
    folder = root / task
    assert [event["event_type"] for event in read(folder / "review-snapshot.json")["events"]] == ["opened"]
    choice(tty, "Submit this decision under your named review account?", "y")
    tty.expect("Saved technical review:")


@pytest.mark.parametrize(
    ("strategy", "window_checked", "chronology", "displayed"),
    [
        ("random", False, {}, "not recorded"),
        ("oot", True, {}, "not recorded"),
        ("random", False, {"chronology_checked": False}, "False"),
        ("oot", False, {"chronology_checked": True}, "True"),
    ],
)
def test_assessment_design_reports_recorded_chronology(
    monkeypatch, capsys, strategy, window_checked, chronology, displayed
):
    monkeypatch.syspath_prepend(str(BACKEND.parent / "scripts"))
    from review_exercise.participant import print_assessment_design

    print_assessment_design(
        {
            "strategy": strategy,
            "entity_separation_checked": False,
            "outcome_window_checked": window_checked,
            **chronology,
        }
    )
    output = capsys.readouterr().out
    assert f"temporal ordering checked: {displayed}" in output
    assert f"outcome window checked: {window_checked}" in output
    assert "entity separation checked: False" in output


def test_resume_stops_before_export_when_live_assessment_hash_differs(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND.parent / "scripts"))
    from review_exercise import participant

    job_id = str(uuid.uuid4())
    spec = {
        "kind": "native_protected_assessment_v1",
        "protected_input_id": "synthetic-input",
        "assessment_sha256": "a" * 64,
        "adoption_id": "synthetic-adoption",
    }
    receipt = {
        "id": job_id,
        "state": "succeeded",
        "project_id": "synthetic-project",
        "file_id": 1,
        "specification": spec,
        "result": {"n_assessed": 60},
        "result_sha256": "b" * 64,
    }
    request = {"request_id": job_id, **{key: spec[key] for key in ("kind", "protected_input_id", "assessment_sha256")}}
    save(tmp_path / "assessment-request.json", request)
    save(tmp_path / "assessment-receipt.json", receipt)
    response = Mock()
    response.json.return_value = {**receipt, "result_sha256": "c" * 64}
    call = Mock(return_value=response)
    monkeypatch.setattr(participant, "call", call)
    session = object()
    with pytest.raises(participant.ExercisePaused, match="saved assessment differs"):
        participant.assess(
            None,
            session,
            receipt["project_id"],
            tmp_path,
            {"id": spec["adoption_id"], "file_id": receipt["file_id"]},
            spec["protected_input_id"],
            "classification",
            {"assessment": job_id},
        )
    call.assert_called_once_with(session, receipt["project_id"], "GET", f"jobs/{job_id}/")
    assert read(tmp_path / "assessment-receipt.json") == receipt
    assert not (tmp_path / "approved").exists()


def test_reviewer_retries_enrollment_resumes_reviews_both_cases_and_withholds_acceptance(reviewer_journey):  # noqa: F811
    installation = reviewer_journey
    root = prepare_exercise(installation)
    command = [str(root / "Start Review.command")]
    environment = dict(installation["env"])
    environment["PATH"] = str(Path(sys.executable).parent) + ":" + environment["PATH"]
    password = secrets.token_urlsafe(32)
    # This one passes the launcher's length/variety rule and fails Django's numeric-password validator.
    rejected = "01234567890123456789"
    with Terminal(command, root, environment) as tty:
        tty.expect("New exercise passphrase (hidden): ")
        tty.reply("short", hidden=True)
        tty.expect("Use at least 16 characters")
        tty.expect("New exercise passphrase (hidden): ")
        tty.reply(password, hidden=True)
        tty.expect("Confirm (hidden): ")
        tty.reply(secrets.token_urlsafe(32), hidden=True)
        tty.expect("The two entries differed. Try again.")
        tty.expect("New exercise passphrase (hidden): ")
        tty.reply(rejected, hidden=True)
        tty.expect("Confirm (hidden): ")
        tty.reply(rejected, hidden=True)
        tty.expect("The account rejected that passphrase.")
        assert not (root / "human-account.json").exists()
        assert enrolled_accounts(installation) == 0
        tty.expect("New exercise passphrase (hidden): ")
        tty.reply(password, hidden=True)
        tty.expect("Confirm (hidden): ")
        tty.reply(password, hidden=True)
        choice(tty, "Your candidate decision", "p")
        tty.finish()

    account = read(root / "human-account.json")
    assert account["role"] == "reviewer"
    assert enrolled_accounts(installation) == 1
    assert not list(root.glob("*/adoption-request.json"))
    assert not list(root.glob("*/assessment-receipt.json"))
    assert not list(root.glob("owner-decision-*.json"))

    classification, regression = installation["cases"]
    with Terminal(command, root, environment) as tty:
        tty.expect("Exercise passphrase (hidden): ")
        tty.reply(password, hidden=True)
        authorize_assessment(tty, root, classification)
        expect_replay_prompt(tty, classification)
        tty.reply("p")
        tty.finish()

    folder = root / "classification"
    receipt = folder / "assessment-receipt.json"
    job_id = read(receipt)["id"]
    manifest = folder / "approved" / "reproduction-manifest.json"
    original = {path: digest(path) for path in (receipt, manifest, folder / "assessment-request.json")}
    assert not (folder / "successful-replay.json").exists()
    assert not (folder / "review-snapshot.json").exists()
    server_log = installation["root"] / "installation.log"
    resume_offset = server_log.stat().st_size
    with Terminal(command, root, environment) as tty:
        tty.expect("Exercise passphrase (hidden): ")
        tty.reply(password, hidden=True)
        expect_replay_prompt(tty, classification)
        with server_log.open("rb") as log:
            log.seek(resume_offset)
            resumed = log.read().decode()
        assert f"GET /api/jobs/{job_id}/?" in resumed
        assert f"GET /api/jobs/{job_id}/reproduction/?" in resumed
        assert "POST /api/jobs/" not in resumed and "POST /api/native-protected-inputs/" not in resumed
        assert {path: digest(path) for path in original} == original
        complete_review(tty, root, classification)
        authorize_assessment(tty, root, regression)
        expect_replay_prompt(tty, regression)
        complete_review(tty, root, regression)
        choice(tty, "As scope owner, does the evidence satisfy the synthetic exercise?", "h")
        rationale(
            tty,
            "Record the evidence and limitations behind your exercise decision.",
            "Resolve the regression finding first.",
        )
        choice(tty, "Add an observation on the reviewer experience?", "s")
        tty.expect("Your records are saved privately.")
        tty.finish()

    (owner_path,) = root.glob("owner-decision-*.json")
    owner = read(owner_path)
    assert owner["owner"] == installation["reviewer_username"]
    assert owner["decision"] == "withheld"
    assert owner["reason"] == "Resolve the regression finding first."
    assert set(owner["cases"]) == {"classification", "regression"}
    assert not list(root.glob("reviewer-observation-*.json"))
    for case in installation["cases"]:
        task = case["task"]
        folder = root / task
        review = read(folder / "review-snapshot.json")
        approval = task == "classification"
        event = review["events"][-1]
        assert [row["event_type"] for row in review["events"]] == ["opened", "approve" if approval else "finding"]
        assert event["actor"]["username"] == installation["reviewer_username"]
        assert event["text"] == f"Synthetic {task} review: limited to this sample."
        assert review["review_approved"] is approval and review["production_use_approved"] is False
        assert owner["cases"][task]["review_snapshot_sha256"] == digest(folder / "review-snapshot.json")
        assessment = read(folder / "assessment-receipt.json")
        assert review["assessment_job_id"] == assessment["id"]
        assert assessment["result"]["confirmatory"] is False
        replay = read(folder / "successful-replay.json")
        assert owner["cases"][task]["binding"] == replay
        assert owner["cases"][task]["review_state"] == review["decision"]
        original = folder / "replays" / replay["attempt"] / "reproduction-report.json"
        assert digest(original) == replay["report_file_sha256"]
        report = read(original)
        assert report["model_refit_reproduced"] is True and report["assessment_reproduced"] is True
        assert report["manifest_sha256"] == review["manifest_sha256"]
        assert report["assessment_result_sha256"] == review["assessment_result_sha256"] == assessment["result_sha256"]
        assert report["task"] == task and report["n_assessed"] == 60
        assert report["scores_sha256"] == case["scores_sha256"] and report["model_sha256"] == case["model_sha256"]
        if approval:
            assert event["details"]["report"] == report
        else:
            assert review["findings"][0]["state"] == "open" and review["findings"][0]["severity"] == "minor"
    # No plaintext credential may enter participant evidence.
    assert not any(password.encode() in path.read_bytes() for path in installation["root"].rglob("*") if path.is_file())
