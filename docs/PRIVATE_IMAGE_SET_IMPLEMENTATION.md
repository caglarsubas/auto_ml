# P32 — Verified offline native image set

The private API/worker/dispatcher image, compiled TLS/frontend ingress, PostgreSQL 17 and Redis 7 can travel as one digest-pinned handoff. This is partial D07. Image preparation, offline import, installation, migration, service adoption, release and customer acceptance remain distinct states.

## Prepare and export

Select separately trusted pristine dependency images. Never select an installation/container snapshot or an image containing customer secrets/data. API and ingress come from the existing [API](PRIVATE_API_PACKAGING_IMPLEMENTATION.md) and [frontend](PRIVATE_FRONTEND_IMPLEMENTATION.md) builders. Dependencies are acquired and reviewed before preparation; these commands do not acquire them:

```sh
python scripts/private_image_set.py prepare --role postgres \
  --base-image sha256:TRUSTED_LOCAL_POSTGRES_IMAGE \
  --tag declarai-private-postgres:reviewed
python scripts/private_image_set.py prepare --role redis \
  --base-image sha256:TRUSTED_LOCAL_REDIS_IMAGE \
  --tag declarai-private-redis:reviewed
python scripts/private_image_set.py export /approved/new-image-set \
  --api-image sha256:API_IMAGE --ingress-image sha256:INGRESS_IMAGE \
  --postgres-image sha256:PREPARED_POSTGRES_IMAGE \
  --redis-image sha256:PREPARED_REDIS_IMAGE
```

Each preparation returns the exact base and resulting native image identities, architecture and observed version. A fresh native manifest preserves the base filesystem/entrypoint and adds fixed role/base labels. No `RUN`, downloads, package installation or supplied commands enter the build. Upstream multi-platform/attestation graphs remain outside the existing tag-free, single-image archive profile; preparation uses `--provenance=false` rather than relaxing that reader. This records selected inputs and runtime behavior, not authenticated provenance or an attestation verification result.

The exporter requires exactly four distinct Linux images on one supported native architecture (`amd64` or `arm64`). It verifies the API's native inventory and fixed ingress profile. Read-only, networkless, unprivileged, resource-bounded probes inventory all sealed frontend assets and fixed ingress files and check dependency versions without starting services. The API component retains the P29 format. Other components carry their role, platform, archive identity/length/hash and runtime inventory. Each nested manifest is bound by the outer manifest. Publication renames a completed verified staging directory; existing destinations cannot be overwritten.

## Verify and import

```sh
python scripts/private_image_set.py verify /approved/image-set \
  --expected-manifest-sha256 TRUSTED_OUTER_MANIFEST_DIGEST
python scripts/private_image_set.py load /approved/image-set \
  --expected-manifest-sha256 TRUSTED_OUTER_MANIFEST_DIGEST
```

Obtain the outer digest through the separately trusted handoff channel. Copying a digest from the same untrusted package does not supply that trust. The set contains exactly `manifest.json` and four fixed component directories, each with exactly `manifest.json` and `image.tar`. Unknown/missing roles, duplicate JSON keys, links/nonregular inputs, extra files, changed manifests/archives, tags, ambiguous image graphs and inconsistent identities/platforms block import.

Both verification and import consume a private staged copy. Directory/file descriptors pin source inputs without following links; replacements of the caller's paths cannot change already captured import bytes. All four manifests and archives pass the existing bounded raw-header/graph verifier before the first Docker load. No archive layers are extracted into the host filesystem. Metadata is limited to 2 MB and archives to 8 GiB per role, up to 32 GiB per set; staging and Docker storage require additional free disk. These are handoff limits, not workload/capacity promises.

Import requires a matching native Linux engine, uses digest-only archives, then checks each loaded identity/platform and isolated runtime inventory. It does not retag images, configure networking/storage, mount secrets, migrate metadata, start services or adopt a deployment. Repeated imports preserve identities and existing tags. A later engine/runtime failure can leave earlier imported digests in the shared store; import is not a transactional installation, and it never deletes unrelated images to simulate rollback.

## Qualification and remaining work

Owned fixtures exercise alteration of the fourth archive and an incorrect outer digest before any Docker call, real native imports, repeated imports and unchanged selected-image tags. Unit checks cover malformed sets, linked/FIFO/bounded inputs, source replacement, graph/tag rejection, native platform mismatch, isolated probes, preparation boundaries and post-import identity/runtime failures. [P32 evidence](evidence/p32-qualification-2026-10-11.json) records final source binding and results.

CI prepares fresh native dependency images, exports all four roles, empties only its own four image slots, imports the complete set twice and then selects exact no-pull PostgreSQL/Redis identities for the existing full TLS/browser/metadata/recovery fixture. The application's scientific assertions, leases, retries, skips, timeout and coverage gates remain unchanged. Fixed API/ingress and actual database/broker operation are checked after import; the existing test runner still owns worker/scoring recovery. This does not newly qualify fixed-image worker task completion.

Complete restricted-network installation (including operator profile, certificates, secrets, storage, initialization and supervisor), authenticated software supply, upgrades/rollback, production recovery and resource qualification remain open. So do comprehensive egress/retention, training/search migration, expert isolation, independent refit/assessment reproduction, accessibility and all release/value/customer gates. No customer installation or running service is changed by this packet.
