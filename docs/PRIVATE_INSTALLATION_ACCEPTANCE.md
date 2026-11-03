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

## Coherent qualification profile

The automated profile is one organization on Ubuntu 24.04 Linux with the exact
four-image offline bundle. Current full qualification targets native ARM64;
the other five CI jobs retain AMD64 coverage. The earlier AMD64 two-root
installation stage passed, but its complete native PostgreSQL suite exceeded
900 seconds and remains unqualified. ARM64 evidence never confers AMD64 support.
Each fresh host's architecture must match its exact frozen image bundle.
The profile uses PostgreSQL 17, a dedicated Redis
broker and reconstructible Redis cache, the fixed API/worker/dispatcher image,
and the immutable frontend/TLS ingress image. Image, package and asset hashes
come from the separately trusted image-set manifest. Docker and Compose versions,
OS, architecture, observed host resources and per-service limits are retained;
these observations do not establish a customer capacity envelope.

The native PostgreSQL job uses GitHub's standard public-repository
`ubuntu-24.04-arm` runner: four CPUs and 16 GB RAM, with the same original
steps, two test workers, loadfile scheduling, no worker restarts, coverage,
skips/retries and 900-second native child cap. The repository is public and
this standard runner has no runner charge. This is an execution-profile
experiment, not a claim that hardware caused previous timeouts. Full PR and
independent main success are still required.

The existing adoption qualification now creates two distinct empty owned roots
from the same exact image IDs. Each run keeps the original initialization,
authentication, TLS, queue, fault, retry and cleanup assertions. The installed
developer uploads synthetic classification and regression CSVs through verified
HTTPS, queues training on the installed worker/dispatcher, exports each candidate,
and queues feature-only scoring. A separate read-only container from the exact
API image replays both chunk sizes with no network, installation mounts or
credentials. Duplicate submissions must retain their original job IDs; training
digests and all approval flags must remain unchanged.

After validating and stopping/removing all application services, the same owned
installation produces a custom PostgreSQL dump and complete bounded regular-file
artifact inventory. The fixture encrypts one combined archive with AES-256-GCM,
decrypts and checks every member, checks the database archive catalog, and refuses
tampering or a different plan binding. The temporary key, backup and installation
are removed with the owned root. Reports retain hashes and checks, not raw
database/artifact bytes, passwords, cookies or keys. This verifies baseline
backup creation; durable operator key custody and machine-loss restore remain
explicitly unqualified under D07-T04 and operational acceptance.

Run the existing command with `--adoption-check` to execute this extended route.
Its reports include `clean-installation-acceptance.json`, `dependency-start.json`
and a second independent-root receipt under `clean-repeat/`. A successful image
import, partial test run or a prepared source patch does not emit a successful
acceptance receipt. Restricted customer installation uses `pull_policy: never`
and internal service networks; online dependency staging is a separate process.

Operators still supply approved host storage encryption, certificate/secret
delivery, backup-key custody, resource sizing and recovery policy before actual
customer use. The synthetic technical acceptance does not confer release,
customer, production-model-use, upgrade or restore approval.

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
