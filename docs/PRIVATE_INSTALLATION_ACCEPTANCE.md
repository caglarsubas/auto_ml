# D07-T02 — Clean-install closure target

The next D07 closure is a reproducible installation on the supported Linux
profile. P162's optional snapshot-read optimization is P1 work and is not a
prerequisite. Installation, upgrade, restore and customer acceptance retain
separate evidence; a preparation script or successful image pull closes none
of those gates.

## Before online dependency staging

Run `python3 scripts/private_build_preflight.py`. Its read-only JSON distinguishes
an unavailable selected Docker engine from failed public HTTPS and synthetic
DNS accompanied by a TLS failure. Exit 0 means the current host can attempt
online staging; exit 2 means resolve the reported prerequisite first. Checks
use verified TLS, fixed public endpoints, bounded child processes and no retries.
The command never changes the current Docker context, VPN, DNS or containers.
Synthetic DNS with working TLS is accepted. No response bodies, tokens or raw
exceptions are retained.

This is an online build-host diagnostic. Do not require internet access for an
offline customer installation. Host success also does not establish guest,
Docker-daemon or signed CDN-layer connectivity. A failed isolated image pull
still needs its own exact-image evidence before a full preparation.

## Finite acceptance sequence

| Stage | Existing implementation to reuse | Required closure evidence |
|---|---|---|
| Freeze the supported profile | API/frontend/ingress packages and `private_image_set.py` | Source and image IDs, architecture, package/assets inventories, trusted manifest digests and resource envelope for one Linux profile. |
| Import into a clean restricted-network environment | Image-set verification/import and `qualify_private_image_set.py` | Empty owned image slots; exact offline import; tampered archives refused; no dependency download during installation. |
| Initialize and start | Installation plan/check/init/resources, dependency init/start, schema init and application adoption | New owned installation root; actual initialization; PostgreSQL/cache/broker TLS; migrations; authenticated HTTPS; worker/dispatcher operation. |
| Exercise and hand off | Existing TLS/browser/native-job/scoring and lifecycle checks | Observable developer-to-scoring workflow, restart evidence, backup creation with matching database/artifact inventory, operator commands and retained receipts. |
| Reproduce and close | The same frozen inputs on a second clean environment | Successful process exits and original assertions, exact output manifests, cleanup record and independent review of the evidence. |

`qualify_private_installation_plan.py` already composes the existing path,
initialization, dependency, resource, adoption and startup qualifiers. Extend
that route for missing acceptance rather than building another installer.
Existing synthetic fixtures remain useful component evidence; they do not
become a clean-install acceptance receipt by relabeling.

The task stays open until both ledger acceptance criteria are demonstrated.
Restore after machine loss and interrupted upgrade/rollback are D07-T04 and
D07-T03 respectively. Their evidence is not inferred from backup creation or a
healthy point-in-time lifecycle observation. D07-T02 completion unlocks both
tasks; it does not depend on P162.

## Progress accounting

The fixed inventory contains 66 acceptance tasks. Closing D07-T02 changes the
done share from 2/66 (3.0%) to 3/66 (4.5%), provided no other task changes. Code
preparation, PR checks and merge are reported separately. Do not subdivide the
inventory or mark an entire task done to improve the percentage.
