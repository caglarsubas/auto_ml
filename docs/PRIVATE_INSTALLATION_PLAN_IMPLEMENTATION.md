# Offline private application installation plan — P34

The operator can render a reviewable application-layer plan from the complete verified P32 image set. P34 is partial D07: it binds the fixed API/worker/dispatcher and compiled TLS/frontend ingress to an explicit installation request, and records prerequisites for operator-managed PostgreSQL, cache and job broker. It does not initialize an installation or start services.

## Render

Save a nonsecret operator request outside the checkout:

```json
{
  "schema": "private_installation_request_v1",
  "installation_id": "pilot",
  "root": "/srv/declarai/pilot",
  "authority": "api.private.test:8443",
  "body_mib": 1,
  "bind_ip": "127.0.0.1",
  "database": {"name": "declarai", "user": "declarai_app"}
}
```

```sh
python scripts/private_installation_plan.py /approved/request.json \
  /approved/image-set /approved/new-plan \
  --expected-image-set-sha256 TRUSTED_OUTER_MANIFEST_DIGEST
docker compose -f /approved/new-plan/compose.json config --format json
```

Use the separately trusted image-set digest from the [handoff procedure](PRIVATE_IMAGE_SET_IMPLEMENTATION.md). All four archives are captured and verified before plan publication. The planner makes no Docker call or network request, reads no installation secret, and does not inspect/create the requested installation root. It requires only Python's standard library and the repository packaging scripts. Archive staging retains the P32 disk requirements and limits.

The request accepts exactly the displayed fields. Unknown options, duplicate JSON keys, symlink/FIFO/oversized request files, traversal/interpolation characters, noncanonical paths, system roots, wildcard/public bind addresses, privileged/reserved database names and unsupported values are rejected. Supported binds are explicit IPv4 loopback or RFC1918 addresses; IPv6 and public-edge configurations require later qualification. Paths are absolute Linux paths with a fixed child layout. These syntactic checks do not establish host ownership, certificate trust, storage encryption or database privileges.

The declared authority and upload limit must reproduce the verified ingress image's exact NGINX configuration hash, including its sealed frontend routes and CSP assets. A mismatched request cannot silently rewrite the image. Build and review a new ingress image/set for a different authority or limit. The published host port follows the declared authority; the ingress listens on container port 8443.

## Review artifacts and prerequisites

The new plan directory contains `request.json`, `compose.json`, `prerequisites.json`, the exact outer and ingress component manifests, and `manifest.json`. The command returns the plan manifest digest; retain it through a trusted channel for later verification. Each output file is SHA-256 bound, mode 0600, inside a 0700 directory. Existing observed destinations are rejected; completed plans publish through a staging-directory rename. Use a trusted, dedicated output parent. These files contain configuration and image identities, never secret values or generated credentials.

The Compose JSON specifies four separate resource-bounded services with exact local image IDs, `pull_policy: never`, UID/GID 10001, read-only roots, no capabilities/new privileges and bounded tmpfs. It retains the fixed image entrypoints. The API has one native WSGI worker and a dedicated socket volume; workers/dispatchers receive no socket or public port. Ingress receives only TLS files and the read-only socket. All secret binds are read-only, and all host binds disable automatic path creation. No source bind, Docker socket, arbitrary command, environment override, migration or knowledge indexing enters the plan.

Before any adoption, the operator must provision:

- Separate dedicated internal bridge networks `declarai-pilot-private` and `declarai-pilot-edge`, and `declarai-pilot-socket` with the recorded UID/mode. The API, worker and dispatcher use only the private service network; ingress uses only the edge network.
- `ROOT/secrets/app`: `django-key`, `app-password`, `job-broker-url`, `postgres-ca.crt`, `job-ca.crt`; and `ROOT/secrets/tls`: `tls.crt`, `tls.key`. Directory UID/GID 10001/mode 0700 and regular unlinked file UID/GID 10001/mode 0400 are prerequisites. Verify secret-manager delivery, TLS trust/validity/key pairing and names separately. The broker URL must select the dedicated authenticated TLS broker at `job-broker:6379`, with an approved logical database.
- Encrypted `ROOT/artifacts` owned by UID/GID 10001, mode 0700, with approved capacity, retention and coordinated backup policy.
- The recorded PostgreSQL 17 image at alias `postgres:5432`, and separately dedicated Redis 7 cache (`cache:6379`) and authenticated TLS job broker (`job-broker:6379`) using the recorded exact Redis image. The cache is reconstructible and reachable only within the private service network. Configure database server TLS, a non-superuser application role and approved explicit migrations. Dependency initialization, credentials, data volumes and supervision are not generated by this application-layer plan.
- Attributable account/project enrollment, host firewall, startup preflight and actual HTTPS/job/recovery qualification. Telemetry and external model providers are disabled in this initial plan; enabling them requires an approved egress configuration.

`docker compose config` checks interpretation only; it does not establish these prerequisites or qualify a deployment. Runtime startup still checks current migrations, real PostgreSQL TLS and the authenticated TLS broker, and fails closed when unavailable. This plan does not isolate expert Python.

## Qualification

`scripts/qualify_private_installation_plan.py` uses the real verified four-image set and Docker Compose's actual parser, and retains safe rendered configuration. Compose 2 omits its false `create_host_path` field from normalized JSON; the comparison accepts that exact representation while rejecting true or other mount changes. A real owned, networkless container-creation attempt must fail specifically because a bound directory is missing, without creating that directory. The UUID container is never started and is cleaned up; no operator installation, network or volume is adopted. Hosted CI performs this after the existing empty-slot/repeated import and before the unchanged private TLS/browser/job/recovery/full-PostgreSQL fixture. The same workflow still has six jobs. Unit checks exercise actual synthetic archive verification and input/tampering/ingress/overwrite boundaries. [P34 source evidence](evidence/p34-qualification-2026-10-11.json) records the qualification.

Complete installation and host prerequisite verification, dependency initialization, authenticated supply, upgrade/rollback, live/machine-loss recovery, training/search migration, comprehensive egress/retention, gVisor expert isolation, independent refit reproduction, accessibility and release/value/customer acceptance remain open. A rendered plan is separate from an implemented, tested or adopted installation.
