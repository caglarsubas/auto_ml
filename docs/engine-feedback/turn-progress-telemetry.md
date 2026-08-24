# Feature request: per-request progress telemetry so clients can show what the model is doing

**Status:** RESOLVED for the asks that survived review (2026-08-24). Item 1 shipped in engine PR #107 and is consumed by DeclarAI; item 4 confirmed and pinned by engine tests. **Item 2 is withdrawn by us** — it was self-inconsistent with our own item 5. Item 3 is reshaped around a constraint we had wrong. Item 5 stands as a contract request.
**Audience:** `llm-inference-engine` team
**From:** DeclarAI (POC customer)
**Date filed:** 2026-08-24
**Engine commit read at filing:** `318468f` on `main`
**Engine commit at resolution:** `9921332` (#107) — see the re-read note below
**Severity:** P2 — no correctness impact. It blocked a UX capability (honest progress reporting) that we could only deliver for the half of a turn we own.

---

## Resolution (2026-08-24)

The engine team answered all five items. Summary first, detail per item below.

| # | Ask | Outcome |
|---|---|---|
| 1 | Per-request scheduler telemetry on the wire | **Shipped** (#107) — and better than asked on streams |
| 2 | Pre-first-token status events | **Withdrawn by us** — costs a response-lifecycle inversion that breaks item 5 |
| 3 | Distinguish queued from model-not-resident | **Reshaped** — needs a resident-models pre-check; our premise was wrong |
| 4 | Confirm reasoning deltas are streamable and labelled | **Confirmed**, with two caveats worth knowing |
| 5 | Keep the queue-rejection shape | Stands |

### A correction to this document's own premise

This doc was written against `318468f`. Two things it asserts were already stale or wrong by the time it was read:

- **`f798691` (#104) made `ollama_http` the primary backend, not the fallback.** That lands directly on item 3 — see below. We reviewed one commit behind that change and reasoned about a backend that was no longer the one in the path.
- The headers we asked for in item 1 then shipped in `9921332` (#107), which is *after* the commit this doc cites throughout. Anyone reading the "Where it lives today" table below should read it as **the state at `318468f`**, not current.

### 1. Shipped — and it does more than we asked on streams

Engine PR #107 puts the lease on the wire:

```
x-engine-queue-wait-ms: 4120
x-engine-queue-depth: 3
x-engine-tenant-queue-depth: 1
x-engine-resource: ollama_http:nemotron-3-nano:30b
```

We asked for this mainly as a retrospective signal. On `stream: true` it is better than that: admission completes before the response is constructed, so the headers flush **when the stream opens** — a streaming caller reads its queue wait *ahead of the first content delta*, which is the live signal item 2 was trying to buy.

Four contract rules came with it. They are not decoration; each one is a way to render a misleading number:

1. **They describe the admission that STARTED the response** — the first lease. Fallback and schema-repair retries are admitted again and that wait is *not* counted.
2. **Both depths count the request itself.** A lone caller sees `1`, not `0`. "Requests ahead of you" is `depth - 1`.
3. **A depth of `0` means the scheduler is disabled**, which is not the same as "nobody ahead of you".
4. **Absent, never zeroed.** A request that never reached the scheduler has no headers at all, so "did not queue" stays distinguishable from "queued for 0 ms".

**DeclarAI consumption (`auto_ml` v3.6.0).** `call_engine` captures the headers through an **httpx transport event hook** rather than the OpenAI SDK's `with_raw_response`. That is deliberate: we route engine traffic through the plain SDK method *specifically* so prometa-sdk's openai auto-instrumentation wraps it, and switching call paths to read a telemetry header would risk the `gen_ai.*` spans that are the entire reason for the indirection. All four rules are encoded in `parse_admission_headers` / `_admission_detail` and pinned by `tests/unit/test_ai_engine_admission.py`.

We call the engine in **blocking** mode, so for us the headers arrive with the completed response. That still converts the single most-unexplained stretch of a turn into an attributed one — the panel now reads `Thought it through — nemotron-3-nano:30b · queued 9.2s, 2 ahead` instead of a flat `Thinking`. Getting the *live* version means switching `call_engine` to streaming, which is ours to do, not yours.

### 2. Withdrawn — our ask contradicted our own item 5

The engine team's objection is correct and we should have caught it before filing.

Emitting `queued` / `admitted` status events **before** admission requires committing to a `200` and opening the response body before the scheduler has decided. But the scheduler is exactly what produces `TenantQueueFullError` → `429` and `TenantQueueTimeoutError` → `503` — the responses item 5 of this very document asks them to treat as a stable contract. Once the stream is open you cannot answer `503` any more; the rejection would have to be demoted into an in-band error frame, changing the status code a client sees for a queue rejection.

So items 2 and 5 could not both be satisfied. Between "narrate the queue wait live" and "a queue rejection is still an HTTP 503 with `Retry-After`", the status code is worth more: it is what every client — including SDK retry logic that never parses our SSE — keys off. **We withdraw item 2.** Item 1's stream-open headers already deliver most of what we wanted, without the inversion.

### 3. Reshaped — our premise was wrong

We asked for a `loading_model` phase assuming the engine knows when weights are resident. Since `f798691` made `ollama_http` the primary backend, that is not true in the path that matters: **`OllamaHttpAdapter.load()` never touches weights.** It validates the descriptor, binds the endpoint and model id, and constructs an `httpx.AsyncClient` — nothing more. Ollama loads weights lazily on the first `/api/chat`, so the adapter reporting `is_loaded` says only "we know where to send this", not "the model is in memory".

A truthful `loading_model` signal therefore needs a **resident-models pre-check** (ollama's `/api/ps` or equivalent) rather than a flag the adapter already has. That is a real feature with a real cost, not the small annotation we implied. We are not pressing for it: with item 1 shipped, a long wait with no queue depth behind it is already a strong hint of a cold load, and that is enough for our UI. Recording it here so the next person does not re-file it as "just expose the flag you have".

### 4. Confirmed — with two caveats we are acting on

Reasoning **does** stream incrementally as labelled `delta.reasoning_content` frames, not batched to the end, and engine tests now pin both that and the channel separation (no `<think>` markup on either side). Two caveats came with the confirmation:

- **The split is the engine's own parse, not a backend field.** Nothing in `StreamChunk` carries a reasoning channel; the engine infers it from a pre-opened `<think>` keyed off the model id via `_REASONING_MARKERS`. A reasoning model whose name misses those markers, or a backend that starts stripping thinking into a field of its own, silently delivers chain-of-thought as answer text. This is why our client-side `_looks_like_cot_leak` backstop in `ai_assistant/views.py` **stays** — it is the defence for exactly this failure mode, and we had been treating it as legacy scar tissue. It is not.
- **There is no reasoning token count.** Reasoning arrives as text deltas only and `usage` does not break it out, so a live "Thinking — N tokens" row would have to approximate client-side from frame content. Not worth a request; noting it so we do not design a UI around a number that does not exist.

### 5. Stands

No change requested beyond what this document already asks: treat the `429` / `503` queue-rejection payloads as a public contract. Item 2's withdrawal makes this strictly easier to honour.

---

## Original request (as filed, against `318468f`)

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
