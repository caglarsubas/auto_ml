# Private plan verification and filesystem prerequisites — P35

P35 verifies a saved P34 application-layer plan against a separately trusted digest and adds Linux filesystem metadata checks before installation. This is partial D07. It does not initialize dependencies, deliver credentials, migrate a database or adopt services.

## Verify the saved plan

```sh
python scripts/private_installation_check.py verify /approved/plan \
  --expected-plan-sha256 TRUSTED_PLAN_MANIFEST_DIGEST
```

Use the digest returned by the [P34 renderer](PRIVATE_INSTALLATION_PLAN_IMPLEMENTATION.md), retained through the approved handoff channel. Reading a new digest from an untrusted plan cannot establish that trust. Verification accepts exactly the six bounded regular files of the P34 plan; duplicate JSON keys, additional/missing files, links/FIFOs, changed bytes, unsupported claims and inconsistent image/ingress bindings are rejected. Directory/file descriptors capture the verified inputs rather than reopening mutable caller paths.

Integrity alone is insufficient. The verifier revalidates the strict operator request, exact four-image metadata, architecture, sealed ingress configuration and original application-layer profile. It derives the expected Compose and prerequisites again and compares canonical JSON, retaining value types as well as meanings. JSON numbers cannot substitute for booleans or declared integer identities. Even a newly hashed plan cannot add arbitrary commands, privileged containers, weaker permissions, debug settings, external providers or a different bind/authority. No modules from the plan are imported; JSON is the only input format.

This command verifies the saved plan and its bound metadata, not the multi-GiB archives or loaded Docker images again. Use the P32 image-set verifier/loader with its separately trusted outer digest for archive/import qualification. `archives_reverified` remains false. Installation/release/expert qualification remain false.

## Check Linux paths without reading secret values

```sh
python scripts/private_installation_check.py check-paths /approved/plan \
  --expected-plan-sha256 TRUSTED_PLAN_MANIFEST_DIGEST
```

Plan verification completes before any installation access. The path check requires Linux and `O_PATH`. It pins every absolute ancestor without following links, rejecting ownership outside root/UID 10001 and group/other writable ancestors, including shared writable temporary roots. It requires the three recorded application-secret, TLS-secret and artifact roots to have UID/GID 10001 and exact mode 0700. Extended/default POSIX ACLs at those selected roots are outside this initial supported profile and are rejected.

The two secret directories must contain exactly the seven declared filenames. Each secret must be a regular file with one hard link, UID/GID 10001 and mode 0400. Secret-value files must contain 1–4096 bytes; certificate/key files permit 1–65536 bytes. Metadata-only `O_PATH` descriptors reject symlinks, hard links, FIFOs, empty/oversized files and permissive or unexpected identities. No secret contents or hashes are read or emitted. The checker neither lists nor reads artifact descendants and performs no repair/chown/chmod. Failure emits a stable reason code without credential values.

The receipt records the plan digest, architecture, root device/inode identities and metadata check result. This is a point-in-time observation, not a lock, deployment approval or guarantee against later changes. The read-only check cannot prove secret entropy, URL semantics, certificate trust/validity/key pairing, storage encryption/capacity/retention, network/socket isolation, database privileges/migrations or actual runtime connectivity. These remain explicit operator checks and subsequent qualification work; their receipt fields stay false.

## Qualification and limits

The existing offline planning qualifier accepts `--path-check-image` selecting the exact API identity from the verified set. It invokes `scripts/qualify_private_installation_check.py` using only UUID-owned synthetic Linux installation/plan volumes. Five actual native cases check valid UID 10001 metadata, permissive files, hard links, symlinks and writable ancestors. A synthetic artifact FIFO remains uninspected. The checker runs as UID/GID 10001 with no network/capabilities, a read-only root and read-only fixture/code mounts. The separate trusted synthetic-volume initializer has only the filesystem capabilities needed to set fixture identities; this is test preparation, not a product service or expert runner. All owned volumes and containers are cleaned up, including failure paths.

Hosted CI uses the newly imported native AMD64 API image; local qualification uses native ARM64. The checker code is trusted qualification harness source mounted read-only, not added to the sealed API runtime allowlist. No existing installation, customer data or production service is read or changed by these fixtures. Full prior TLS/browser/job/recovery checks, test/skip/time/coverage budgets and six CI jobs remain.

[P35 source evidence](evidence/p35-qualification-2026-10-11.json) records actual qualification. Complete secrets/storage/dependency initialization, network/socket preparation, service adoption, authenticated supply, upgrade/rollback, production recovery, expert isolation, reproduction, accessibility and all release/value/customer gates remain open.
