# P31 — Compiled same-origin private frontend

The fixed TLS ingress can include compiled Angular assets. Browsers use the installation's HTTPS origin for UI, `/api/` and protected `/media/`. Development/legacy production environment defaults are unchanged. This is partial D06/D07/D12; technical release and customer gates remain open.

## Build and inspect

Use Node 24 and separately acquire locked dependencies with `npm --prefix frontend ci`. Prepare a fresh package and fresh owned ingress tag:

```sh
python scripts/private_frontend_package.py /approved/new-frontend-package \
  --dependencies frontend/node_modules
python scripts/private_ingress_package.py build \
  --base-image sha256:<exact-trusted-native-nginx-image-id> \
  --tag declarai-private-ingress:<fresh-owned-tag> \
  --authority models.customer.example:8443 \
  --frontend /approved/new-frontend-package
```

Only Git-indexed application/configuration files and approved web assets enter a fresh temporary source snapshot. Source links and budgets are checked; tests, installation files, arbitrary JSON/Python assets and old `Zone.Identifier` download metadata are excluded. The fixed `production,private` AOT build disables analytics, source maps and automatic font downloads while preserving production bundle/style budgets. The explicitly supplied trusted dependency directory is linked only into this build snapshot; four compiler versions must match the lockfile. The tool performs no npm installation/download.

The manifest records original source hashes, compiler/Node versions, build overrides, asset lengths/hashes and `/api/`. Font and generated dependency license notices travel in the published package. The ingress verifies and copies bytes into its owned context rather than passing the caller's directory to Docker. Changed/missing/extra files, links, source maps, hidden files, reserved API/media/admin namespaces and configuration-injection names stop packaging. The frontend manifest remains build evidence and is not served. Image permissions are independent of the build operator's umask: fixed config/start files are readable, their parent is traversable, and the unprivileged server owns asset directories/files while the runtime root remains read-only.

Receipts identify a build; they do not authenticate a supplier or prove that a manually modified manifest originated from the claimed source. The operator trusts the compiler/dependency filesystem and validates the immutable native image through an approved channel. Binary-identical cross-platform builds and multi-image offline import remain unqualified.

## Serving and installation

The existing private Compose ingress accepts the resulting exact image and approved certificate/key directory and edge network. Configure the API's allowed host and approved HTTPS origin for the same public authority, including a nonstandard port. Existing PostgreSQL/broker TLS, socket, secrets and artifact settings apply. Runtime uses no Node/development server, source mount, template substitution, public download or asset CDN.

Only compiled asset paths and current Angular routes have exact locations. [NGINX `try_files`](https://nginx.org/en/docs/http/ngx_http_core_module.html#try_files) serves the packaged file or returns 404. Known routes return the entrypoint; unknown routes/assets, metadata, admin, API errors and media never receive an application-page fallback. UI/assets accept GET/HEAD with appropriate MIME types, `no-store`, HSTS, nosniff, frame denial and no-referrer. CSP permits only the exact compiled bundle URLs as scripts, same-origin connections/fonts, Angular/Plotly inline styles and data/blob images/workers. Protected media retains its MIME type and authorization but is delivered as an attachment with document sandboxing. A data artifact cannot become a UI script through the shared origin. External connections, inline/evaluated scripts, objects and embedding are disallowed. Server-side inference/embedding/telemetry/log egress governance remains open.

The session interceptor resolves relative API and absolute artifact URLs before checking origin/path. Private requests retain cookies/CSRF; external origins and lookalike paths receive no added credentials. Django project/data authorization remains authoritative for API/media.

## Qualification and limits

Add `--private-frontend-browser` to the existing disposable PostgreSQL fixture alongside exact `--private-api-image` and `--private-ingress-image` values. Install Node 24, locked frontend dependencies and Playwright Chromium first. The fixture owns a random loopback TLS binding and separate edge bridge; Docker does not publish ports from its internal bridge. Ingress/browser never join the API's private-service network. Owned certificates, volumes, containers and networks are removed.

Chromium pins only the generated synthetic leaf SPKI; no global verification disable or `ignoreHTTPSErrors` is used. The raw HTTPS probe independently verifies CA/name and rejects wrong CA/SNI/Host. The browser checks session/CSRF, secure cookies, project selection/reload, compiled deep links, local fonts, pipeline creation/upload, exact protected download bytes, logout/revoked access, absent metadata/admin/assets/API fallback, and zero external requests, runtime errors or unexpected CSP violations; one deliberate media-script attempt must produce the expected CSP denial. Existing buffering/chunking/limits/startup and natural lease/scoring recovery checks retain their budgets. All six CI jobs remain.

The first port-binding fixture failed before browser execution because the internal bridge did not publish its loopback port. The corrected owned edge fixture and final packaged image are qualified separately. A separate actual umask-077 build reproduced unreadable config/start files before repair; an intermediate COPY mode also removed parent-directory traversal. The final image passes reads of all50 assets as UID10001 on a read-only root. CI builds under umask077 and runs the complete native HTTPS/browser/metadata fixture on that exact image. Application assertions, retries, timeouts, skips and coverage budgets remain unchanged. [P31 evidence](evidence/p31-qualification-2026-10-11.json) records source/image qualification.

Complete restricted-network installation with all images, authenticated software supply, upgrades/rollback and production recovery, client-source attribution, comprehensive egress/retention, durable training/search, gVisor expert execution, independent refit/assessment reproduction, comprehensive accessibility and every release/value/customer gate remain open. This bounded browser flow does not qualify every modeling/reviewer screen under the private CSP or establish capacity/customer acceptance. The user's running installation is unchanged.

[P32 image-set handoff](PRIVATE_IMAGE_SET_IMPLEMENTATION.md) combines the API, compiled ingress and prepared native database/broker images under one externally trusted digest. It adds verified offline import; complete installation and service adoption remain separate qualifications.
