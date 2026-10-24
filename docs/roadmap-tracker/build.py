#!/usr/bin/env python3
"""Build an offline, read-only roadmap view from DeclarAI's canonical ledger."""
import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = Path(__file__).resolve().parents[2]
READ_ATTEMPTS = []


def command(repo, *args):
    result = subprocess.run(args, cwd=repo, text=True, capture_output=True, timeout=35)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:500] or f'{args[0]} failed')
    return result.stdout.strip()


def remote_json(repo, endpoint):
    # Retry reads only. Retain failed attempts; never rerun a workflow or mutation.
    for attempt in range(1, 4):
        try:
            value = json.loads(command(repo, 'gh', 'api', endpoint))
            READ_ATTEMPTS.append({'endpoint': endpoint, 'attempt': attempt, 'result': 'success'})
            return value
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            READ_ATTEMPTS.append({'endpoint': endpoint, 'attempt': attempt, 'result': 'unavailable', 'error': str(error)[:500]})
            if attempt == 3:
                raise


def run_record(repo, number, expected):
    raw = remote_json(repo, f'repos/caglarsubas/auto_ml/actions/runs/{number}')
    jobs = remote_json(repo, f'repos/caglarsubas/auto_ml/actions/runs/{number}/attempts/{raw["run_attempt"]}/jobs?per_page=100')['jobs']
    checks = [{'name': x['name'], 'conclusion': x['conclusion']} for x in jobs]
    verified = (raw['head_sha'] == expected and raw['status'] == 'completed'
                and raw['conclusion'] == 'success' and len(checks) == 6
                and all(x['conclusion'] == 'success' for x in checks))
    return {k: raw[k] for k in ['id', 'head_sha', 'event', 'run_attempt', 'status', 'conclusion', 'html_url', 'updated_at']} | {'jobs': checks, 'verified': verified}


def build(repo):
    ledger_path = repo / 'docs/product-roadmap.json'
    raw = ledger_path.read_bytes()
    ledger = json.loads(raw)
    spec = importlib.util.spec_from_file_location('roadmap_validator', repo / 'scripts/render_product_roadmap.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate(ledger)
    assert validator.render(ledger) == (repo / 'docs/PRODUCT_DEVELOPMENT_ROADMAP.md').read_text(), 'Canonical Markdown projection is stale.'
    source_head = command(repo, 'git', 'rev-parse', 'HEAD')
    source_dirty = command(repo, 'git', 'status', '--porcelain', '--', 'docs/product-roadmap.json', 'docs/PRODUCT_DEVELOPMENT_ROADMAP.md')
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    verification = {'checked_at': now, 'errors': [], 'read_only': True, 'read_attempts': READ_ATTEMPTS}
    try:
        main = remote_json(repo, 'repos/caglarsubas/auto_ml/commits/main')
        verification['main'] = {'sha': main['sha'], 'url': main['html_url'], 'source_base_matches': main['sha'] == source_head,
                                'matches_source': main['sha'] == source_head and not source_dirty}
    except Exception as error:
        verification['errors'].append(f'Main refresh unavailable: {error}')
    latest_packet = ledger['implementation_packets'][-1]['id']
    latest = next((p['id'] for p in reversed(ledger['implementation_packets'])
                   if (repo / f'test-reports/{p["id"].lower()}/final-audit.json').exists()), latest_packet)
    audit_path = repo / f'test-reports/{latest.lower()}/final-audit.json'
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text())
            pr = remote_json(repo, f'repos/caglarsubas/auto_ml/pulls/{audit["pr"]}')
            record = {'packet': latest, 'pr': pr['number'], 'url': pr['html_url'], 'merged': pr['merged'],
                      'head': pr['head']['sha'], 'merge': pr['merge_commit_sha'], 'merged_at': pr['merged_at'],
                      'receipt': str(audit_path), 'receipt_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest()}
            record['pr_ci'] = run_record(repo, audit['ci_run'], audit['qualified_head'])
            record['main_ci'] = run_record(repo, audit['main_run'], audit['merge'])
            record['receipt_qualified'] = all(audit.get(key) is True for key in (
                'main_qualified', 'merged_tree_matches_qualified_pr',
                'original_case_skip_workload_limits_preserved', 'source_hashes_match'))
            record['verified'] = (record['merged'] and record['head'] == audit['qualified_head']
                                  and record['merge'] == audit['merge']
                                  and record['receipt_qualified']
                                  and record['pr_ci']['verified'] and record['main_ci']['verified'])
            verification['latest_delivery'] = record
        except Exception as error:
            verification['errors'].append(f'Latest-delivery refresh unavailable: {error}')
    else:
        verification['errors'].append(f'No retained final audit for {latest}; delivery CI/merge status is not independently refreshed.')
    next_id = latest_packet if latest_packet != latest else f'P{int(latest[1:]) + 1:02d}'
    checkpoint_path = repo / f'test-reports/{next_id.lower()}/checkpoint.json'
    starter = None
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        branch = command(repo, 'git', 'branch', '--show-current')
        if (source_head in {checkpoint.get('source_base'), checkpoint.get('pr_head'), checkpoint.get('merge')} or checkpoint.get('branch') == branch) and checkpoint.get('packet') == next_id:
            scope_path = checkpoint_path.parent / 'next-task-scope.md'
            starter = {'id': next_id, 'title': scope_path.read_text().splitlines()[0].lstrip('# ') if scope_path.exists() else next_id,
                       'checkpoint': checkpoint, 'scope': scope_path.read_text() if scope_path.exists() else '',
                       'source': str(checkpoint_path), 'sha256': hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()}
    operator_checkpoint = None
    handoff_path = repo / f'test-reports/{latest.lower()}/checkpoint.json'
    if handoff_path.exists() and verification.get('latest_delivery', {}).get('verified'):
        handoff = json.loads(handoff_path.read_text())
        if handoff.get('operator_review_required') is True and handoff.get('main_qualified') is True and handoff.get('merge') == source_head:
            operator_checkpoint = {'packet': latest, 'next': handoff['next'],
                                   'source': str(handoff_path), 'sha256': hashlib.sha256(handoff_path.read_bytes()).hexdigest()}
    notes = json.loads((HERE / 'notes.json').read_text())
    ledger_digest = hashlib.sha256(raw).hexdigest()
    note_current = notes['reviewed_against'] == source_head and (
        notes.get('reviewed_ledger_sha256') == ledger_digest if notes.get('reviewed_ledger_sha256') else not source_dirty)
    # Stale editorial notes remain in the companion file but never override a newer source snapshot.
    editorial = notes['items'] if note_current else {}
    assert not editorial or set(editorial) == {x['id'] for x in ledger['items']}
    refs = []
    for entry in ledger['items'] + ledger['implementation_packets']:
        for evidence in entry.get('evidence', []):
            for target in re.findall(r'\]\(([^)]+)\)', evidence):
                if not re.match(r'^[a-z]+:', target):
                    path = (repo / 'docs' / target.split('#')[0]).resolve()
                    if not path.is_file():
                        refs.append(f'{entry["id"]}: {target}')
    assert not refs, f'Missing evidence targets: {refs}'
    data = {'ledger': ledger, 'editorial': editorial, 'starter': starter, 'operator_checkpoint': operator_checkpoint, 'verification': verification,
            'meta': {'generated_at': now, 'repository': str(repo), 'source_commit': source_head,
                     'ledger_sha256': ledger_digest, 'ledger_path': str(ledger_path),
                     'local_only_paths': command(repo, 'git', 'ls-files', '--others', '--exclude-standard', '--', 'docs').splitlines(),
                     'ledger_dirty': bool(source_dirty), 'editorial_current': note_current,
                     'editorial_reviewed_against': notes['reviewed_against'], 'snapshot_is_live': False}}
    font_dir = repo / 'frontend/src/assets/fonts'
    # Retain the product's packaged fonts and their OFL notices; no network assets.
    # Derive Latin serif/mono filenames from the product CSS rather than assuming the hash names.
    font_css = (font_dir / 'fonts.css').read_text()
    fonts = []
    for family, weight in [('Instrument Sans', '400 700'), ('Instrument Serif', '400'), ('IBM Plex Mono', '400')]:
        blocks = re.findall(r'@font-face\s*\{([^}]+)\}', font_css)
        block = next(b for b in blocks if f"font-family: '{family}'" in b and 'font-style: normal' in b and 'font-weight: 400;' in b and 'U+0000-00FF' in b)
        filename = re.search(r'src: url\(([^)]+)\)', block).group(1)
        payload = base64.b64encode((font_dir / filename).read_bytes()).decode()
        fonts.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:swap;src:url(data:font/woff2;base64,{payload}) format('woff2')}}")
    metrics_spec = importlib.util.spec_from_file_location('roadmap_status_metrics', repo / 'docs/roadmap-tracker/metrics.py')
    metrics = importlib.util.module_from_spec(metrics_spec)
    metrics_spec.loader.exec_module(metrics)
    data['status_metrics'] = metrics.status_metrics(ledger)
    data['font_licenses'] = [{'name': p.name, 'text': p.read_text()} for p in sorted(font_dir.glob('*OFL.txt'))]
    template = (HERE / 'template.html').read_text()
    json_text = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    output = template.replace('/*__FONTS__*/', '\n'.join(fonts)).replace('/*__SNAPSHOT__*/', json_text)
    (HERE / 'index.html').write_text(output)
    (HERE / 'snapshot.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'product-roadmap.source.json').write_bytes(raw)
    licenses = HERE / 'font-licenses'
    licenses.mkdir(exist_ok=True)
    for notice in font_dir.glob('*OFL.txt'):
        shutil.copyfile(notice, licenses / notice.name)
    report = {'generated_at': now, 'items': len(ledger['items']), 'packets': len(ledger['implementation_packets']),
              'states': {s: sum(x['status'] == s for x in ledger['items']) for s in validator.STATES},
              'source_commit': source_head, 'ledger_sha256': data['meta']['ledger_sha256'],
              'source_projection_valid': True, 'evidence_targets_valid': True, 'verification': verification,
              'editorial_current': note_current, 'html_sha256': hashlib.sha256(output.encode()).hexdigest()}
    (HERE / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'verification'}, indent=2))
    print('Remote qualification:', verification.get('latest_delivery', {}).get('verified', False))
    print('Output:', HERE / 'index.html')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    args = parser.parse_args()
    build(args.repo.resolve())
