"""Governed export binds the exact result and exposes only development evidence."""

import hashlib
import json

import pytest

from execution_jobs import legacy_execution, selection_provenance, service
from execution_jobs.models import NativeJob
from modeling.verify_fold_provenance import verify
from tests.unit.test_durable_training_search import admission, queue, world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


def test_reviewer_export_uses_exact_training_evidence(world):
    w = world
    # Place two otherwise-eligible training rows across the first CV boundary.
    w.frame.loc[10, 'entity'] = w.frame.loc[40, 'entity']
    w.frame.loc[11, 'end'] = w.frame.loc[42, 'date']
    w.frame.to_csv(w.path, index=False)
    options = {**w.options, 'validation': {'strategy': 'oot', 'date_column': 'date',
               'label_end_column': 'end', 'group_column': 'entity', 'n_splits': 2}}
    body, _ = admission(w, options)
    identifier = queue(w, body)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == 'succeeded', job.reason_code
    url = f'/api/jobs/{identifier}/fold-provenance/?sha256={job.result_sha256}'
    result = w.clients['reviewer'].get(url)
    assert result.status_code == 200, result.content
    assert result['Cache-Control'] == 'no-store'
    assert result['X-DeclarAI-Export-SHA256'] == hashlib.sha256(result.content).hexdigest()
    offline = verify(result.content, result['X-DeclarAI-Export-SHA256'])
    assert offline['fit_count'] == 5 and offline['unverified_count'] == 0
    with pytest.raises(ValueError, match='retained export digest'):
        verify(result.content + b' ', result['X-DeclarAI-Export-SHA256'])
    assert w.clients['anonymous'].get(url).status_code == 403
    evidence = result.json()
    assert evidence['result_sha256'] == job.result_sha256
    assert evidence['evidence_scope'] == 'exploratory_development'
    assert evidence['production_use_approved'] is False
    assert len(evidence['fits']) == 5 and len(evidence['partitions']) == 3
    first = evidence['partitions'][evidence['fits'][0]['partition_sha256']]
    assert 9 in first['train_rows'] and not {10, 11}.intersection(first['train_rows'])
    assert 40 in first['validation_rows']
    for row in evidence['fits'][:-1]:
        partition = evidence['partitions'][row['partition_sha256']]
        tr, va = w.frame.loc[partition['train_rows']], w.frame.loc[partition['validation_rows']]
        assert tr.end.max() < va.date.min()
        assert set(tr.entity).isdisjoint(va.entity)
        state = evidence['transform_states'][row['transforms_sha256']]
        assert state['impute_means']['z'] == pytest.approx(tr.z.mean())
    assert b'model_json' not in result.content
    assert w.clients['outsider'].get(url).status_code == 403
    assert w.clients['reviewer'].get(url.rsplit('=', 1)[0] + '=' + '0' * 64).status_code == 409
    altered = job.result
    altered['refit_preprocessing']['train_rows'] = []
    NativeJob.objects.filter(pk=identifier).update(result=altered)
    assert w.clients['reviewer'].get(url).status_code == 409


def test_export_rejects_protected_rows_in_fitted_membership():
    from modeling.fit_receipts import receipt_digest
    from modeling.fold_evidence import FoldEvidence

    fit = {'train': {'n_rows': 2}, 'valid': {'n_rows': 1}, 'validation_role': 'evaluation_only'}
    fit['sha256'] = receipt_digest(fit)
    output = FoldEvidence([1, 2, 3, 4])
    with pytest.raises(ValueError, match='permitted partition'):
        output.record('fold/1', fit, train_rows=[1, 5], valid_rows=[3])
    with pytest.raises(ValueError, match='different partition'):
        output.record('fold/1', fit, {'purifier': {'fit_rows': [1, 5]}}, train_rows=[1, 2], valid_rows=[3])
    fit = {key: value for key, value in fit.items() if key != 'sha256'}
    fit.update(train_rows_sha256=receipt_digest([2, 1]), valid_rows_sha256=receipt_digest([3]))
    fit['sha256'] = receipt_digest(fit)
    with pytest.raises(ValueError, match='Ordered development row identities'):
        output.record('fold/1', fit, train_rows=[1, 2], valid_rows=[3])
    with pytest.raises(ValueError, match='outer development-training'):
        output.fold('search/fold/1', {'native_fit': fit, 'train_rows': [2, 1], 'valid_rows': [3]},
                    parent_rows={1, 2, 4})
    assert output.result()['fits'] == []


def test_legacy_evidence_pins_exact_source_and_never_reads_protected_artifacts(world, monkeypatch):
    from tests.unit.test_durable_legacy_execution import launch, options, post

    w = world
    prepared = post(w.clients['developer'], '/api/preprocessing/run/', {
        'file_id': w.file_id, 'options': [29], 'target_column': 'outcome',
        'split': {'strategy': 'oot', 'date_column': 'date', 'label_end_column': 'end',
                  'group_column': 'entity', 'cutoff': '2020-03-20'},
    })
    assert prepared.status_code == 200, prepared.content
    identifier, _, _ = launch(w, 'training', {**options(w), 'processed_file': prepared.json()['processed_file']})
    service.execute(identifier)
    source = NativeJob.objects.get(pk=identifier)
    assert source.state == 'succeeded', source.reason_code
    args = {'file_id': w.file_id, 'source_job_id': identifier, 'source_result_sha256': source.result_sha256,
            'execution_id': source.result['payload']['execution_id'], 'cv_folds': 2, 'n_jobs': 1}
    search_id, _, _ = launch(w, 'sfs', {**args, 'methods': ['forward'], 'top_k': 2,
                                      'stopping_criteria': {'max_features': 1}})
    service.execute(search_id)
    search = NativeJob.objects.get(pk=search_id)
    assert search.state == 'succeeded', search.reason_code
    hpo_id, _, _ = launch(w, 'hpo', {**args, 'param_space': {
        'max_depth': {'type': 'int', 'min': 1, 'max': 2, 'enabled': True}},
        'fixed_params': {'n_estimators': 8}, 'n_iter': 2, 'search_method': 'random',
        'validation_curve_points': 2})
    service.execute(hpo_id)
    hpo = NativeJob.objects.get(pk=hpo_id)
    assert hpo.state == 'succeeded', list(hpo.events.values('event_type', 'detail'))
    original = legacy_execution.read
    captured = []

    def read(path, limit=None):
        assert path.name in {'modeling_status.json', 'lineage.json', 'manifest.json',
                             'selection-fits.jsonl'}, path.name
        captured.append(path)
        return original(path, limit)

    monkeypatch.setattr(legacy_execution, 'read', read)
    outputs = {}
    for job in (source, search, hpo):
        res = w.clients['reviewer'].get(f'/api/jobs/{job.pk}/fold-provenance/?sha256={job.result_sha256}')
        assert res.status_code == 200, res.content
        evidence = outputs[job.pk] = res.json()
        audited = verify(res.content, res['X-DeclarAI-Export-SHA256'])
        assert audited['fit_count'] and not evidence['unverified'], evidence['unverified']
        assert b'final_holdout' not in res.content and b'train_data.pkl' not in res.content
        for fit in evidence['fits']:
            if '/cv/' not in fit['stage'] and '/other_top_k/' not in fit['stage']:
                continue
            partition = evidence['partitions'][fit['partition_sha256']]
            tr = w.frame.loc[partition['train_rows']]
            va = w.frame.loc[partition['validation_rows']]
            assert tr.end.max() < va.date.min()
            assert set(tr.entity).isdisjoint(va.entity)
            state = evidence['transform_states'][fit['transforms_sha256']]
            assert state['purifier']['fit_rows'] == partition['train_rows']
    evidence = outputs[search.pk]
    assert evidence['source_result_sha256'] == source.result_sha256
    stages = {row['stage'] for row in evidence['fits']}
    assert {'forward/1/screen/1', 'forward/1/other_top_k/1/1', 'candidate/forward/cv/1'} <= stages
    stages = {row['stage'] for row in outputs[hpo.pk]['fits']}
    assert {'trial/0/fit', 'trial/0/cv/1', 'curve/1/point/1/cv/1', 'candidate/winner/cv/1'} <= stages
    for kind in (search, hpo):
        assert outputs[kind.pk]['candidate_assessments'][0]['execution_id']

    for name in ('selection-fits.jsonl', 'lineage.json'):
        path = next(path for path in captured if path.name == name)
        path.chmod(0o600)
        original_bytes = path.read_bytes()
        path.write_bytes(b'{}')
        res = w.clients['reviewer'].get(f'/api/jobs/{search.pk}/fold-provenance/?sha256={search.result_sha256}')
        assert res.status_code == 409
        path.write_bytes(original_bytes)


def test_selection_sidecar_bounds_integrity_and_keeps_result_references_small(tmp_path, settings, monkeypatch):
    import types

    monkeypatch.setattr(selection_provenance.legacy_context, 'active', lambda: types.SimpleNamespace())
    monkeypatch.setattr(selection_provenance, 'MAX_BYTES', 200)
    settings.MEDIA_ROOT = tmp_path
    payload = {'screening': {'value': 'x' * 120}, 'other_top_k': {}}
    ref = selection_provenance.record(payload)
    assert len(json.dumps(ref)) < len(json.dumps(payload))
    assert selection_provenance.record(payload) == {'status': 'evidence_budget_exceeded'}
    raw = (tmp_path / selection_provenance.NAME).read_bytes()
    assert selection_provenance.read(raw, ref) == payload
    with pytest.raises(ValueError, match='digest'):
        selection_provenance.read(raw, {**ref, 'sha256': '0' * 64})
    with pytest.raises(ValueError, match='extent'):
        selection_provenance.read(raw, {**ref, 'offset': len(raw)})
