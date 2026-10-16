# Canonical frontend dependency installation (P82)

The repository root retained a second npm manifest and lockfile declaring
Angular CLI 18, `menu` and npm `xlsx` 0.18.5. The application, documented commands,
CI jobs, Docker build and private frontend packager use the manifests under
`frontend/`, which already declare Angular 22 and vendored SheetJS 0.20.3.
Installing at the root could therefore select an obsolete, unrelated toolchain.

Remove the unused root manifests and document the existing installation path:
Node 24 with `cd frontend && npm ci`, or `npm --prefix frontend ci` from the
repository root. Correct the README's stale mathjs and SheetJS version entries.
The supported frontend manifest, lockfile and vendored archive remain identical
to the independently qualified P81 main. No dependency is upgraded or downgraded,
and installed packages, services, customer configuration and application behavior
are unchanged. Existing local root installations are outside the supported
frontend profile; source cleanup does not uninstall them.

Manifest-only audits used owned copies of both dependency graphs, explicit npm
registry access and empty npm configuration. They installed no packages and ran
no package lifecycle scripts. The retired root graph reported 35 findings,
including one critical finding. The supported frontend graph reported 11 high
findings, all on nodes marked development-only by its lockfile, and no critical
findings. These are audit observations, not installed-runtime or exploitability
assessments, and removing the root graph does not resolve the supported findings.

The supported findings trace to the [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
checked on 16 October 2026: versions through 3.0.3 are affected and no patched
version is listed. Applicability, mitigation and build/test supply-chain
qualification remain open; dependency classification does not establish release
acceptance. No audit exclusion, waiver, downgrade or relaxed CI gate is added.

Qualification checks the canonical graph's byte identities and the existing
private frontend/image/installation metadata workflows after removal. No new
test mirrors a deleted manifest or README sentence. Complete six-check CI still
installs the supported frontend afresh, builds the private image set and runs
the existing scientific, authorization, runtime, frontend and browser suites.
No scientific workload, timeout, coverage/skip limit or retry budget changes.

Source qualification is recorded in [P82 evidence](evidence/p82-qualification-2026-10-16.json).
Exact-head/private reports and independent merged-main qualification remain
required. Full D07 lifecycle/upgrade/restore, durable search, expert execution,
release and customer-acceptance gates remain open.
