# Managed broker trust and replay through restart (P47)

P47 adds bounded qualification of the P46 private broker transport across an actual restart of the managed dependency. It leaves production transport, task execution and model/scoring behavior unchanged.

The fresh Linux fixture verifies its generated `/srv/declarai-p37-UUID/installation` scope, current dependency preparation, all active application profiles and exact broker profile before interruption. A helper in the already adopted sealed API creates its actual private Celery connection, captures the channel/client/pool and CA data, and publishes one unique synthetic JSON payload without retry. Only the validated broker is stopped. The same client must refuse access while unavailable, then reconnect after the same broker is restarted and current dependency readiness passes. Its pool and CA data remain unchanged; the AOF-backed queue yields the payload once and is deleted by its owner.

The controller requires identical dependency IDs and byte-preserved startup receipt. Actual API, worker and dispatcher containers rerun metadata/broker/cache/migration/non-elevated-role preflight. Repeat admission requires the same four application IDs and the existing HTTPS check. Scope refusals precede file or container access; helper handshakes are bounded, and the existing owner cleans up only its resources.

This proves helper transport/pool behavior, AOF replay, current role preflight and same-ID readmission in the owned fixture. It does not prove a continuing customer task during outage, complete production recovery, future health or an upgrade/rollback policy. Existing native task/broker-loss/outbox recovery, duplicate delivery, scientific scoring replay, cache recovery, schema/accounts/HTTPS, full metadata matrices and browser qualification remain required. No timeout, skip, coverage or retry budgets are changed. D07 and release/customer gates remain open.

The preceding broker trust PR and the independent main run are verified separately. Local ARM component prototypes are retained as component evidence only; actual Linux-root/adopted-role receipts are required before merge.
