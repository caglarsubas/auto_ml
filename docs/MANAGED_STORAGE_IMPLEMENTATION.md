# P13 — Managed native inputs and preserved generated files

Updated 9 October 2026. This packet follows merged [PR #102](https://github.com/caglarsubas/auto_ml/pull/102)
and partially advances D04, D06 and D08 in the [canonical ledger](product-roadmap.json).
The preceding merge-main CI passed all five jobs. Release, deployment, customer
acceptance and complete milestone qualification remain open.

Previously, encoding, data-quality and feature-card requests could name an
absolute file outside artifact storage. Explanation requests could select an
unverified XGBoost model file. Uploads and encoded CSVs used second-resolution
names, so repeated or concurrent calls could overwrite an earlier result.

Native DRF requests now validate reference selectors after session authentication
and before their handlers run. `file_id` must be a canonical positive integer
within the database identifier range; route, query and body selectors must
agree, and duplicate query selectors are rejected. Oversized numeric strings
fail with an actionable 400 rather than reaching integer conversion or storage.
Table selectors must resolve to CSV/Excel files inside `MEDIA_ROOT`; parent
traversal, hidden components, external paths/symlinks, nonregular files and
malformed references fail with `managed_storage_reference_invalid`. Relative
managed references and existing absolute paths inside the root remain usable.
The same helper guards the corresponding handler reads and generated outputs.

A client-selected model override must identify the model in a hash-verified
immutable execution bound to the requested dataset. An explicit execution ID
must agree with that path. Unsupported/unverified legacy overrides return 409;
verified native XGBoost overrides use development rows and never read the final
holdout. Existing server-managed legacy default diagnostics remain available;
this does not certify their historical provenance. The override uses XGBoost's
loader, not a Python pickle loader. Other internal native fitted-state readers
are outside this packet's complete security qualification.

New upload, standalone encoding and modeling display CSV names use independent
UUIDs. Exclusive creation prevents even a forced collision from replacing an
existing file. Standalone encoding also creates its metadata exclusively and
returns success only after it is written; a metadata failure removes that
request's newly created CSV. Modeling's optional display CSV still reports its
absence if saving fails. These are file-preservation guarantees, not a
transaction across the database and filesystem or a crash-recovery protocol.
Existing files are not renamed. A missing historical declaration falls back
only when its legacy processed-file match is unique; ambiguous matches no
longer select an arbitrary neighboring dataset.

The [qualification record](evidence/p13-qualification-2026-10-09.json) binds the
executable source, environment and retained reports. Regression coverage uses
actual Django sessions and CSRF, asserts rejected inputs never reach readers,
forces output collisions, breaks metadata writes, and checks external output
symlinks, nonregular files, hidden aliases and oversized/conflicting IDs. It
also exercises valid relative/absolute tables and verified model overrides.
The governed Chromium suite includes authenticated file downloads and repeated
upload/encoding preservation alongside existing login, review, raw-replay and
scoring journeys. The real MCP SDK stdio qualification remains separate.

Local qualification passed 1,692 backend tests with six expected skips and
68.92% combined statement/branch coverage against the unchanged 50% gate.
All 540 frontend unit tests, 23 governed browser/API checks and 49 ledger
checks passed. Ruff, migration drift, dependency consistency, frontend build
and TypeScript checks passed; frontend lint retains 158 existing warnings.
Actual MCP stdio registered 29 tools and recorded ten access events. GitHub
CI is a separate observation from these local results.

This root boundary does not grant dataset/project access. Signed-in REST users
still have installation-wide data access; MCP retains its separately scoped
installation actor/grants. Project developer/reviewer roles, ownership and
policy checks, common egress/retention controls and trustworthy review approvals
remain required. The filesystem/controller are trusted; these checks do not
provide protection against a hostile process racing filesystem mutations.
Expert Python remains blocked until exact authority and Linux isolation are
implemented and qualified. Full immutable legacy stages, durable jobs,
PostgreSQL deployment/recovery and independent clean reproduction remain open.
