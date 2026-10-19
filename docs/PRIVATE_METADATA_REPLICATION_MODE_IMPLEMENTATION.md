# Current PostgreSQL metadata replication mode

P107 requires the actual connection used by private startup to have
`session_replication_role` set to `origin` or `local`. The selected metadata
profile excludes `replica`, including when every required RI trigger has valid,
enabled catalog metadata. The check remains part of the existing read-only
schema query, with its original two parameters and four-column result. It uses
`pg_catalog.current_setting`, built-in equality and a built-in text array, so
caller-controlled lookup functions and operators cannot fabricate normal mode.
Invalid mode produces the existing redacted `job_schema_invalid` before
broker/cache access. Unavailable evidence propagates to the runtime's existing
`job_storage_unavailable`; direct schema callers retain their database exception.

The ordinary-role predecessor proof has no SET authority for this parameter:
its own attempt is denied with SQLSTATE 42501. A separate administrator of the
owned PostgreSQL fixture temporarily installs a `replica` login default. The
application reconnects; the administrator resets that default before startup is
tested. All role attributes and defaults have returned to baseline, but the
already-open ordinary connection still uses `replica`. Startup accepts it, and
an orphan commits. A second ordinary connection using `origin` observes that
committed row; related-user lookup fails. All 152 genuine trigger OIDs and
attributes, all constraint/column metadata and all 31 migration records remain
unchanged. No role elevation, membership or parameter-setting grant is used.

The fixed startup rejects this state before reaching the broker response
fixture. The proof still demonstrates the underlying direct-write hazard, then
removes only its orphan, reconnects normally, verifies deferred rejection at
commit and preserves original rows/history and duplicate rejection. A separate
`local` healthy control also verifies ordinary trigger firing.

## Qualification

Append 48 physical cases to the existing owned PostgreSQL qualifier:

- Direct schema, runtime and management-command checks for all three active
  modes after the administrator resets their login defaults.
- Healthy active `origin`/`local` connections whose login default is subsequently
  changed to `replica`, demonstrating that evidence describes the current
  connection rather than a future connection's default.
- Public-first search paths containing forged `current_setting`, text equality,
  or both, with zero side effects from the forged functions.
- Actual revoked access to the lookup function, its static runtime failure and
  successful restoration of its original permissions.

The frozen predecessor passes 35 new controls but misses 13 expectations: all
12 replica-mode denials and direct lookup unavailability. The candidate passes
all 48. All original 392 RI cases remain present with identical expected
outcomes; the complete physical qualifier passes 440 without skips or retries.
Its existing JSON/JUnit/log artifact and host-only administrator boundary remain.
The application process receives only its own password and no Docker socket.
Owned resources are cleaned up; no public port or customer installation is used.

The workflow and 163 of 165 protected test/execution files remain byte identical.
Only the two qualification helpers receive additive coverage. Removing the
P107 additions restores both helpers' P106 bytes exactly. The original pytest
inventory, assertions, workloads, resource/pool/coverage/retry/skip budgets,
900-second full native deadline and 120-second per-test limits are unchanged.
Source hashes and local results are retained in
[P107 qualification](evidence/p107-qualification-2026-10-19.json).

Initial TLS and broker responses in the semantic and physical qualifiers are
explicit response fixtures over plaintext. Actual private TLS, installation,
workers, recovery and browser qualification remain separate required receipts.
This is a current-connection observation, not historical row-integrity
certification, broad parameter-privilege attestation, arbitrary replication
support or continuous fencing after the check. It does not reset settings or
repair data. Future connections and later state changes require their own
qualified checks. D07 and lifecycle/release/customer acceptance remain open.

References: [PostgreSQL connection defaults](https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-SESSION-REPLICATION-ROLE),
[role login defaults](https://www.postgresql.org/docs/17/sql-alterrole.html).
