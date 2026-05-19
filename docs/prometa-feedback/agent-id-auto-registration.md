# Design feedback: auto-register Agents on first sighting (mirror Tool registration)

**Audience:** Prometa platform / SDK team
**From:** DeclarAI (POC customer, `solution_id=sol_declarai`)
**Date:** 2026-05-19
**SDK version observed:** `prometa-sdk` 0.7.0
**Severity:** Onboarding friction + silent correctness footgun

---

## TL;DR

`agent_id` is the only customer-facing identifier in the Prometa SDK that
follows a *server-assigned-UUID* contract. Every other identifier
(`solution_id`, `agent_name`, `tool name`) follows a *customer-owned-slug*
contract, and at least one of them (`tool name`) is **already auto-registered
server-side on first sighting**. The asymmetry creates an onboarding cliff and
a silent platform-side join bug for any customer who doesn't notice the
0.7.0 `UserWarning`.

**Proposal:** treat `agent_id` the same way you treat tool names — auto-register
`(orgId, solutionId, agent_name)` on first sighting, return the assigned UUID
through the OTLP response (or expose it via `GET /api/v1/agents`), and stop
asking customers to copy-paste UUIDs from the platform UI into their `.env`.

---

## Background: how DeclarAI hit this

DeclarAI ships AI assistant traces to Prometa staging via `prometa-sdk`. We
discovered (via the new 0.7.0 `UserWarning`) that since our integration
landed in **v2.18.0 about a month ago**, every backend container restart was
generating a fresh random per-process `agent_id`:

```python
# pre-0.7.0 SDK behaviour
self.agent_id = agent_id or _new_id()   # _new_id() = uuid4().hex[:16]
```

We construct the client like every customer following the README quick-start:

```python
Prometa(
    endpoint=...,
    api_key=...,
    solution_id="sol_declarai",
    agent_name="declarai-assistant",
    stage="staging",
    # agent_id intentionally omitted — quick-start doesn't show it
)
```

**Result on the platform side:** every PG `Agent.id` ↔ ClickHouse
`prometa.agent.id` join silently returned empty for the
`declarai-assistant` agent. Lineage queries, AML scoring rollups, and
incident-to-trace lookups were all broken. **From the customer side it was
invisible** — traces appeared in Trace Explorer, the SDK didn't error, and we
had no way to know joins were failing without inspecting the platform
internals.

The 0.7.0 `UserWarning` surfaces this, which is a clear improvement. **But
the underlying design that requires the customer to know and copy-paste a
UUID is itself the issue.**

---

## The asymmetry

The SDK asks customers to provide three identifiers when constructing the
client. Each follows a different contract:

| Field | Example value | Contract | Validation in SDK |
|---|---|---|---|
| `solution_id` | `sol_declarai` | Customer-owned slug. Looks like a server-assigned ID (`sol_*` prefix), but the SDK accepts any string and the platform stores it as-is. | None |
| `agent_name` | `declarai-assistant` | Customer-owned display label. | None |
| `agent_id` | `06309e7ef7954b85` (fallback) or copy-pasted UUID | **Documented as** "your registered Agent UUID" — implying server-assigned. | None — typed `Optional[str]`, accepts any string |

The SDK's typing and validation tells the truth: `agent_id` is **just a
string** as far as the wire is concerned. The "UUID" framing is platform
convention surfaced through the warning text, not enforced by the SDK or by
the OTLP ingest.

---

## Existing precedent: Tool auto-registration

The 0.5.0 README (correlation-chain helpers section) describes
`set_tool_name` as:

> **Auto-registers a Tool row per `(orgId, solutionId, name)` triple on
> first sighting.**

This is exactly the right design — the customer provides a name, the
platform owns the lifecycle of the registry row (creates on first sighting,
assigns the UUID, dedupes by tuple). **Customers never see a Tool UUID.**

There's no architectural reason Agents couldn't work the same way. They're
the same kind of entity: long-lived, identified by a `(solution, name)`
tuple, indexed for joins on the platform side.

---

## Customer-side impact today

For every Prometa customer following the quick-start, the current
`agent_id` design produces:

1. **Silent correctness bug** — random per-process IDs break PG↔CH joins
   for the affected agent. Customer has no way to detect this without
   platform-internal access.

2. **Onboarding friction** — the fix requires:
   - Logging into the Prometa UI
   - Navigating to the Agent registry
   - Finding the auto-created row (assuming the platform created one;
     unclear whether agents auto-register today)
   - Copying the UUID
   - Pasting into a `.env` file or deployment manifest
   - Repeating per environment (staging / prod / per-developer)

3. **Drift risk** — every developer on the team needs the same UUID. If
   someone runs locally without it, they emit traces under a random ID
   and pollute the registry with phantom rows.

4. **No validation** — the SDK accepts any string. A customer could
   set `PROMETA_AGENT_ID=foo`, the platform would dutifully ingest it,
   and the join query would fail silently.

DeclarAI's v2.34.0 ships with the env-var wiring, but the underlying
question stands: **why is the customer doing this work?**

---

## Proposal

Mirror the Tool registration model for Agents.

### SDK side (zero or near-zero change)

- `Prometa(...)` `agent_id` parameter becomes **fully optional with no
  warning**.
- If the customer supplies one, honour it (current behaviour) — useful for
  customers who *want* a stable client-controlled ID.
- If absent, do not generate a random fallback. Let the platform assign.
  The SDK can either:
  - **(a) Send traces with no `prometa.agent.id` attribute** and let the
    platform attach one at ingest based on `(orgId, solutionId, agent_name)`.
  - **(b) Hash a deterministic UUID5** from `(orgId, solutionId,
    agent_name)` so the same triple always produces the same id without
    coordination. (UUID5 is what the platform would compute server-side
    too, given the same inputs.)

Option (b) has the nice property that *both sides* can compute the canonical
ID independently, so even pre-registration traces join correctly.

### Platform side

- On first sighting of `(orgId, solutionId, agent_name)` in an OTLP trace,
  auto-create an Agent registry row using the deterministic UUID5 (or
  whatever scheme matches Tool registration).
- `GET /api/v1/agents` exposes the assigned UUID for customers who *want*
  to look it up (debugging, custom dashboards), but **the customer never
  needs to set it back into their config**.
- Cease the `UserWarning` once the platform reliably attaches IDs at ingest.

### Documentation

- Remove `agent_id` from the README quick-start. Customers should not
  encounter this concept on day one.
- Add a section *"Stable Agent IDs"* explaining the auto-registration
  semantics and the (rare) cases where pinning a custom `agent_id` makes
  sense (multi-process workers needing identical IDs before first ingest;
  cross-region replicated agents; testing).

---

## Why this matters beyond DeclarAI

Prometa's value proposition is **"observe agent behaviour without
instrumenting your code"** — at least for the OpenAI auto-instrumentation
path. The current `agent_id` design contradicts that: customers *must*
instrument their boot code (or env file) with platform-specific identifiers
to make the basic platform features work, and the failure mode is silent.

The fix is small, the pattern already exists for Tools, and it eliminates
an entire category of customer-visible config that no other OpenTelemetry-
adjacent platform requires.

---

## What DeclarAI is doing in the meantime

- **v2.34.0 (just shipped)** — wires `PROMETA_AGENT_ID` env-var support so
  we can set a stable id and silence the warning.
- **Considering** — switching `PROMETA_AGENT_ID` to a customer-owned slug
  (e.g. `declarai-assistant-prod`) instead of a copy-pasted UUID, on the
  basis that the SDK doesn't validate format and the slug is the natural
  customer-owned identifier shape. Would appreciate confirmation that the
  platform won't reject non-UUID strings.

Happy to discuss further or move this onto a public issue tracker.

— DeclarAI / `sol_declarai`
