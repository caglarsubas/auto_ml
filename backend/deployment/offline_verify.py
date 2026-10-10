"""Offline native CSV scoring parity. Never execute code supplied by a package.

Run in a clean, fixed DeclarAI runtime with read-only approved inputs, no
network, no installation database/media and externally bounded resources.
Native pickle/joblib state still requires explicit trust. This is not D08.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from deployment.deploy_utils import score_bundle_directory
from deployment.evidence import verify_bundle
from deployment.scoring_receipts import byte_digest, csv_input, require_digest, scoring_runtime

NATIVE_ALGORITHMS = {'xgboost', 'lightgbm', 'catboost', 'logistic_regression',
                     'scorecard', 'isolation_forest'}
# Deliberately bounded first verification profile, not a product capacity promise.
MAX_BYTES = 1024 ** 3
MAX_MEMBERS = 256
SEMANTICS = ('file_id', 'bundle_id', 'execution_id', 'assessment_id', 'manifest_sha256',
             'class_mapping', 'score_semantics', 'input_stage', 'scores_calibrated',
             'feature_count', 'algorithm', 'lineage_id', 'evidence_status', 'production_use_approved')


class VerificationBlocked(ValueError):
    """Actionable checks defined here, safe to include in local evidence."""


def unpack(archive_path, destination):
    """Only flat regular members; bounded expansion, no links or extraction APIs."""
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > MAX_MEMBERS or len(names) != len(set(names)):
            raise VerificationBlocked('Package contains duplicate members or exceeds the member limit.')
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise VerificationBlocked('Package exceeds the expanded byte limit.')
        for entry in entries:
            mode = entry.external_attr >> 16
            if (not entry.filename or entry.filename in {'.', '..'} or '/' in entry.filename
                    or '\\' in entry.filename or entry.is_dir()
                    or (mode & 0o170000) not in {0, 0o100000} or entry.flag_bits & 1):
                raise VerificationBlocked('Package members must be flat, unencrypted regular files.')
            with archive.open(entry) as source, (destination / entry.filename).open('xb') as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    return set(names)


def snapshot(source, target, expected):
    require_digest(expected)
    source = Path(source)
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise VerificationBlocked('Verification input is missing or exceeds the byte limit.')
    shutil.copyfile(source, target)
    from modeling.execution_artifacts import digest_file
    if digest_file(target) != expected:
        raise VerificationBlocked('Verification input differs from its independently supplied digest.')


def verify_package(package, csv, receipt, *, package_sha256, receipt_sha256,
                   manifest_sha256, atol, rtol, chunk_sizes=(1, 64), trust_native_state=False):
    """Return evidence of score parity only; never refit, assess or approve."""
    require_digest(manifest_sha256)
    if not trust_native_state:
        raise VerificationBlocked('Explicit trust in native serialized state is required before scoring.')
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in (atol, rtol)):
        raise VerificationBlocked('Absolute and relative tolerances must be explicit finite nonnegative numbers.')
    if (len(set(chunk_sizes)) < 2 or len(chunk_sizes) > 8
            or any(type(size) is not int or size < 1 for size in chunk_sizes)):
        raise VerificationBlocked('Select two to eight distinct positive chunk sizes.')
    with tempfile.TemporaryDirectory(prefix='declarai-offline-') as temporary:
        root = Path(temporary)
        snapshot(package, root / 'package.zip', package_sha256)
        snapshot(receipt, root / 'receipt.json', receipt_sha256)
        recorded = json.loads((root / 'receipt.json').read_text())
        if not isinstance(recorded, dict) or recorded.get('receipt_schema_version') != 1:
            raise VerificationBlocked('An input-bound version-one scoring receipt is required.')
        input_spec = recorded.get('input') or {}
        if not isinstance(input_spec, dict) or input_spec.get('format') != 'csv':
            raise VerificationBlocked('Offline verification currently supports exact CSV inputs only.')
        snapshot(csv, root / 'input.csv', input_spec.get('sha256'))
        if input_spec != csv_input((root / 'input.csv').read_bytes()):
            raise VerificationBlocked('CSV bytes or parser version differ from the scoring receipt.')
        runtime = scoring_runtime()
        if runtime != recorded.get('scoring_runtime'):
            raise VerificationBlocked('Installed scoring runtime differs from the recorded runtime; parity is unqualified.')
        out = root / 'bundle'
        out.mkdir()
        names = unpack(root / 'package.zip', out)
        manifest, digest = verify_bundle(out, recorded.get('file_id'), recorded.get('bundle_id'))
        if digest != manifest_sha256 or digest != recorded.get('manifest_sha256'):
            raise VerificationBlocked('Package manifest differs from the pinned manifest or scoring receipt.')
        if (manifest.get('handoff_schema_version') != 1 or not manifest.get('execution_id')
                or not manifest.get('assessment_id') or manifest.get('algorithm') not in NATIVE_ALGORITHMS):
            raise VerificationBlocked('Only versioned registered native packages with assessment evidence are supported.')
        for key in ('bundle_id', 'execution_id', 'assessment_id'):
            if str(uuid.UUID(str(manifest[key]))) != manifest[key] or recorded.get(key) != manifest[key]:
                raise VerificationBlocked('Package and receipt version identities must agree.')
        if names != set(manifest['artifact_integrity']) | {'manifest.json', 'publication.json', 'README.txt'}:
            raise VerificationBlocked('Package contains unrecorded members or is incomplete.')
        execution = json.loads((out / 'execution_manifest.json').read_text())
        if (execution.get('python_version') != runtime['python_version']
                or execution.get('packages') != runtime['packages']):
            raise VerificationBlocked('Installed dependencies differ from the recorded model environment.')
        frame = pd.read_csv(root / 'input.csv')
        if frame.empty or recorded.get('n_scored') != len(frame):
            raise VerificationBlocked('Receipt row count must agree with a nonempty CSV.')
        reference = np.asarray(recorded.get('scores'), dtype=float)
        if (reference.ndim not in {1, 2} or len(reference) != len(frame)
                or not np.isfinite(reference).all()):
            raise VerificationBlocked('Receipt must contain finite full scores with row alignment.')
        checks = []
        for size in (len(frame), *chunk_sizes):
            batches = []
            for start in range(0, len(frame), size):
                result = score_bundle_directory(out, recorded['file_id'], frame.iloc[start:start + size].copy(), recorded['bundle_id'])
                if any(result.get(key) != recorded.get(key) for key in SEMANTICS):
                    raise VerificationBlocked('Score semantics differ from the recorded receipt.')
                batches.append(np.asarray(result['scores'], dtype=float))
            scores = np.concatenate(batches, axis=0)
            if scores.shape != reference.shape or not np.isfinite(scores).all():
                raise VerificationBlocked('Replayed scores do not preserve score shape or finite row alignment.')
            delta = float(np.max(np.abs(scores - reference)))
            passed = bool(np.allclose(scores, reference, atol=atol, rtol=rtol))
            checks.append({'chunk_size': size, 'batches': len(batches), 'passed': passed,
                           'max_absolute_difference': delta})
        return {'schema_version': 1, 'status': 'passed' if all(c['passed'] for c in checks) else 'failed',
                'scope': 'native_csv_batch_score_parity', 'package_sha256': package_sha256,
                'receipt_sha256': receipt_sha256, 'input_sha256': input_spec['sha256'],
                'manifest_sha256': digest, 'bundle_id': recorded['bundle_id'],
                'execution_id': recorded['execution_id'], 'assessment_id': recorded['assessment_id'],
                'batch_id': recorded['batch_id'], 'rows': len(frame), 'score_shape': list(reference.shape),
                'atol': atol, 'rtol': rtol, 'runtime': runtime, 'checks': checks,
                'model_refit_reproduced': False, 'assessment_reproduced': False,
                'review_approved': False, 'production_use_approved': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'csv', 'receipt', 'package-sha256', 'receipt-sha256', 'manifest-sha256', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--atol', type=float, required=True)
    parser.add_argument('--rtol', type=float, required=True)
    parser.add_argument('--chunk-sizes', nargs='+', type=int, default=[1, 64])
    parser.add_argument('--trust-native-state', action='store_true', help='Acknowledge trusted pickle/joblib state; this is not isolation.')
    args = vars(parser.parse_args())
    output = Path(args.pop('output'))
    try:
        report = verify_package(**args)
    except Exception as error:
        report = {'schema_version': 1, 'status': 'blocked', 'scope': 'native_csv_batch_score_parity',
                  'error': str(error) if isinstance(error, VerificationBlocked) else
                  'Input, package, runtime or scoring verification failed. No parity claim is available.',
                  'review_approved': False, 'production_use_approved': False}
    # Refuse to overwrite earlier evidence, including blocked attempts.
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, allow_nan=False, indent=2)
    print(json.dumps({'status': report['status'], 'scope': report['scope']}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
