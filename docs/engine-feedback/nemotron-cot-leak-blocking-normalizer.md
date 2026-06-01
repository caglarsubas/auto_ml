# Bug report: Nemotron CoT leak into `content` on the blocking-path response normalizer

**Status:** RESOLVED (2026-05-30) — engine blocking-path normalizer fix verified live; chain-of-thought no longer leaks into `content`. Two optional ergonomic follow-ups remain (see [Residual follow-ups](#residual-follow-ups-optional-low-priority)).
**Originally filed:** Open — diagnosed end-to-end via repeated A/B probe + engine code read.
**Audience:** `llm-inference-engine` team
**From:** DeclarAI (POC customer)
**Date filed:** 2026-05-28
**Engine commit at filing:** `ebf6dd6` on `main` (PR #9 multi-turn fix, running native PID 28945)
**Model:** `nemotron-3-nano:30b` (representative of the `_REASONING_MARKERS` family)
**Severity:** P1 — every multi-turn tool-calling conversation on a reasoning-family model is at risk of leaking the model's chain-of-thought into `content` whenever the model exhausts `max_tokens` before emitting `</think>` or a `<tool_call>` anchor.

---

## Resolution (2026-05-30 — engine fix verified live)

The `llm-inference-engine` team shipped the blocking-path fix (the AGGRESSIVE `expects_reasoning_prelude` policy — unanchored text on a reasoning-family model routes to `reasoning_content` regardless of `finish_reason`, making the blocking path byte-symmetric with `StreamNormalizer`). DeclarAI re-probed `nemotron-3-nano:30b` live against the running engine and confirms the P1 leak is **closed**.

**`finish_reason == "length"`** (tight `max_tokens=350` — the original failure condition):
- `content` length: **0** — no CoT in `content`
- `reasoning_content` length: 1438 — the unfinished thought is correctly routed here (`"We need to propose 3-5 new features derived from existing ones…"`)
- choice keys: `['finish_reason', 'index', 'logprobs', 'message']`

**`finish_reason == "stop"`** (`max_tokens` ∈ {4096, 8192, 16384} — realistic UI prompt stack: lite system prompt + 3.8 KB slim context + skill snippet + 12 tools):
- `content`: clean formatted answer (a `**Proposed derived features**` markdown table)
- `reasoning_content`: 4936–6689 chars, cleanly separated
- no markers leaked into `content` at any budget

So the P1 symptom (raw chain-of-thought rendered to the user) no longer reproduces. The original recommendation — **Option A point 1** (on `finish_reason=="length"`: `reasoning_content=text`, `content=None`) — is implemented and working.

### DeclarAI client-side refinement (`auto_ml` v2.44.0)

The aggressive policy moved the burden to the client for one sub-case: when `finish_reason=="length"`, `reasoning_content` holds UNFINISHED thought, not a deliverable answer. v2.44.0:
- `_recover_reasoning_content` promotes `reasoning_content`→`content` ONLY on `finish_reason=="stop"` (a complete answer the engine merely misrouted); on `"length"` it leaves `content` empty and tags the choice `declarai_reasoning_truncated`.
- `_chat_workflow` then runs a strict finalization re-prompt (tools off) to produce a clean answer from the tool results already in hand.
- Live recheck: **12/12** runs of the original failing question returned a clean answer with an `execute_code` Apply action and zero CoT leak.

## Residual follow-ups (optional, low priority)

Neither blocks DeclarAI; both are ergonomic improvements for any reasoning-family client.

1. **Structured truncation flag (P3, small).** The choice payload exposes no signal that reasoning was truncated — keys are just `['finish_reason', 'index', 'logprobs', 'message']`. Clients must infer it from `content=="" AND reasoning_content!="" AND finish_reason=="length"`. Re-raising **Option A point 2** below: surface `reasoning_truncated: true` (or `model_reasoning_unanchored: true`) on the choice so every client doesn't reimplement the same heuristic.
2. **Reasoning/thinking budget knob (P3–P4, feature).** Root cause of the residual `finish_reason=="length"` empty-answer case: on large prompt stacks the model spends its entire `max_tokens` thinking and never emits an answer. A `reasoning_max_tokens` / `thinking_budget` (cap thinking, then force the answer) would fix this at the source. DeclarAI's finalization pass handles it adequately for now.

---

## Symptom (as originally filed)

A blocking `POST /v1/chat/completions` against `nemotron-3-nano:30b` with a large system-prompt stack + 15 tools returns:

- `content`: full chain-of-thought as prose ("We need to suggest 3 derived features for credit-risk boosting. We're an ML advisor inside a credit-risk pipeline. The user wants…")
- `reasoning_content`: empty
- `tool_calls`: none
- No `<think>` markers anywhere in the text — neither `<think>` nor `</think>`

In the failing case the response normalizer has nothing to anchor on, so 2000+ chars of pure reasoning land in `content`. UI behavior: the chat panel renders the model's internal monologue to the user, and the structured tool call never materialises.

## Root cause

**Architectural asymmetry between streaming and blocking paths in the response normalizer.**

The **streaming** normalizer (`StreamNormalizer`) takes an `expects_reasoning_prelude` flag (see `response_normalize.py:352-357`) and initialises its state to `_S_REASONING` when set, so it correctly handles the case where the chat template invisibly pre-emitted `<think>` at the generation prompt. This flag is wired up at the streaming call site (`api/chat.py:412-414`):

```python
normalizer = StreamNormalizer(
    tools_requested=bool(params.tools),
    expects_reasoning_prelude=bool(caps.get("reasoning")),
)
```

The **blocking** normalizer (`normalize_assistant_text`, called from `_normalize_blocking_result` at `api/chat.py:201-230`) has **no equivalent knob**. It looks for `<think>…</think>` paired blocks, orphan-close (`</think>` with no open), and orphan-open (`<think>` with no close) — but ALL of those require some marker IN the text to anchor on.

When the chat template silently pre-emits `<think>\n`, the model's sampled output starts inside a `<think>` block but the tag itself never appears in `result.text` (it was emitted by the template, not by the model). If the model then runs out of `max_tokens` before emitting either `</think>` or a `<tool_call>` block, the normalizer sees raw prose with no markers and passes it straight through to `content`.

The capability detection is already there — `infer_model_capabilities()` at `response_normalize.py:623-651` returns `reasoning: True` for anything matching `_REASONING_MARKERS = ("nemotron", "deepseek-r1", "qwen3-thinking", ..., "thinking")`. The streaming path uses it. The blocking path doesn't.

## Repro (3-of-3 reliable on `max_tokens=800`; intermittent on 4096)

```bash
curl -sS http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "nemotron-3-nano:30b",
  "messages": [
    {"role":"system","content":"You are an ML advisor inside a credit-risk pipeline. Use tools to fetch data dictionary and feature stats. Ground your answer in bullets and short paragraphs over essays. You can DIRECTLY MODIFY the user pipeline by emitting an ACTION BLOCK at the END of your reply."},
    {"role":"user","content":"Suggest 3 derived features for credit-risk boosting and create them."}
  ],
  "tools":[{"type":"function","function":{"name":"get_data_dictionary","description":"Returns the data dictionary","parameters":{"type":"object","properties":{}}}},
           {"type":"function","function":{"name":"execute_code","description":"Run pandas code","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}}}],
  "max_tokens": 800,
  "temperature": 0.4
}'
```

Expected: `reasoning_content` populated, `content` empty (or contains only the post-`</think>` answer).
Observed (typical): `content` contains full CoT prose, `reasoning_content` is empty, `tool_calls` empty, `finish_reason: "length"`.

Note on flakiness: on a *small* `max_tokens`, the model usually fails to close `</think>` in time, so the leak happens reliably. On `max_tokens=4096` (DeclarAI's production default), the model usually succeeds — but production system prompts in our app routinely stack 15k+ chars of context, which leaves less effective output budget and reproduces the leak ~30% of the time. The screenshot we captured in DeclarAI was one of those leaking responses.

## Why `chat_template_kwargs={"enable_thinking": True}` is hygiene, not a fix

It's tempting to think the fix is to set `enable_thinking=True` on the Jinja render so the template explicitly opens `<think>\n`. We confirmed via 6 probes that this:

- **Does** make the wire-output more explicit when the model does produce markers (the `<think>` opener becomes visible in the prompt → model is more likely to produce a matching `</think>`).
- **Does not** reliably prevent the leak — at tight token budgets it actually makes the leak slightly *more* likely, because the template-side "you have a thinking section" signal nudges the model to spend more tokens reasoning.

So `enable_thinking=True` is a defensible default for reasoning-family models on ergonomic grounds, but it is not the bug fix. The bug fix is making the blocking-path normalizer match the streaming-path normalizer's behavior.

## Recommended fix

**Option A (preferred): add `expects_reasoning_prelude` to the blocking-path normalizer.** Mirror what `StreamNormalizer` already does. Two sub-cases need to be handled when the flag is set and no `</think>` exists in the text:

1. **`finish_reason == "length"`**, no `<think>` markers, no `<tool_call>` anchors → the model was still thinking when the budget ran out. The entire `result.text` is reasoning. Set `reasoning_content = result.text`, `content = None`, `finish_reason = "length"`.
2. **`finish_reason == "stop"`**, no markers, no tool_calls → ambiguous. Two plausible policies:
   - Conservative: treat as content (current behavior). Risk: leak.
   - Aggressive: treat as reasoning since `expects_reasoning_prelude` was True. Risk: hides a real assistant answer in the rare case the model chose not to think.
   We'd prefer the conservative policy here PLUS surfacing `model_reasoning_unanchored: True` in the choice payload so clients can render an optional "this model's reasoning may have leaked" caveat — but either is fine.

**Option B (smaller diff): synthetic `<think>` prepend.** When the blocking-path normalizer is called for a reasoning-family model, prepend a virtual `<think>` to the text before running `_split_reasoning`. The existing orphan-open handler at `response_normalize.py:203-209` already does the right thing in this case (treat everything from `<think>` onward as reasoning when no `</think>` follows).

Pseudocode for Option B:

```python
def normalize_assistant_text(text, *, expects_reasoning_prelude=False, ...):
    raw = text or ""
    if expects_reasoning_prelude and "<think>" not in raw:
        # The chat template silently opened a think block; tell the splitter.
        raw = "<think>" + raw
    body, reasoning = _split_reasoning(raw)
    ...
```

Then `_normalize_blocking_result` at `chat.py:211` becomes:

```python
caps = infer_model_capabilities(model_name, backend=adapter.backend_name, fmt=...)
normalized = normalize_assistant_text(
    result.text,
    existing_tool_calls=result.tool_calls,
    finish_reason=result.finish_reason,
    tools_requested=bool(params.tools),
    expects_reasoning_prelude=bool(caps.get("reasoning")),
)
```

## Test suggestions for the engine repo

Three new cases in `tests/test_response_normalize.py`:

1. **Reasoning-family + unmarked text + finish=length** → everything goes to `reasoning_content`, `content` is None.
2. **Reasoning-family + unmarked text + finish=stop** → policy-dependent; pin whichever the team picks.
3. **Reasoning-family + properly-marked `<think>…</think>answer`** → existing orphan-close path keeps working unchanged.

## DeclarAI-side mitigation (already shipped — does not fix the leak)

`auto_ml#19` (v2.43.1) does two things:

1. Mirrors the engine's `reasoning`/`thinking`/`thinking_level` flags from `/v1/models` into DeclarAI's model registry. These were hard-coded `False` previously, which masked this exact bug-class from our config layer. This is a legitimate config bug fix and stays.
2. Passes `chat_template_kwargs={"enable_thinking": True}` for reasoning-family models. This is hygiene, not a fix (see "Why … is not a fix" above), but we keep it because it's a documented OpenAI-extension default that other clients (vLLM, Ollama HTTP) honour the same way.

Neither change closes the leak. The leak only closes when the engine's blocking-path normalizer learns about `expects_reasoning_prelude`.

## Cross-reference

- Code references: `response_normalize.py:623-651` (capability inference), `response_normalize.py:170-212` (`_split_reasoning`), `response_normalize.py:320-414` (`StreamNormalizer` and its `expects_reasoning_prelude` knob), `api/chat.py:201-230` (blocking normalizer call site missing the flag), `api/chat.py:409-414` (streaming normalizer that has the flag).
- DeclarAI client-side capability mirroring + hygiene kwarg: PR `auto_ml#19` (v2.43.1).
- Prior engine fixes in the same family: PR `llm_inference_engine#8` (vendor reasoning/tool-call XML normalization), PR `llm_inference_engine#9` (multi-turn tool-arguments dict/str fix).
- DeclarAI bug-report doc for the multi-turn 500: `docs/engine-feedback/nemotron-multi-turn-tool-arguments-500.md` (RESOLVED).
