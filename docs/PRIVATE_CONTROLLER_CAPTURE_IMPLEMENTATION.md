# Consistent stored controller capture (P52)

The Linux dependency controller's stored-file reader now compares two bounded reads through the same descriptor and complete identity, size, ownership, mode, link and timestamp metadata. It also rechecks the no-ACL requirement after reading. Previously one read plus size/timestamps could accept changed bytes, permissions, ownership, links or an extended ACL when timestamp precision concealed the change.

Existing caller-specified UID/GID/mode/size limits, final-symlink refusal, regular/single-link requirements, pinned parent descriptors, trusted-directory checks, controller locks and immutable publication remain. The reader serves prepared configuration and stored initialization, startup, schema and adoption evidence; this change does not rewrite them, rotate credentials or recreate services.

Thirteen new cases cover exact stored bytes, six inter-read faults with coarse timestamps, and qualification scope refusal. All six fault cases fail against the preceding reader. Unit ownership snapshots are simulated; the owned Linux reader component additionally changes real UID/GID and installs a zero-extra-access POSIX ACL that preserves mode 0600. A local tmpfs lacked ACL support, so that failed result is retained and the component was rerun successfully on an owned ACL-capable volume. The container has only CHOWN capability for the owned identity faults, no network, read-only source and bounded resources. It qualifies the reader component, not the complete host installation.

Fresh Linux CI runs the same six faults on temporary copies beside its owned fixture root after application adoption. Installed configuration and receipts are untouched; all previous CA/TLS, authentication, recovery, schema/account, image-binding and cleanup checks remain mandatory.

These checks establish observed consistency during capture, not atomicity against arbitrary authorized writers or an atomic snapshot across files. Trusted directory/ACL custody and controller locks remain necessary. Delivery-file readers are the successor packet. Complete secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/customer gates remain open.

Local source receipts: [P52 qualification](evidence/p52-qualification-2026-10-13.json). Complete exact-head all-six CI and separate main receipts remain required before adoption claims.
