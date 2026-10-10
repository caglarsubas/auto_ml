#!/usr/bin/env python3
"""Qualify synthetic authenticated-browser exports in an isolated clean runtime."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-image', required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    args.reports.mkdir(parents=True, exist_ok=True)
    contexts = sorted(args.inputs.rglob('offline-context.json'))
    if len(contexts) != 2:
        raise ValueError('Exactly one synthetic classification and regression export are required.')
    tasks, evidence = set(), []
    for context_path in contexts:
        context = json.loads(context_path.read_text())
        task = context['task']
        if context.get('synthetic_fixture') is not True or task not in {'classification', 'regression'} or task in tasks:
            raise ValueError('Only distinct explicit synthetic browser fixtures may authorize native-state trust here.')
        tasks.add(task)
        with tempfile.TemporaryDirectory(prefix='declarai-offline-qualification-') as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            approved = root / 'approved'
            approved.mkdir(mode=0o755)
            output = root / 'output'
            output.mkdir(mode=0o777)
            output.chmod(0o777)
            for name in ('offline-package.zip', 'offline-input.csv', 'offline-receipt.json'):
                shutil.copyfile(context_path.parent / name, approved / name)
                (approved / name).chmod(0o644)
            command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
                       '--user', '65534:65534', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                       '--memory', '1g', '--pids-limit', '128', '--cpus', '2',
                       '--tmpfs', '/tmp:rw,nosuid,nodev,size=512m',
                       '--tmpfs', '/app/backend/media:ro,nosuid,nodev,size=4m',
                       '-e', 'PYTHONPATH=/app/backend', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                       '-e', 'PROMETA_DISABLE=1', '-e', 'OMP_NUM_THREADS=2',
                       '-e', 'OPENBLAS_NUM_THREADS=2', '-e', 'MKL_NUM_THREADS=2',
                       '-v', f'{approved}:/approved:ro', '-v', f'{output}:/evidence:rw',
                       '-w', '/tmp', '--entrypoint', 'python', args.runtime_image,
                       '-m', 'deployment.offline_verify', '--package', '/approved/offline-package.zip',
                       '--csv', '/approved/offline-input.csv', '--receipt', '/approved/offline-receipt.json',
                       '--package-sha256', context['package_sha256'],
                       '--receipt-sha256', context['receipt_sha256'],
                       '--manifest-sha256', context['manifest_sha256'],
                       '--trust-native-state', '--atol', '1e-12', '--rtol', '1e-12',
                       '--chunk-sizes', '1', '17', '64', '--output', '/evidence/verification.json']
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            (args.reports / f'{task}.log').write_text(result.stdout + result.stderr)
            report = json.loads((output / 'verification.json').read_text()) if (output / 'verification.json').is_file() else {'status': 'blocked'}
            (args.reports / f'{task}.json').write_text(json.dumps(report, indent=2))
            evidence.append({'task': task, 'exit_code': result.returncode, 'status': report['status'],
                             'network': 'none', 'read_only_runtime': True, 'unprivileged': True,
                             'installation_media': 'empty read-only tmpfs', 'rows': report.get('rows')})
    summary = {'schema_version': 1, 'runtime_image': args.runtime_image, 'checks': evidence,
               'scope': 'synthetic_native_csv_batch_score_parity',
               'production_recovery_qualified': False, 'expert_isolation_qualified': False}
    (args.reports / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if all(c['exit_code'] == 0 and c['status'] == 'passed' for c in evidence) else 1


if __name__ == '__main__':
    raise SystemExit(main())
