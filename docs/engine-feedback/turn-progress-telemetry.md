# Feature request: per-request progress telemetry so clients can show what the model is doing

**Status:** Open — feature request, no bug. Nothing is broken; the information exists inside the engine and never reaches the caller.
**Audience:** `llm-inference-engine` team
**From:** DeclarAI (POC customer)
**Date filed:** 2026-08-24
**Engine commit read at filing:** `318468f` on `main`
**Severity:** P2 — no correctness impact. It blocks a UX capability (honest progress reporting) that we can currently only deliver for the half of a turn we own.

---

## What we are trying to do

DeclarAI's AI Assistant panel used to render one three-dot typing indicator for a whole chat turn — 5 to 60 seconds of silence with no signal about whether anything was happening. We have just replaced that with a Claude-Code-style step list: one row per phase, live, with per-phase durations.

We can narrate everything that happens **on our side of the wire**:

```
· Reading your question          — about current results     402ms
· Gathering pipeline context     — 6 cached artifacts        301ms
· Decided what to look up        — 1 lookup                    1.2s
· Reading data-quality summary   — 2841 chars                 501ms
● Reviewing results              — nemotron-3-nano:30b
```

The rows we cannot fill in are the ones inside `POST /v1/chat/completions`. From the client, the entire span between "request sent" and "first byte back" is one opaque block — and on a busy engine that block is usually the **majority of the turn**. We currently label it `Thinking`, which is a guess: the request may be sitting in the tenant queue, the model may not be resident yet, or the model may genuinely be generating.

That guess is the problem. "Thinking" while a request is actually queued behind three other tenants is a misleading UI, and it is the single case where users most want to know it is queued (so they can wait rather than retry, which makes the queue worse).

## What the engine already knows and does not tell us

We read the engine source at `318468f`. Every number we want is already computed — it just terminates in OTEL spans and Prometheus histograms rather than on the response:

| Signal | Where it lives today | Reaches the client? |
|---|---|---|
| Queue wait for **this** request | `SchedulerLease.wait_ms` (`scheduler.py`) | No — only `scheduler_span_attrs()` (`api/_scheduling.py:35`) |
| Queue depth at submit | `SchedulerLease.queue_depth_at_submit` / `tenant_queue_depth_at_submit` | No — same span-only path |
| In-flight / queued totals | `TenantScheduler.snapshot()` → `api/metrics.py:153` | Aggregate only, not per request |
| Time to first token | `genai_metrics.record_time_to_first_token()` (`genai_metrics.py:141`) | Aggregate histogram only |
| Reasoning vs answer text | `reasoning_content` (`schemas.py:106`, `:452`), `StreamNormalizer` | Yes in the payload, but only at the end on the blocking path |

Note the asymmetry this creates for us specifically: we call the engine through the OpenAI SDK so that prometa-sdk auto-instrumentation picks the call up (see `ai_assistant/model_registry.py::call_engine`). Those span attributes land in **our** trace backend after the fact — which is great for post-hoc analysis and useless for a live UI. We need the same facts in-band, while the request is in flight.

## What we are asking for

Ordered by value-to-us over effort-for-you. (1) and (2) are the ones that matter; (3)–(5) are opportunistic.

### 1. Per-request scheduler telemetry on the response — P1, small

Put the lease numbers on the wire. Response headers are the least invasive option and don't touch the OpenAI-compatible body schema:

```
X-Engine-Queue-Wait-Ms: 4120
X-Engine-Queue-Depth: 3
X-Engine-Tenant-Queue-Depth: 1
X-Engine-Resource: ollama:nemotron-3-nano:30b
```

Equivalently, a non-standard `engine` object alongside `usage` in the JSON body would work for us — whichever you prefer to support long-term. The data is already on the `SchedulerLease` at the point the response is assembled, so this should be close to plumbing.

Even on the blocking path this is worth having: it lets us render an honest **retrospective** row ("waited 4.1s in queue") and, over time, lets us set expectations before the next request.

### 2. A pre-first-token status event on the streaming path — P1, medium

This is the one that actually fixes the live UI. On `stream: true`, emit one or more status events **before** the first content delta:

```
event: status
data: {"phase": "queued", "queue_depth": 3, "tenant_queue_depth": 1, "estimated_wait_ms": 4000}

event: status
data: {"phase": "admitted", "queue_wait_ms": 4120}

event: status
data: {"phase": "prefill", "prompt_tokens": 5312}

event: status
data: {"phase": "generating"}

data: {"choices":[{"delta":{"content":"The"}}], ...}
```

Phases we would render distinctly: `queued`, `admitted`, `loading_model`, `prefill`, `generating`. Anything you don't have a cheap signal for, omit — a client that sees only `admitted` and `generating` still shows far more than we can today.

Two constraints from our side:

- Please make it **opt-in** (a request field such as `stream_status: true`, or an `Accept` hint) or otherwise inert to clients that don't understand it. Vanilla OpenAI SDK consumers must not break on an unknown SSE event type. If a separate event type is a problem, a chunk with an empty `choices` array and an `engine` object would also work.
- The status events must be flushed immediately, not coalesced with the first content chunk — the whole point is that they arrive during the wait.

### 3. Distinguish "queued" from "model not resident" — P2

Right now a cold model load and a busy queue are the same long silence to us, but they mean different things to a user: one is "someone else is ahead of you", the other is "first request after idle, this one is slow, the next won't be". A `loading_model` phase (or a `model_resident: false` flag on the first status event) is enough for us to say so.

### 4. Confirm reasoning deltas are streamable and labelled — P2

`reasoning_content` exists in the schema and `StreamNormalizer` already tracks a reasoning state with `expects_reasoning_prelude`. Can you confirm that on the streaming path reasoning tokens arrive as `delta.reasoning_content` (distinct from `delta.content`) throughout, not just at the end?

If so we can show a live "Thinking — 340 tokens" row for reasoning-family models **without** ever rendering the chain-of-thought — which is the good version of the behaviour we had to defend against client-side in `auto_ml` v2.44.0 (see [`nemotron-cot-leak-blocking-normalizer.md`](nemotron-cot-leak-blocking-normalizer.md)).

### 5. Keep the queue-rejection shape, and add an ETA if it's cheap — P3

`TenantQueueFullError` → 429 with `queue_depth` + `Retry-After`, and `TenantQueueTimeoutError` → 503, are already well-shaped and we intend to render them directly ("the engine is at capacity, N requests ahead, retry in Ns"). Please treat that payload shape as a public contract. An `estimated_wait_ms` on the 429 would let us show a countdown instead of a static retry hint — nice to have, not required.

## What we have already built, so you don't over-build

We are not asking the engine to model our chat turn. DeclarAI's turn is a multi-phase workflow — intent classification, context assembly, knowledge-bank retrieval, N tool-calling rounds, synthesis — and **all** of that orchestration and its narration lives on our side (`backend/ai_assistant/progress.py`, streamed to the browser as NDJSON over our own endpoint).

The engine's job in that picture is exactly one row per LLM round. All we need is for that row to be able to say which of "queued", "loading", "prefilling", "generating" it is in, instead of a flat "Thinking". Anything beyond the per-request signals listed above is our problem, not yours.

## Impact if this stays as-is

Not a blocker. We ship the step list without it and label the engine call `Thinking`. The cost is that on a loaded engine the longest, least-explained part of every turn stays unexplained — and that is precisely when users retry, which compounds the queue pressure that caused the wait. Item (1) alone (headers, small change) already lets us report the wait retrospectively and is the highest value-per-line-changed of anything here.

Happy to test against a branch — we can reproduce multi-tenant queue pressure locally and will report what the UI does with whatever you emit.
