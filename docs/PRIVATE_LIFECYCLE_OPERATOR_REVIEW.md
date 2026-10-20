# Private installation lifecycle: operator review checkpoint

`scripts/private_lifecycle_readiness.py` provides a bounded, read-only report
before an operator chooses a maintenance or recovery plan. It is supported for
the current v3, single-organization, native Linux installation with DeclarAI
managed dependencies. Run on the target host as root, from the reviewed source:

```sh
python3 scripts/private_lifecycle_readiness.py /absolute/path/to/plan \
  --expected-plan-sha256 <independently-trusted-plan-manifest-sha256> \
  --client-ca /absolute/path/to/operator-selected-client-ca.crt
```

The digest must come from the trusted delivery record, not be accepted merely
because it was recomputed from an untrusted plan. The selected CA must satisfy
the existing absolute-path, root-owned, bounded, no-link/no-ACL trust checks.
The command emits JSON to stdout. If retaining it, use a protected operator
location; do not store credentials or customer records alongside the report.

## What the report observes

- Plan and initialization binding, paths, native image identities and the
  supported Docker/runtime profile.
- All four application and three dependency containers against their exact
  profiles, managed startup receipt, network and socket membership.
- Two observations of service identities, restarts and stable engine state
  surrounding a real anonymous HTTPS request using the selected CA, declared
  hostname/SNI and address. Changes or invalid state fail the observation.
- One existing managed operation lock held throughout Docker inspection and
  HTTPS. A held, absent, unsafe or replaced lock fails without creating one.

The report allowlists nonsecret identifiers and engine state. It emits no
container environment, credential values or hashes, certificate material,
raw engine errors, model data or customer database content. It does not create
containers, execute in containers, start/stop/repair services, migrate, enroll,
run a fresh database/broker preflight, write installation receipts or adopt a
candidate. Existing adoption still creates a missing lock under its original
protocol; the new read-only observer explicitly disables that behavior.

## What remains unverified

The observation can become stale immediately. The lock only coordinates
participating DeclarAI controllers; it cannot exclude privileged direct host
or Docker changes. A healthy anonymous HTTPS endpoint and matching container
profiles do not establish current database schema, broker delivery, a usable
backup, restore integrity, upgrade/rollback compatibility, host firewall or
network-policy acceptance. Engine observation is not application-level
maintenance quiescence. All maintenance, recovery, upgrade, installation,
release and customer-acceptance claims remain false or explicitly open.

## Decisions needed from the deployment owner

Before selecting or executing a real lifecycle drill, review these concrete
inputs with the report:

| Input | Review needed |
|---|---|
| Target and trust | Identify the installation host/root and the independently trusted plan digest and client-CA path. Do not share private keys or passwords. |
| Downtime | State the approved maintenance window and maximum interruption, including whether workers must drain or jobs may be interrupted. |
| Recovery objectives | State acceptable data loss (RPO) and time to recover (RTO); identify who verifies restored data and artifacts. |
| Backup storage | Select destination, encryption/key ownership, available capacity, retention and independent restore access. |
| External controls | Confirm ownership and acceptance criteria for firewall, ingress/egress and restricted-network operation. |

These choices define the next implementation and acceptance profile. They do
not themselves authorize arbitrary service changes. A subsequent executable
backup/restore or upgrade plan must bind the chosen target, source versions,
consistent database/artifact boundary, restore checks and rollback procedure.
Durable training/search execution and full D07 recovery/upgrade gates remain
open; this report does not close D07 or M2.

## Qualification

Unit cases exercise read-only behavior, real kernel contention, descriptor
release, invalid states/images, changes between observations and output
redaction. The existing owned Linux installation qualifier exercises all seven
real services and selected-CA HTTPS, rejects a held lock and paused worker,
and verifies unchanged service identities/state and recorded history. Only
that synthetic fixture pauses/unpauses its owned worker; the observer never
repairs the fault. The original suite, physical PostgreSQL cases and limits
are retained. Qualification evidence is recorded in
[P117 source receipt](evidence/p117-qualification-2026-10-20.json), with later
PR and independent push-main evidence tracked in the roadmap ledger.
