# Private migration history guard (P83)

A private service could previously start with migration history that the selected
sealed image did not recognize. Django's migration plan ignores unknown applied
records and can treat an applied descendant as satisfying a missing ancestor.
Checking only for a pending plan therefore does not establish compatible history.

The shared private runtime preflight now checks Django's history consistency and
requires every applied migration to exist in the selected image's disk graph.
Unknown or inconsistent history blocks API, worker and dispatcher startup with
`job_migration_history_invalid`, before broker/cache connectivity is attempted.
A consistent pending graph retains `job_migrations_required`; storage failures
retain `job_storage_unavailable`. Diagnostics omit migration names and database
errors. The preflight never edits migration history, migrates, repairs or reverses
schema, or changes application-role privileges.

This guard follows the current sealed, unsquashed private installation profile.
It intentionally blocks histories from newer/foreign images and removed migration
files. Squash/removal compatibility needs a reviewed upgrade policy; it is not
inferred from an empty Django migration plan. Matching history does not prove
physical columns, constraints or data are intact, nor does it qualify rollback.
Existing development/legacy startup and fresh initialization remain separate.

Twelve database-backed regression cases exercise actual Django loader/recorder
behavior through the direct preflight and management command. They cover unknown
app/version records, missing ancestors, a consistent pending leaf and current
history, with history preservation and no early broker access. Only TLS transport
is stubbed in these focused tests; full private CI independently checks actual TLS,
installation and service adoption. The corrected predecessor fails eight cases
and passes four references under PostgreSQL. A draft pending-leaf fixture actually
had a downstream dependency; its logs are retained, and the fixture was corrected
without weakening product checks. The early draft full local run was stopped
before qualification and is not counted as a pass.

See [P83 source evidence](evidence/p83-qualification-2026-10-16.json).
Exact-head six checks/private receipts and independent main qualification remain
required. Scientific workloads, timeouts, concurrency, retries, coverage and skip
budgets are unchanged. Durable search, dependency findings, complete upgrade/restore,
expert isolation, release and customer gates remain open.
