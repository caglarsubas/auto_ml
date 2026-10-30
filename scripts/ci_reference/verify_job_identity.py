"""Host-only strict identity proof for the frozen approved CI workflow.

Run with the existing PyYAML-capable host interpreter. No network or credential
access: controller supplies fresh API rows and exact git-show workflow bytes.
"""
import hashlib
import re
import yaml

WORKFLOW_SHA256 = '475f23a91669b7a590c285e19f914ddd9f2be27234a1a36a694e707490c9cc7b'
KEY = 'postgresql-runtime'
DISPLAY = 'PostgreSQL runtime and metadata'
LABELS = {'self-hosted', 'Linux', 'X64', 'ubuntu-24.04', 'declarai-p162-mac-amd64'}


def identity_from_api(raw, jobs, *, head, run, job_id):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != WORKFLOW_SHA256:
        raise ValueError('workflow_source_unapproved')
    if type(head) is not str or not re.fullmatch('[0-9a-f]{40}', head) or type(run) is not int or run <= 0 or type(job_id) is not int or job_id <= 0:
        raise ValueError('identity_scope_invalid')
    definitions = yaml.safe_load(raw)['jobs']
    if len(definitions) != 6 or KEY not in definitions or any('strategy' in value or 'uses' in value for value in definitions.values()):
        raise ValueError('workflow_jobs_unsupported')
    names = [value.get('name') for value in definitions.values()]
    if any(type(name) is not str or not name or '${{' in name for name in names) or len(set(names)) != 6 or definitions[KEY]['name'] != DISPLAY:
        raise ValueError('workflow_identity_ambiguous')
    if type(jobs) is not list or len(jobs) != 6 or len({j.get('id') for j in jobs}) != 6 or sorted(j.get('name','') for j in jobs) != sorted(names):
        raise ValueError('API_job_inventory_mismatch')
    if any(j.get('head_sha') != head or j.get('run_id') != run or type(j.get('run_id')) is not int or type(j.get('id')) is not int for j in jobs):
        raise ValueError('API_job_scope_mismatch')
    target = [j for j in jobs if j['id'] == job_id]
    if len(target) != 1 or target[0]['name'] != DISPLAY or target[0]['status'] != 'queued':
        raise ValueError('API_target_job_mismatch')
    if set(target[0].get('labels',[])) != LABELS or len(target[0]['labels']) != len(LABELS):
        raise ValueError('API_target_labels_mismatch')
    if any(j.get('labels') != ['ubuntu-24.04'] for j in jobs if j['id'] != job_id):
        raise ValueError('API_other_job_labels_mismatch')
    return dict(schema='declarai_verified_workflow_job_identity_v1',workflow_sha256=WORKFLOW_SHA256,
                job_key=KEY,display_name=DISPLAY,declared_jobs=6,API_job_id=job_id,
                source_head=head,run_id=str(run),unique_display_verified=True)
