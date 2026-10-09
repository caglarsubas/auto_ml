# Project authorization foundation (P18)

P18 implements part of D06. Project membership governs native REST, pipeline records,
managed table overrides, registered artifact downloads, local MCP reads/proposals
and browser typed-action approvals. This is a foundation packet; private deployment,
independent review, retention/egress policy and all release/customer gates remain open.

## Activation and migration

Private mode requires project authority. A successful `manage_project` operation
also records durable installation activation in `ProjectPolicy`. Changing back to
the development profile cannot remove that recorded governance. The additive
migration creates empty tables; it neither guesses legacy ownership nor activates
an unconfigured development database. Development installations without activation
retain the previously authenticated, organization-wide behavior and are unqualified
for project isolation. Disposable browser CI explicitly activates projects.

An installation operator first creates a project for an existing active account.
The initial role is administrator. Existing identity enrollment is required; this
packet does not add SSO, MFA, self-service enrollment or a role-management screen.
The commands run in the configured customer installation, after migrations:

```sh
python backend/manage.py manage_project create --name "Credit development" \
  --user project-admin --request-id <UUID> --operator-label installation-operator
python backend/manage.py manage_project member --project-id <PROJECT_UUID> \
  --user model-developer --role developer --request-id <UUID> --operator-label installation-operator
python backend/manage.py manage_project member --project-id <PROJECT_UUID> \
  --user independent-reviewer --role reviewer --request-id <UUID> --operator-label installation-operator
python backend/manage.py manage_project dataset --project-id <PROJECT_UUID> \
  --file-id <LEGACY_DATASET_ID> --request-id <UUID> --operator-label installation-operator
python backend/manage.py manage_project pipeline --project-id <PROJECT_UUID> \
  --pipeline-id <LEGACY_PIPELINE_ID> --request-id <UUID> --operator-label installation-operator
```

Each change needs a fresh UUID; an exact retry returns the original receipt without
reapplying the change. A changed request cannot reuse its UUID. Operator labels are
assertions from a trusted installation command, **not authenticated human identity**.
Adoption records a current assignment, never historical ownership or missing
scientific evidence. Dataset/pipeline reassignment to another project is unsupported.
Pipeline dataset references must agree with its project, including state identifiers.
Missing declared source files cannot fall back to a globally matched filename.

## Roles and interfaces

| Project role | Read existing project data/evidence and export | Develop, score, change pipeline/settings, prepare/approve typed actions | Change other users' project membership |
| --- | --- | --- | --- |
| Developer | Yes | Yes | No |
| Reviewer | Yes | No | No |
| Administrator | Yes | No | Yes |

A membership has one role; administration does not imply modeling authority.
Django staff/superuser flags grant no project access. In governed mode, unscoped
Django administration pages are unavailable; authentication/password endpoints
retain their existing identity controls. Customer identity administration remains
an installation responsibility pending the broader identity workflow.

`GET /api/projects/` returns only the actor's active memberships, role and revision.
`POST /api/projects/<UUID>/members/` accepts an existing `username`, `role`
(`developer`, `reviewer`, `admin`, `none`) and `request_id`. It requires that
project's administrator, records the authenticated actor, serializes membership
changes and supports exact retries. Administrators cannot change their own role
through this API; operator recovery uses the command above.

New uploads and pipelines carry a project binding, including pipelines created
before upload and iteration clones. A caller with exactly one developer membership
can omit `project_id`; multiple choices require it. Existing UI qualifies the
single-project developer flow. A project picker, reviewer workspace, approval of
model use and comprehensive accessibility remain future product work.

## Enforcement and evidence

Native endpoints use an explicit policy registry. New endpoints without a policy
fail closed in governed mode, and a route-inventory regression catches omissions.
Missing/invalid selectors stop before a handler; unassigned or inaccessible objects
return generic denial. Lists filter by membership. Pipeline selectors and root
state dataset references receive the same checks as direct dataset IDs. The static
purifier catalog and assistant model catalog carry no project data.

`processed_file` and `file_override` must resolve to the selected dataset's source
or explicitly registered native artifact. Being under `MEDIA_ROOT` is insufficient.
`model_path` requests are unavailable in governed mode; select an immutable
`execution_id`. Native upload, preprocessing/encoding, execution/assessment and
export writers register their artifact owners. Unregistered legacy media is blocked;
it is not adopted by inferring a file ID from its name. Native serialization/code
files remain unavailable through media downloads.

Access receipts reserve authority before the protected handler, then recheck
membership/binding revisions before output. Synchronous streams recheck before
advancing and releasing each chunk. Revocation withholds later output; it cannot
recall bytes already delivered. Authorized deletion checks continued membership
while recognizing the actual deleted resource. Failed/unavailable authority blocks
output; interrupted receipts may remain `started` and never imply completion.
This is not cancellation or recovery of an already authorized background job.

MCP requires both its existing active installation actor/process scope/dataset grant
and current project membership. Reviewer reads remain allowed; a MCP `prepare`
grant cannot elevate a reviewer to developer. Both authorities are rechecked before
returning results. Network MCP and direct/expert execution remain independently blocked.
Typed proposals pin project, dataset binding, role and membership revision along with
the existing session/input/environment evidence. Role changes cancel unused prepared/
approved actions; revoke/regrant cannot reuse an earlier approval. Consumed receipts
remain evidence and do not authorize another dispatch.

Cross-project final-outcome history preserves exact/overlap/unknown reuse counts and
exploratory status while withholding the other project's identifiers, actors, times
and parameters. Frozen legacy JSON/ZIP exports containing those references are
withheld with `cross_project_evidence_requires_new_assessment`; originals are not
rewritten. Create a new assessment to produce a correctly scoped historical snapshot.

`ProjectAuthorityEvent` records browser actors separately from installation assertions,
current assignments, role changes, native/media access and failures. Membership and
binding revisions are authority generations, not signatures. Database/artifact
administrators remain trusted; tamper-proof audit, retention/deletion, provider and
telemetry egress, ingress isolation, complete resource limits, expert isolation and
production restore/upgrade qualification remain open.

## Qualification

See [P18 evidence](evidence/p18-qualification-2026-10-10.json). Coverage includes real
HTTP/session/CSRF boundaries, roles and staff flags, path and pipeline selection,
legacy adoption, exact retries, mid-request/regrant revocation, typed approvals,
stream withholding, native artifact ownership and cross-project holdout evidence.
The existing full marked suites run on SQLite and PostgreSQL with unchanged 50%
coverage and 15-skip budgets. The private TLS fixture additionally checks five
independent processes committing one role change and four exact retries, native/MCP
revocation, unaffected reviewer access, and retained project bindings across restart
and a quiescent synthetic database/artifact restore. This is not a production
recovery qualification.

Governed browser CI retains its existing scientific/approval/keyboard assertions
using explicitly owned untrained datasets where appropriate, and adds a real-browser
check that project denials preserve sign-in. Actual stdio qualification retains the
original MCP scope/grant/actor checks and adds project revocation and reviewer role
checks. Local browser role/revocation evidence supplements these automated cases.
