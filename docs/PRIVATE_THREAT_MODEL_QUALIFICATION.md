# Sealed private deployment threat-model qualification

D06-T03 covers a synthetic single-organization installation using the shipped
Linux ARM64 image set, the sealed local data policy, TLS ingress, PostgreSQL,
and dedicated Redis broker and cache. The separately provisioned Linux gVisor
worker receives exact reviewer-approved feature projections through the
operator intake path.

Trust starts with the independently verified image-set digest, installation
administrator, managed host and storage, and the operator's review and key
custody. The exercise tests the effects of unauthenticated callers, unrelated
projects, revoked actors, tampered evidence, unavailable controls, and an
untrusted expert program within these boundaries.

| Threat | Exercise and required result |
| --- | --- |
| Installer accepts untrusted inputs or unsafe dependency authority | Create a fresh offline installation from exact images. Reject changed profile, elevated database authority, foreign catalog and invalid TLS without altering the managed state. Verify the dependency network, TLS ingress, service adoption and owned fixture cleanup. |
| Execution or artifact access crosses a project or role boundary | Complete synthetic training and scoring using installed services. Verify authorized access to the retained receipt and candidate. Deny unauthenticated access and access by an unrelated project or revoked actor. |
| Review persists despite loss of authority or integrity | Complete an independent assessment and clean offline refit. Verify exact receipt and report bindings, technical approval, and invalidation when the applicable authority or review state changes. Restrict protected outcomes to their approved custody path. |
| Local data leaves through provider features, raw logs or unmanaged artifacts | Exercise the sealed policy and inspect the denial receipt. Verify network confinement, retention of used evidence, and detection of modified audit history. |
| MCP sidesteps review or isolation | Exercise the actual SDK over stdio with current grants. Allow typed proposals and permitted reads. Refuse direct execution and unavailable job, review and protected artifact operations, including requests with legacy flags or forged approvals. |
| Expert code reaches unrelated data or publishes after a control fails | Run the retained gVisor hostile-code and fitted-state exercises. Verify partition and artifact binding, disabled egress, cleanup, cancellation and failure when runtime isolation is unavailable. |

MCP job receipt reads bind both the primary dataset and any related source
before loading the receipt. The single-dataset tool requires both to be
covered by its current grant. Reviewers can inspect authorized multi-dataset
receipts through the HTTP workflow, which checks authority for each dataset.

The installed profile, authenticated application checks, MCP protocol exercise,
and gVisor worker run against exact CI source. The delivery audit verifies the
PR and independent main runs, matching source and artifact hashes, and
original case, skip and native execution budgets. This qualification uses
synthetic records and preserves only the evidence required for review.

Customer operation requires approval of host encryption, network and
identity configuration, retention periods, backup key custody and the named
operator's installation. The independent reviewer exercise and governed
expert workflow integration have separate roadmap acceptance criteria.

See the [clean installation profile](PRIVATE_INSTALLATION_ACCEPTANCE.md),
[sealed policy procedure](PRIVATE_DATA_POLICY_IMPLEMENTATION.md),
[expert isolation and operator intake](PRIVATE_EXPERT_WORKER.md), and
[independent review workflow](INDEPENDENT_REVIEW_IMPLEMENTATION.md).
