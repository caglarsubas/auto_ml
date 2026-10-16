# Private broker authentication (P75)

Private broker configuration required TLS but accepted URLs with no password.
An owned TLS-only Redis fixture with authentication disabled demonstrated that
the previous dependency-readiness client could connect and return a successful
ping. Transport encryption alone therefore did not establish the required
credentialed broker connection.

Private job configuration now requires a nonempty password before capturing
trust or constructing a network client. Default-user passwords and named Redis
ACL users are supported. Usernames and passwords must use valid percent escapes
and strict UTF-8 without ASCII control characters. Valid encoded reserved
characters, Unicode and spaces retain their meaning across Kombu and dependency
readiness. Rejections use the static `private_broker_authentication_required`
configuration error without connection or credential values. Protected-file and
direct-value configuration use the same check. Development behavior is preserved.

The guard does not establish a server's password strength, ACL scope, rotation
policy or credential custody. Existing fixed installations retain their stronger
provisioning rules and actual authenticated TLS checks. No installed secret,
server ACL, saved plan, execution budget or workflow is changed.

Thirty-two new cases exercise rejection before trust/network construction,
credential parity between Kombu and readiness, protected files and development
compatibility. The same owned TLS-only unauthenticated broker is accepted by the
predecessor and blocked by the new client. It exposes no host ports and is
removed with its owned network and temporary key material. Existing complete
private qualification remains required for live authenticated positives, wrong
credentials/CA/hostname, restart/recovery, exact images, schema/accounts/adoption
and HTTPS. Full source tests and exact PR/main CI are separate evidence states.

D07 remains in progress. Durable search, lifecycle/upgrade/rollback/restore,
expert isolation and release/customer acceptance remain open.
