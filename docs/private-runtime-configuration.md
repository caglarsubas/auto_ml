# Explicit runtime configuration (P16–P17)

P16 adds a fail-closed private settings profile and PostgreSQL metadata support.
It is partial D06/D07 implementation. The bundled Compose/live-reload stack is
development only. A private settings profile does not qualify a production
deployment, authorize project access, or isolate expert Python.

## Profiles and startup

`DECLARAI_RUNTIME_PROFILE` accepts `development` (the compatibility default) or
`private`. Invalid configuration raises `ImproperlyConfigured` during settings
import, before requests or migrations. Errors name the field without printing
secret values. There is no implicit SQLite fallback when PostgreSQL is requested.

Development retains local HTTP origins, SQLite and debug output. P17 requires a
current authority revision for browser sessions in both profiles; pre-migration
sessions must sign in again. Set `DECLARAI_DB_ENGINE=postgresql` explicitly to test PostgreSQL in
development. Supplying database fields while selecting SQLite blocks startup.
`docker/backend-entrypoint.sh` rejects every profile except development before
migrating, indexing or starting Django's live-reload server; Compose forwards the
selected profile. Do not use that entrypoint for a private installation.

Private configuration requires the following inputs:

| Variable | Contract |
| --- | --- |
| `DJANGO_SECRET_KEY` or `DJANGO_SECRET_KEY_FILE` | Distinct key, at least 50 characters and five distinct characters; no repository development key or `django-insecure-` prefix. Generate a random key through the installation's secret manager. |
| `DJANGO_DEBUG` | Defaults to `false`; `true` is rejected. |
| `DJANGO_ALLOWED_HOSTS` | Explicit comma-separated DNS names, IPv4 or bracketed IPv6 literals; no wildcard, URL, port or leading-dot domain. |
| `DECLARAI_ALLOWED_ORIGINS` | Explicit HTTPS origins for both CORS and CSRF; ports are permitted, credentials/paths/queries/wildcards are rejected. |
| `DECLARAI_MEDIA_ROOT` | Existing absolute artifact directory; root `/`, relative paths and a symlink at the selected root are rejected. Ancestor ownership, filesystem encryption, mounts and access permissions remain installation responsibilities. |
| `DECLARAI_DB_ENGINE` | Defaults to `postgresql`; private SQLite is rejected. |
| `DECLARAI_DB_NAME`, `DECLARAI_DB_USER`, `DECLARAI_DB_HOST` | Explicit database, application role and one hostname/IP; no Unix-socket path or multi-host connection string. Use the name appearing in the server certificate. Bracketed IPv6 is normalized for libpq. |
| `DECLARAI_DB_PASSWORD` or `DECLARAI_DB_PASSWORD_FILE` | Required nonempty single-line password. |
| `DECLARAI_DB_PORT` | Integer 1–65535; default 5432. |
| `DECLARAI_DB_SSLMODE` | Defaults to and requires `verify-full`; weaker modes are rejected. |
| `DECLARAI_DB_SSLROOTCERT` | Existing absolute CA certificate file; the driver verifies trust and server hostname during connection. |

Secrets accept a direct value **or** its `_FILE` source, never both. Secret files
must be readable regular UTF-8 files, at most 4096 bytes, without embedded NUL or
line breaks; trailing line endings are accepted. Symlink secret files are
rejected on the supported Linux profile. Protect mounted secrets with filesystem
permissions and restrict environment access. Configuration validates shape,
not secret entropy, database reachability, CA authenticity or storage durability.

Private mode enables HTTPS redirects, secure session/CSRF cookies and HSTS
(default 3600 seconds). `DJANGO_HSTS_SECONDS` permits 0–31536000;
`DJANGO_HSTS_INCLUDE_SUBDOMAINS` and `DJANGO_HSTS_PRELOAD` default to false.
Choose domain-wide/preload policy only after reviewing the installation's HTTPS
coverage. `DJANGO_TRUST_PROXY_TLS` defaults to false. Enable it only behind a
trusted proxy that strips client-supplied `X-Forwarded-Proto` and supplies its own
HTTPS value; prevent clients from reaching the application directly. Other
boolean inputs accept only `true` or `false`.

PostgreSQL uses psycopg 3, connection health checks, a ten-second connection timeout
and 60-second connection reuse. Provision a dedicated application role and
database; the runtime does not create roles, alter grants, or silently elevate
privileges. Run schema migrations under an approved installation procedure.
No application schema or existing SQLite database is modified by selecting a
profile; transferring existing metadata requires a separately qualified migration.

These defaults follow Django's [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
and PostgreSQL's [certificate and hostname verification](https://www.postgresql.org/docs/17/libpq-ssl.html).

## Repeatable qualification

With Docker, openssl, Python 3.12 and the public backend requirements installed:

```sh
python scripts/qualify_postgres_fixture.py
```

An optional `--runner-image` uses a local qualified core image instead of host
Python. The runner owns randomly named PostgreSQL 17/Redis containers and a
temporary fixture directory; it never accepts a production database name or
reads an existing installation. Application writes/migrations use a non-superuser
database owner. Only the separate pytest role has `CREATEDB` for its disposable
test database. Fixture secrets and the session-bearing state remain outside
the checkout and are deleted with the containers on normal exit or failure.
Ignored `test-reports/postgresql/` contains only check logs, coverage and a safe
summary; it must never include database dumps or session fixture state.

The fixture verifies private settings through Django's real middleware/test client,
server TLS negotiation, certificate/hostname rejection, PostgreSQL migrations,
session/CSRF enforcement and JSON/UUID metadata persistence. It restarts the
database and restores a **quiescent synthetic** database snapshot plus matching
artifact copy, then checks session validity, pipeline state, receipts, grants,
approval state and artifact hashes, including the authentication receipt and
session authority revision. P17 adds five-process source/principal admission and
five-process retry-safe revocation, revoked-session denial, unaffected-user access
and fresh-session retry checks. See [authentication governance](AUTHENTICATION_GOVERNANCE.md)
for configuration, operator commands and evidence limits. The full existing marked backend suite runs
against PostgreSQL with the same assertions, skip budget and coverage gate as
SQLite. CI runs this as an additional job; the five existing jobs remain.

This does not test a real TLS ingress/browser installation, online coordinated
restore, encrypted storage, SQLite-to-PostgreSQL transfer, backup retention,
upgrade/rollback, interrupted publication or worker/broker recovery. Celery jobs,
bounded concurrency/cancellation, project roles, egress/retention, offline locked
packaging, expert isolation and independent reproduction remain open, as do all
technical release and customer gates. Inspect deployment checks, including HSTS
policy warnings, when qualifying an actual private installation.
