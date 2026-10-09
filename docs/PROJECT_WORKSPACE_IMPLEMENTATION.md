# Project workspace and development context (P19)

P19 extends D06 and D12 with a browser entry point for the project authority introduced
in P18. It does not complete independent review, identity enrollment, or any release gate.

## User workflow

After sign-in, Home loads current server memberships. A single membership is selected;
multiple memberships require a choice. The labeled picker shows the project name and
role. Datasets and pipeline records belong to that selected project. A reviewer or
administrator can browse records and download the existing pipeline HTML report. Only
a developer can open the model development workspace. Administration continues to be
separate from modeling authority.

The development screen shows its project and role. Uploads and initial checkpoints
include an explicit `project_id`, so users with multiple developer memberships can
create work. Saved-pipeline listing, detail, changes, deletion, and report downloads
carry the current project selector. The source upload and scientific pipeline contracts
remain unchanged. A project selection cannot move an existing resource.

Use **Change project at home** to leave development through the existing unsaved-change
handling. Opening the chosen development workspace starts a fresh page and in-memory
services, including the prior dataset and assistant context. A query change cannot
relabel a mounted workspace as another project; it returns to Home. The picker uses
Angular form binding so refreshed/deep-linked choices remain visible after its options
are rebuilt. A manual choice becomes the refresh preference.

Unavailable projects, missing memberships, and authority/directory outages have explicit
blocked states. Refresh discards displayed records before rechecking membership. Record
requests are canceled on a selection change, old directory responses are generation
checked, sign-out discards the directory, and a late report response from a previous
project is withheld. Selection is in memory, not persisted as an authorization token.
The server continues to verify current membership and resource binding on each request.

Ungoverned development retains its authenticated organization-wide compatibility path.
Home identifies it as requiring operator-enabled project governance before private
customer data is used. No existing installation is activated by loading this UI.

## API compatibility and authority

`GET /api/declaration/?project_id=<UUID>` and `GET /api/pipeline/?project_id=<UUID>`
filter to one currently readable project. Dataset serialization and pipeline list rows
include read-only `project_id` metadata (`null` for an unassigned legacy record). Omitted
selectors retain the existing list of all authorized records. In governed mode,
unavailable, malformed, empty, repeated, and mismatched selectors fail; none falls back
to all records. A selector is checked in addition to the resource's existing binding,
including a pipeline created before upload. Authority is rechecked before response
release using the existing P18 boundary. Ungoverned legacy compatibility is unchanged.

## Qualification and limits

[P19 evidence](evidence/p19-qualification-2026-10-10.json) records full marked SQLite and
PostgreSQL suites with the existing coverage/skip budgets, project selector regressions,
frontend units/build/lint, private TLS/process/restart/restore checks, actual MCP stdio,
and the existing governed browser/API suite. The browser fixture adds a separate actor
with two developer memberships, a reviewer membership, and an administrator membership;
it preserves the original single-project scientific fixture. The disposable seed
command still requires `DECLARAI_TEST_INSTALLATION=1` and caller-supplied credentials.

Browser checks cover keyboard type-ahead and link activation, explicit upload/checkpoint
ownership, read-only report downloads, fresh role checks at development entry, selector
rendering after redirects, choice preservation on refresh, and simulated directory
unavailability. These are bounded keyboard/browser checks, not complete screen-reader
or accessibility qualification.

The directory exposes existing records and reports. Findings, reviewer responses,
approvals, model reproduction, and independent assessment workflows remain D09 work.
Member administration/enrollment UI, SSO/MFA, retention/egress policy, tamper-proof audit,
durable job authority, expert isolation, and production recovery remain open. Private
runtime fixtures are synthetic qualification, not production installation or recovery.
