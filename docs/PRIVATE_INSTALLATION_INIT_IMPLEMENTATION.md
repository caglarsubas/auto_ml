# Fresh private filesystem initialization — P36

P36 initializes the filesystem portion of a **new** P34/P35 installation. It consumes an independently digest-approved plan and an operator-provided secret delivery. No dependency, migration, network, container, account or existing installation is adopted by this command. This is partial D07.

```sh
sudo python scripts/private_installation_init.py /approved/plan \
  --expected-plan-sha256 TRUSTED_PLAN_MANIFEST_DIGEST \
  --secret-delivery /approved/secret-delivery
```

Run on the supported Linux host using trusted repository/controller code. The plan digest comes from the approved handoff, not a newly computed hash of untrusted input. The initializer is separate from the unprivileged fixed application image and cannot execute expert Python.

The plan's destination parent must already exist. Every ancestor must be root-owned, without group/other write access or extended/default POSIX ACLs. The destination itself must be absent; directories, files, links and dangling links block **before secret reads**. No parent is created or repaired.

The secret delivery must be an absolute path with exactly `app` and `tls` directories. The delivery and both children require UID/GID 10001, mode 0700 and no extended/default ACLs, reached through non-writable root/UID 10001 ancestors without following links. `app` contains `django-key`, `app-password`, `job-broker-url`, `postgres-ca.crt`, `job-ca.crt`; `tls` contains `tls.crt`, `tls.key`. Files require UID/GID 10001, mode 0400, a single hard link, and bounded nonempty regular-file contents. Value files allow up to 4096 bytes; certificate/key files allow up to 65536. The secret manager remains responsible for trustworthy delivery and entropy. Quiesce updates to the delivery while copying; captured bytes are not a lock against later source changes.

The three application values must be single-line UTF-8. The Django key meets the existing private shape requirement: at least 50 characters, five distinct characters, and no development-key prefix. The broker URL must be `rediss://:PASSWORD@job-broker:6379/N`, with database 0–99, authentication and no username, query, fragment or whitespace. This initial installation profile narrows the runtime's broader connection syntax. Secret bytes are copied unchanged. Certificates and keys remain opaque: parsing, expiry, authority/key pairing and actual server trust are still separate checks. No certificate trust or encryption claim is inferred from successful copying.

The new layout has root-owned installation/secrets parents with GID 10001/mode 0750; application/TLS secret and artifact roots have UID/GID 10001/mode 0700. Files have UID/GID 10001/mode 0400. The new artifact root starts empty; no existing artifact tree is inspected. A root-owned mode 0600 `initialization.json` binds the nonsecret result to the plan digest and unique initialization ID. It contains no secret values, value hashes or delivery path. The source delivery is unchanged and is retained for the operator's secret-manager lifecycle.

The initializer writes and fsyncs a mode 0700 private sibling stage, then publishes with Linux `renameat2(RENAME_NOREPLACE)`. Unsupported publication blocks; no replacing-rename fallback exists. An empty competing destination is protected too. UID 10001 access is enabled only after publication. Ordinary pre-publication failures remove only the owned staging directory. An abrupt host/process loss can leave a private sibling stage, or a published directory before access/durability completion. Inspect and reconcile these states before retrying; the command never overwrites or resumes an observed destination. This is not complete crash recovery, upgrade or rollback.

Run the existing P35 `check-paths` as the application identity afterward. Its receipt still reports point-in-time filesystem metadata only. Before service adoption, qualify storage encryption/capacity/retention, certificate semantics, database/cache/TLS broker initialization and privileges, explicit migrations/enrollment, dedicated networks/socket, firewall and actual authenticated runtime behavior.

The owned native qualification runs the initializer on seven fresh synthetic Linux cases: success plus unsafe-parent, invalid broker value, hard-link, symlink, interrupted-write and competing-empty-destination faults. It verifies exact copied fixture bytes, real identities/modes, cleanup, rejection of a repeated initializer and UID 10001 P35 path checks. Fourteen owned volumes are removed. Trusted harness code is mounted read-only in the exact API image with no network; only the initializer/test preparation has the bounded filesystem capabilities required for ownership. It does not initialize operator resources or add arbitrary entrypoints to the sealed API runtime. Hosted CI repeats on its fresh AMD64 image, alongside all prior gates and unchanged budgets.

[P36 source evidence](evidence/p36-qualification-2026-10-11.json) records observed qualification. Complete dependency initialization, network/socket preparation, service adoption, authenticated supply, upgrade/rollback, production recovery, expert isolation, reproduction, accessibility and release/value/customer acceptance remain open.
