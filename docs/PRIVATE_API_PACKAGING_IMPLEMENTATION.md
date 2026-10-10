# P29 — Fixed private native API and offline image handoff

Updated 11 October 2026. Partial D06/D07 after verified [PR #118](https://github.com/caglarsubas/auto_ml/pull/118). The existing developer stack remains available. This packet supplies a native API/worker/dispatcher image and an offline handoff, not a complete governed installation or a release qualification.

## Build and trust

`scripts/private_api_package.py context DESTINATION` creates a new context from explicitly allowed, Git-recorded application Python, bundled assistant skill text, knowledge-bank Markdown and fixed runtime entrypoints. It rejects source symlinks. It excludes tests, environment files, databases, model state, uploaded datasets and indexes even when such files are tracked historically. Existing files are preserved. The context records captured source hashes, the Git base, whether the worktree had changes, and dependency/Dockerfile hashes; the commit field alone is not proof of the captured working tree.

The supplied dependency Dockerfile builds the public core from exact Python package versions. On x86_64 it includes XGBoost's declared NCCL dependency; hardware acceleration is not qualified. Dependency builds require network access and review of the selected base/distribution artifacts. This is not a hash-locked wheelhouse, a reproducible-from-source binary build, a vulnerability attestation or a signed supply-chain package.

The private builder accepts an exact trusted local dependency image ID, creates its own unique temporary reference, and copies only system directories into a fresh image before adding the allowlisted application. It does not inherit the dependency image's application/data layers. The dependency image's system paths remain trusted input; arbitrary operator-supplied system images are not sanitized or certified. Never select a customer installation as a dependency source.

```sh
python scripts/private_api_package.py context /tmp/declarai-private-context
docker build -f /tmp/declarai-private-context/dependencies.Dockerfile \
  -t declarai-private-dependencies:reviewed /tmp/declarai-private-context
python scripts/private_api_package.py build \
  --base-image "$(docker image inspect declarai-private-dependencies:reviewed --format '{{.Id}}')" \
  --tag declarai-private-api:reviewed
```

The fixed image has UID/GID 10001, no automatic migration/indexing/live reload and no source mount. Its runtime manifest inventories Python/platform, installed distribution versions and every packaged application file. Each normal service launch verifies that inventory before importing Django, then performs the existing actual PostgreSQL TLS/current-migration/authenticated Redis TLS preflight. Distribution inventory checks versions, not every installed library byte; the exact Docker image digest and verified archive bind the whole installed filesystem. Hashes detect changes relative to trusted inputs and do not establish independent authenticity.

## Offline handoff

```sh
python scripts/private_api_package.py export --image sha256:IMAGE_DIGEST /approved/handoff
python scripts/private_api_package.py verify /approved/handoff \
  --expected-manifest-sha256 TRUSTED_MANIFEST_DIGEST
python scripts/private_api_package.py load /approved/handoff \
  --expected-manifest-sha256 TRUSTED_MANIFEST_DIGEST
```

Export returns the manifest digest for a separate trusted handoff channel. A digest copied from the same untrusted package does not establish that trust. The package contains exactly `manifest.json` and `image.tar`; the TAR is normalized to one image graph without tags or secondary image selections. Legacy Docker config identity and OCI manifest/index identity are verified separately; the selected engine identity survives handoff. OCI metadata/config/layers must form the complete, digest-verified graph and agree with the legacy compatibility record. Native builds disable additional build attestations; this is not a signed provenance claim. Import checks the externally expected manifest digest, archive digest/size, bounded raw TAR headers, image identity, paths and graph before calling Docker. It refuses extension records, links, traversal, foreign tag annotations, extra graphs and malformed/oversized metadata. It never extracts layers into the host filesystem.

Import consumes a private staged copy, so swapping the original path after verification cannot alter the imported bytes. It then verifies the exact loaded image's platform and native inventory. It does not pull dependencies or use an image tag. Limits are 8 GiB per archive and 2 MB per metadata record; sufficient local disk is required for staging and Docker storage. These limits are not workload or capacity promises. A failed post-import check can leave the explicitly imported digest in the local Docker store; it never starts a service or adopts/promotes that image.

## Private services

`docker-compose.private-api.yml` is an operator-configured fragment for three fixed roles using the same verified image. `pull_policy: never`, a read-only root, no capabilities, no new privileges, fixed process/resource limits and an external approved network are specified. It has no public port, source bind or Docker socket. Secret/CA mounts are read-only; the artifact directory must already exist, be writable by UID/GID 10001 and use customer-approved encrypted storage. Bind mounts do not silently create missing host directories. Cache/index storage remains reconstructible.

Set the Compose selectors `DECLARAI_PRIVATE_IMAGE` (the verified sha256 image ID), `DECLARAI_PRIVATE_ENV_FILE`, `DECLARAI_PRIVATE_SECRETS`, `DECLARAI_PRIVATE_ARTIFACTS`, `DECLARAI_PRIVATE_NETWORK` and `DECLARAI_PRIVATE_SOCKET_VOLUME`. The environment file contains the explicit private settings from [runtime configuration](private-runtime-configuration.md), with `DJANGO_TRUST_PROXY_TLS=true`, `DECLARAI_MEDIA_ROOT=/artifacts` and secret/CA `_FILE` paths under `/installation`. The broker must use its dedicated `rediss://` URL file and CA. Database roles, migrations, account/project enrollment, network restrictions, volume ownership and retained-data policies require the installation's approved procedure; startup never performs them automatically.

The API exposes only `/run/declarai/api.sock` under an existing, owned directory without group/world write permissions. Gunicorn 26.2.0 runs one synchronous API worker with a 120-second request timeout. Legacy SFS/HPO progress and cancellation still live in process memory, so multiple API workers and automatic request-count recycling are deliberately disabled. A process restart can still lose that legacy control state; durable search migration remains required. The separate native Celery service retains its existing two-worker bound. There is no reload/control socket or TCP binding. Server options cannot be injected through Gunicorn/forwarder environment overrides or role arguments. Gunicorn's own forwarded-scheme/forwarder-header handling is disabled; Django recognizes only the explicitly approved canonical `X-Forwarded-Proto` header. The socket volume and its authorized peer form the ingress trust boundary.

An operator-controlled buffering TLS ingress must strip client proxy headers, supply the canonical scheme/Host, and have only the required socket access. See [Gunicorn deployment](https://gunicorn.org/deploy/) and [settings](https://gunicorn.org/reference/settings/). Frontend assets, Django admin static assets, TLS ingress, request buffering/body limits, customer certificates, secret rotation and full browser installation are not delivered by this fragment. Do not expose the local socket through an untrusted peer. Existing synchronous training/search paths remain synchronous; requests exceeding the fixed timeout are not qualified, and durable migration remains D07 work.

Workers and dispatcher use the existing fixed private job launcher after the same inventory/preflight checks. Startup connection success is not a continuous health guarantee. Service restart policy is bounded; production monitoring, upgrades/rollback, live backup/recovery and machine-loss drills remain open. Provider/telemetry defaults are disabled/lexical, but this packet does not implement comprehensive network egress policy. Dedicated gVisor expert execution remains unavailable and mandatory for the first governed release.

## Qualification

The existing PostgreSQL owner accepts `--private-api-image sha256:IMAGE_DIGEST`. It supplies only its randomly named, explicitly disposable database/network to a fresh read-only fixed API container, separate secret/artifact/socket volumes and a networkless Unix-socket probe. Real Gunicorn requests exercise HTTPS interpretation, allowed Host, session/secure cookies, CSRF denial/admission, project/media authorization and recorded logout. This probe represents an authorized local ingress; it does not establish a real TLS ingress/browser installation. No installation data or credentials are exported into evidence.

The same check is required in the existing PostgreSQL CI job alongside unchanged scientific tests, recovery drills, timeout, coverage and skip budgets. The other five jobs remain. Packaging regressions exercise tracked-data exclusion, immutable source/runtime inventory, bounded archive/graph handling, external digest trust, source-path swaps, role/environment failures and native server configuration. Complete private installation, supply-chain authenticity, comprehensive egress/retention, production recovery, expert isolation, full independent refit/assessment reproduction and all release/value/customer gates remain open. Qualification is pending until recorded in the canonical ledger and evidence.
