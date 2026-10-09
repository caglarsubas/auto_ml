# Authentication audit and browser revocation (P17)

P17 implements part of D06: shared password-login admission, durable authentication
receipts, revision-bound browser sessions and a retry-safe installation-operator
revocation command. It does not complete project authorization or qualify a
private release. Existing sessions without a recorded revision must sign in again
after the additive migration; their missing provenance is not reconstructed.

## Shared admission and evidence

The API and Django admin use `GovernedModelBackend`. Before password work, a
database transaction reserves source and source/username budgets and records an
admitted attempt. PostgreSQL row locks share these budgets across application
processes. SQLite is for development; concurrent locking/capacity is not qualified.
An admission/audit outage blocks API sign-in with HTTP 503. Wrong, inactive and
unknown accounts return the same credential error. Throttled API requests return
429 with `Retry-After`; admin follows Django's generic unsuccessful-login form.

| Environment variable | Default | Accepted range |
| --- | --- | --- |
| `DECLARAI_AUTH_LOGIN_WINDOW_SECONDS` | 60 | 1–86400 |
| `DECLARAI_AUTH_LOGIN_PAIR_LIMIT` | 10 | 1–1000 |
| `DECLARAI_AUTH_LOGIN_SOURCE_LIMIT` | 100 | 1–10000 |

Invalid values block settings import. Source means `REMOTE_ADDR`; client-supplied
`X-Forwarded-For` is ignored. Behind a proxy, the source budget may cover many
users. Configure limits for the installation's actual ingress. Successful
credential validation resets its pair budget; the source budget remains bounded.
Source denial allocates no new username buckets. Limits govern admission to
password work, not request size/connection rate at ingress.

`AuthenticationEvent` distinguishes these facts:

- API `login`: an admitted attempt begins `pending`; rejection becomes `denied`.
  `completed` means the current active account/password, session save and audit
  completion committed together. An interrupted attempt can remain `pending`;
  it is not evidence of a successful or rejected login.
- Admin `credentials_validated`: the password backend validated credentials.
  This does not assert staff authorization or a delivered browser session.
- `session_bound`: Django's login signal bound a revision in the session. The
  API owns its stronger login receipt; other framework logins use this binding
  event. A binding alone does not prove subsequent session persistence/cookie
  delivery. Login/logout behavior follows Django's [authentication lifecycle](https://docs.djangoproject.com/en/5.2/topics/auth/default/).
- `logout` and `session_rejected`: the application recorded logout or rejected
  unbound/revoked authority. An audit-write failure returns 503 before a protected
  handler runs. A failed explicit logout does not claim completion; retry after
  recovery. Not every external password/account change produces a known-actor
  receipt: Django can invalidate/flush a session before this middleware.
- `sessions_revoked`: an installation operator committed one revocation, its
  asserted label, subject snapshot, new revision and unused-approval cancellation.

Records contain HMAC source/principal keys, known-account snapshots and reason
codes, not passwords, presented unknown usernames, raw source addresses, session
identifiers, cookies or CSRF/bearer values. The first throttled attempt per bucket
window produces a denial event; repeat denials increment the current bucket's
counter. Window reset does not preserve a complete per-attempt denial history.
Actor deletion retains the recorded snapshot with a null actor reference. This
ordinary database audit store is not tamper-proof evidence. Retention, deletion,
access controls and audit export policy remain separate D06 work.

## Installation-operator revocation

Run the command with the installation's configured metadata credentials and a
new UUID. Retry the exact same operation with the same UUID:

```sh
python backend/manage.py revoke_web_sessions \
  --user exact-existing-username \
  --request-id 0259f4bb-8662-4a70-a6b3-2d4621264abc \
  --operator-label installation-ticket-123
```

The command rotates the account's browser revision and cancels its `prepared` or
`approved` typed-action receipts in one transaction. JSON output identifies the
audit event, subject, cancellation count, deactivation choice and replay status.
It contains no session credentials. `--operator-label` is an assertion by an
operator with database/runtime access, **not an authenticated human identity**.
The command is not a public browser/MCP API or a developer/reviewer/admin role
system. Labels permit 1–100 letters, digits, dots, underscores, @ or hyphens.

Old sessions are rejected on their next request, including protected REST and
artifact access; browsers return to sign-in when authentication is checked.
Another account's sessions remain valid. A fresh login receives the new revision.
A retry returns the original receipt and does not revoke that fresh session.
Reusing the UUID with a changed subject, label or deactivation choice fails without
committing another operation. Database failure rolls back authority changes and
cancellations; retry with the same UUID.

Add `--deactivate` to block future password sign-in and the currently configured
local MCP actor's active-account check. Browser revocation alone does not revoke
MCP dataset grants, process scopes or an external identity provider. Reactivation,
if appropriate, is an independent authorized installation action.

Typed approvals include the recorded authority revision. Revocation followed by
re-login cannot reuse an old proposal. Pending legacy proposals without this
binding must be prepared/reviewed again. Dispatching or finished receipts remain
inspectable. Revocation does not interrupt an already-authorized handler/job;
an action reserved before revocation can finish. Durable worker cancellation and
execution reconciliation remain open.

## Qualification and remaining gates

`python scripts/qualify_postgres_fixture.py` owns a disposable TLS PostgreSQL/Redis
installation and checks migrations, private middleware, session/audit persistence,
restart and a quiescent matching database/artifact restore. Its identity check
uses five independent Python processes per budget and five concurrent revocation
commands. The marked backend suite runs against PostgreSQL at the existing
coverage/skip gates. The fixture never targets an existing installation.

The [source qualification record](evidence/p17-qualification-2026-10-09.json)
separately records SQLite, real development-browser checks and exact source hashes.
CI status belongs to the PR's exact head. These checks do not establish live TLS
ingress, project roles, SSO/MFA enrollment, egress/retention, adversarial full
deployment security, encrypted/offline packaging, coordinated online recovery,
expert-code isolation, independent reproduction or customer acceptance. All
technical release and customer gates remain open.

P18 adds a separate [project authorization boundary](PROJECT_AUTHORIZATION_IMPLEMENTATION.md).
Authentication receipts remain distinct from project membership, organizational
review, production approval and release qualification.
