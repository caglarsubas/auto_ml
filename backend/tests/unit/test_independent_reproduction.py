"""Reproduce exact worker outputs without opening installation outcome storage."""

import copy
import json
import uuid
from unittest.mock import patch

import pandas as pd
import pytest
from django.db import connection
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import CaptureQueriesContext

from deployment import native_candidate, offline_reproduce
from execution_jobs import service
from execution_jobs.models import NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_governed_foundation import declaration
from tests.unit.test_native_protected_assessment import approve, proposal, queued, seal
from tests.unit.test_prospective_assessment import prospective, seal as prospective_seal  # noqa: F401


pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def export(w, identifier):
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded", job.reason_code
    request = f"/api/jobs/{identifier}/reproduction/?sha256={job.result_sha256}"
    with CaptureQueriesContext(connection) as queries:
        response = w.clients["reviewer"].get(request)
    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    assert response["X-DeclarAI-Export-SHA256"] == native_candidate.sha(response.content)
    assert response["Content-Disposition"] == f'attachment; filename="reproduction-{identifier}.json"'
    payload = f'"{NativeProtectedInput._meta.db_table}"."payload"'
    assert not any(payload in query["sql"] for query in queries)
    value = response.json()
    assert "model_json" not in value["training"]["fit"]
    assert not set(value["assessment"]["result"]) & {"labels", "scores", "payload"}
    path = w.root / "manifest.json"
    path.write_bytes(response.content)
    return path, response["X-DeclarAI-Export-SHA256"], request


def test_reproduce_temporal_first_use_in_separate_custody(prospective):
    w = prospective
    response, raw, seal_id = prospective_seal(w, w.outcomes)
    assert response.status_code == 200, response.content
    identifier = queued(w, {"id": seal_id})
    service.execute(identifier)
    manifest, digest, _ = export(w, identifier)
    outcomes = w.root / "reviewer-protected.csv"
    outcomes.write_bytes(raw)
    with patch("pickle.load", side_effect=AssertionError("Serialized state cannot enter replay.")):
        report = offline_reproduce.reproduce(manifest, digest, w.path, outcomes)
    assert report["task"] == "classification"
    assert report["model_refit_reproduced"] and report["assessment_reproduced"]
    assert not any(report[key] for key in ("confirmation_granted", "review_approved", "production_use_approved"))
    assert HoldoutAccess.objects.count() == 1
    assert HoldoutAccess.objects.get().evidence_status == "confirmatory"


def test_reproduce_regression_blocks_altered_evidence_or_authority(world):
    w = world
    options = copy.deepcopy(w.options)
    options["business_understanding"] = declaration("regression")
    options['business_understanding']['exclusions'] = 'Rows without a complete outcome window'
    options['business_understanding']['feature_availability']['overrides'] = {'entity': 'excluded', 'x': 'available_at_prediction'}
    options['business_understanding']['target_contract']['outcome_window'] = {
        'horizon_days': 1, 'maturity_lag_days': 3, 'development_as_of': '2020-06-01T00:00:00Z',
    }
    options['validation'] = {'strategy': 'oot', 'date_column': 'date', 'label_end_column': 'end', 'n_splits': 2}
    w.frame["outcome"] = [10.0, 20.0] * 60
    w.frame.to_csv(w.path, index=False)
    body, _ = admission(w, options)
    job_id = queue(w, body)
    service.execute(job_id)
    w.trained = NativeJob.objects.get(pk=job_id)
    p = approve(w, proposal(w))
    frame = pd.DataFrame({"z": [None, 2.0, 4.0] * 20, "x": range(60), "outcome": [10.0, 20.0] * 30})
    frame['date'] = pd.date_range('2021-01-01', periods=60).strftime('%Y-%m-%d')
    frame['end'] = pd.date_range('2021-01-02', periods=60).strftime('%Y-%m-%d')
    immature = frame.copy()
    immature.loc[59, 'end'] = '2026-10-20'
    denied = w.clients['reviewer'].post(f"/api/native-adoptions/{p['id']}/protected-inputs/", {
        'request_id': str(uuid.uuid4()), 'proposal_sha256': p['proposal_sha256'],
        'rationale': 'Complete outcome maturity required for this frozen candidate.',
        'assessment_as_of': '2026-10-21T00:00:00Z', 'population_and_maturity_attested': 'true',
        'file': SimpleUploadedFile('immature.csv', immature.to_csv(index=False).encode()),
    })
    assert denied.status_code == 409 and denied.json()['error_code'] == 'native_assessment_time_or_maturity_invalid'
    assert not NativeProtectedInput.objects.exists() and not HoldoutAccess.objects.exists()
    sealed, raw, _ = seal(w, p, frame)
    identifier = queued(w, sealed)
    service.execute(identifier)
    manifest, digest, request = export(w, identifier)
    data = json.loads(manifest.read_bytes())
    outcomes = w.root / "protected.csv"
    outcomes.write_bytes(raw)
    report = offline_reproduce.reproduce(manifest, digest, w.path, outcomes)
    assert report["task"] == "regression" and report["n_assessed"] == 60
    assert report["scores_sha256"] == data["assessment"]["result"]["scores_sha256"]
    assert report["model_sha256"] == data["training"]["fit"]["model_sha256"]
    paired = data["training"]["fit"]["paired_diagnostics"]
    assert paired == w.trained.result["paired_diagnostics"]
    assert paired["validation_strategy"] == "oot" and paired["direction"] == "minimize"
    assert paired["status"] == "completed"
    frozen = data['training']['specification']['training']['prediction_contract']
    assert frozen == data['assessment']['result']['prediction_contract']
    assert frozen['forbidden_features'] == ['entity']
    assert data['assessment']['result']['population_checks']['fixed_outcome_window_checked'] is True
    assert data['assessment']['result']['population_checks']['prediction_contract_sha256'] == frozen['sha256']

    for role in ("anonymous", "outsider", "developer", "admin"):
        denied = w.clients[role].get(request)
        assert denied.status_code == 403 and denied["Cache-Control"] == "no-store"
    assert w.clients["reviewer"].get(request.rsplit("=", 1)[0] + "=" + "0" * 64).status_code == 409
    with pytest.raises(offline_reproduce.ReplayBlocked, match="development CSV"):
        offline_reproduce.reproduce(manifest, digest, outcomes, w.root / "absent.csv")

    altered_metrics = copy.deepcopy(data)
    altered_metrics["assessment"]["result"]["n_assessed"] = float(report["n_assessed"])
    altered_metrics["assessment"]["result_sha256"] = offline_reproduce.digest(altered_metrics["assessment"]["result"])
    altered = native_candidate.canonical(altered_metrics)
    manifest.write_bytes(altered)
    with pytest.raises(offline_reproduce.ReplayMismatch, match="Reproduced final scores"):
        offline_reproduce.reproduce(manifest, native_candidate.sha(altered), w.path, outcomes)

    manifest.write_bytes(native_candidate.canonical(data))
    outcomes.write_bytes(raw + b"\n")
    with pytest.raises(offline_reproduce.ReplayBlocked, match="protected outcomes CSV"):
        offline_reproduce.reproduce(manifest, digest, w.path, outcomes)

    # A failed development comparison must finish before attempting to open outcomes.
    data["training"]["fit"]["paired_diagnostics"]["reference_max_depth"] = True
    changed = native_candidate.canonical(data)
    manifest.write_bytes(changed)
    with pytest.raises(offline_reproduce.ReplayMismatch, match="refitted model"):
        offline_reproduce.reproduce(manifest, native_candidate.sha(changed), w.path, w.root / "absent.csv")
    changed_runtime = data["training"]["specification"]["runtime"]
    changed_runtime["reproduction_platform"]["machine"] = "other-architecture"
    with pytest.raises(offline_reproduce.ReplayBlocked, match="runtime differs"):
        offline_reproduce._verify_runtime(changed_runtime)

    edit = {
        "request_id": str(uuid.uuid4()), "expected_revision": p["revision"],
        "proposal_sha256": p["proposal_sha256"], "action": "revoke",
        "rationale": "The exact approval has been revoked for this validation fixture.",
    }
    assert post(w.clients["reviewer"], f"/api/native-adoptions/{p['id']}/", edit).status_code == 200
    assert w.clients["reviewer"].get(request).status_code == 409
    assert HoldoutAccess.objects.count() == 1
