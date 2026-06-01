# Bug report: `n_ctx=8192` is too small for reasoning-family chat — long answers truncate mid-render (`finish_reason="length"`)

**Status:** Open — diagnosed end-to-end via live engine probes + engine config read.
**Audience:** `llm-inference-engine` team
**From:** DeclarAI (POC customer)
**Date filed:** 2026-05-30
**Engine at filing:** native build, `uvicorn inference_engine.main:app` on `127.0.0.1:8080` (PID 1603), `llama_cpp` backend, `N_CTX=8192` (from `.env` / `config.py:51` default).
**Model:** `nemotron-3-nano:30b` (`reasoning: true`, `thinking: true`, `thinking_level: "med"`, `backend: llama_cpp`) — representative of the reasoning/thinking family.
**Severity:** P2 — every sufficiently long structured answer from a reasoning-family model is silently truncated mid-output. The user is left with a half-rendered table and no indication the answer was cut off. Intermittent (depends on answer + reasoning length), not a crash.

---

## TL;DR

The engine's context window is **`n_ctx = 8192`**. For a *reasoning* model that window is shared, in a single turn, by:

1. the prompt (system + context + tool schemas + **tool results**, e.g. a 53-feature data dictionary), plus
2. the hidden `reasoning_content` (the model's thinking), plus
3. the visible `content` (the actual answer).

`llama.cpp` caps generation at `min(max_tokens, n_ctx − prompt_tokens)`. When prompt + thinking + answer would exceed 8192, generation stops at `finish_reason="length"` and the answer is chopped — typically mid-markdown-table. Raising the client's `max_tokens` cannot fix this; the binding limit is `n_ctx`.

This is the same 8192-token ceiling behind the **multi-turn tool-calling 500** that DeclarAI currently works around client-side (auto_ml `v2.43.3`). Both symptoms disappear if `n_ctx` is raised.

---

## Symptom

A blocking `POST /v1/chat/completions` to `nemotron-3-nano:30b` asking for a long, structured answer (two markdown tables) returns a reply whose last line is a half-written table row, e.g.:

```
## 2. How to pick the concrete IDs for your problem
| Step | Recommended ID(s)          ← cut off here; no separator row, no data rows
```

`finish_reason` on that final round is `"length"`. `content` is non-empty and well-formed up to the cut, so no downstream "empty answer" guard fires — the truncated table renders straight to the chat panel.

## Root cause

`n_ctx` is fixed at 8192 for all models (`src/inference_engine/config.py:51` → `n_ctx: int = Field(default=8192)`, `.env: N_CTX=8192`, passed to `Llama(n_ctx=settings.n_ctx)` at `src/inference_engine/adapters/llama_cpp.py:198,208`). 8192 is far below `nemotron-3-nano`'s trained context (`n_ctx_train` is much larger). Reasoning models are the worst case because thinking tokens consume the same window before the answer is even started.

## Repro (against the running engine)

### A. The context ceiling is 8192 (prompt alone overflows past it)

```python
# probe prompt sizes with a trivial max_tokens=16
for n in (6000, 9000, 16000, 30000, 60000):
    prompt = "Repeat OK. Context: " + ("data " * n)
    client.chat.completions.create(model="nemotron-3-nano:30b",
        messages=[{"role": "user", "content": prompt}], max_tokens=16)
```

Observed:

```
prompt ~6000 tokens → OK   (usage.prompt_tokens=6022)
prompt ~9000 tokens → 500 Internal Server Error   ← prompt exceeds n_ctx
prompt ~16000/30000/60000 → 500 Internal Server Error
```

So the hard ceiling sits between 6,022 and ~9,000 tokens — i.e. the configured 8192. NB: this surfaces as an **HTTP 500**, not a clean `400 context_length_exceeded` (see "Secondary ask" below).

### B. Reasoning + answer share the budget and truncate together

```python
# tiny prompt, but ask for an exhaustive multi-table answer, cap at 4096
r = client.chat.completions.create(model="nemotron-3-nano:30b",
    messages=[{"role":"system","content":"Answer in exhaustive markdown with multiple big tables."},
              {"role":"user","content":"List ALL data purification steps with two large tables. Be exhaustive."}],
    max_tokens=4096, temperature=0.4,
    extra_body={"chat_template_kwargs": {"enable_thinking": True}})
```

Observed:

```
finish_reason: length
usage.completion_tokens: 4096          ← hit the budget exactly
reasoning_content chars: 6310          ← ~1.6K tokens spent thinking
content chars: 11009                   ← answer truncated mid-row:
   "... | 51 | **Data-Quality Reporting** | Generate summary tables ... |"
```

The 4096-token completion budget was split between reasoning and answer; the answer was cut off. In production the limit is `n_ctx − prompt`, which is smaller still once real tool-result prompts are included.

### C. Production shape

In DeclarAI's UI the per-turn prompt routinely includes a large tool result (a 53-feature data dictionary). The visible answer therefore gets only `8192 − prompt − reasoning` tokens — enough for short answers, but long two-table answers overrun it and truncate.

## Recommended fix

**Raise `n_ctx` substantially for chat / tool-calling workloads** — e.g. a default of **32768** (or size it per-model from the GGUF's `n_ctx_train`, capped by a memory budget). `nemotron-3-nano:30b` supports far more than 8K. On the 128 GB unified-memory target box the extra KV-cache cost is acceptable; if memory is the concern, gate the larger window behind a per-model or per-deployment setting rather than a global 8192.

Raising `n_ctx` fixes this report **and** retires the DeclarAI client-side workaround for the multi-turn 500 (auto_ml `v2.43.3`), since both are caused by the same 8192 ceiling.

### Secondary asks (lower priority, previously raised)

1. **Return `400 context_length_exceeded`, not `500`, on prompt overflow.** Repro A overflows the window and surfaces as an opaque `500 Internal Server Error`. A typed 4xx (with the limit in the body) lets clients degrade deterministically instead of pattern-matching on 500s. (Cross-ref: auto_ml `v2.43.3` has to treat a 500-with-prior-tool-results as "context overflow" heuristically.)
2. **Reasoning/thinking budget knob (`reasoning_max_tokens` / `thinking_budget`).** Re-raising follow-up #2 from `nemotron-cot-leak-blocking-normalizer.md`: capping thinking would reserve window for the answer and directly reduce the truncation in repro B. Complementary to raising `n_ctx`.

## Test suggestions for the engine repo

1. Load `nemotron-3-nano:30b`; assert the effective `n_ctx` is ≥ the configured value and ideally derived from `n_ctx_train`.
2. Prompt just over the configured `n_ctx` → expect a typed `400 context_length_exceeded`, not a 500.
3. Reasoning-family model + `max_tokens` set so `prompt + reasoning + answer` would exceed the window → assert the response still completes (or that a thinking-budget cap leaves room for a non-truncated answer).

## DeclarAI side — no client change planned

The only real fix is engine-side (`n_ctx`). DeclarAI is **not** shipping a client-side mitigation for this: `max_tokens` cannot raise the ceiling, and a continuation pass under an 8192 window would itself overflow (the continuation prompt = original prompt + the large partial answer). We'll wait on the engine fix. Existing client-side guards (`v2.43.3` overflow handling, `v2.44.x` finalization) remain as-is and can be simplified once `n_ctx` is raised.

## Cross-reference

- Engine config: `src/inference_engine/config.py:51` (`n_ctx` default 8192), `.env: N_CTX=8192`, `src/inference_engine/adapters/llama_cpp.py:198,208` (`n_ctx=settings.n_ctx`).
- Related engine feedback: `docs/engine-feedback/nemotron-cot-leak-blocking-normalizer.md` (RESOLVED; follow-up #2 = thinking budget), `docs/engine-feedback/nemotron-multi-turn-500-arguments-shape.md` (RESOLVED).
- DeclarAI client-side context-overflow workaround this would retire: auto_ml `v2.43.3` (`backend/ai_assistant/views.py`, tool-loop `except` at the `_call_llm` call — treats a 500-after-tool-results as overflow and falls through to a no-tools synthesis).
