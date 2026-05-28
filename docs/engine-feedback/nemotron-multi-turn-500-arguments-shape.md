# Bug report: Nemotron multi-turn tool calls return HTTP 500 (Jinja `items` on JSON-string `arguments`)

**Status:** **RESOLVED 2026-05-28** — engine team shipped the recommended fix as `llm_inference_engine#9` (merged commit `ebf6dd6`) within a few hours of filing. See the resolution log immediately below; the original bug report is preserved verbatim further down for posterity.
**Audience:** `llm-inference-engine` team
**From:** DeclarAI (POC customer)
**Date filed:** 2026-05-28
**Date resolved:** 2026-05-28 (same-day turnaround)
**Engine commit at filing:** running build of `/Users/caglarsubasi/Desktop/prometa/pocs/llm_inference_engine_v1` (process PID 77443, uvicorn → `inference_engine.main:app`)
**Engine commit at resolution:** `ebf6dd6` on `main` (PR `llm_inference_engine#9`)
**Model:** `nemotron-3-nano:30b` (GGUF blob `sha256-a70437c41b3b…`)
**Severity at filing:** P1 — every multi-turn tool-calling conversation on Nemotron crashes on turn 2. The engine-side Nemotron XML-leak fix shipped earlier this week unblocked turn 1; this was the next wall.

---

## Resolution log — `llm_inference_engine#9` (merged 2026-05-28)

The engine team adopted the recommended fix verbatim: a small static helper on `LlamaCppAdapter` that JSON-decodes `tool_calls[].function.arguments` before handing the message to the Jinja chat template, with sensible fallbacks for the empty-string and non-JSON-string cases. The change is engine-local and scoped to the `llama_cpp` adapter — vLLM and Ollama HTTP adapters intentionally keep `arguments` as a string because their upstream servers do their own templating.

### Engine-side changes that landed

| File | Change |
|---|---|
| `src/inference_engine/adapters/llama_cpp.py` | New `_arguments_for_template(raw)` static helper. Empty string → `{}` (zero-argument call is a mapping with no keys). Valid JSON → parsed (dict, list, etc.). Non-JSON string → returned unchanged so OpenAI-strict templates that index `arguments` as a string still work. Helper wired into `_to_llama_messages` at the single point where the rendered dict is built; `_to_llama_messages` switched from `@staticmethod` to `@classmethod` so it can reach the helper cleanly. No other code paths touched. |
| `tests/test_llama_cpp_tool_arguments.py` | New file, 6 focused regression tests: JSON string → dict (the Nemotron-fix case), empty string and `"{}"` → `{}`, non-JSON garbage → raw string (fallback for OpenAI-strict templates), JSON array → list (positional-args tools), full multi-turn round-trip (user → assistant w/ tool_calls → tool result) preserves all other fields, plain chats without `tool_calls` unaffected. |

### Engine-side verification (from PR #9)

```
tests/test_llama_cpp_tool_arguments.py ......  [6 new tests pass]
tests/                                          [252/252 pass overall]
ruff check                                      [clean]
```

### DeclarAI-side verification (post-restart, this checkout)

After fast-forwarding the local engine checkout to `ebf6dd6` and restarting the native launchd agent (`make native-restart`), the exact `curl` reproduction from the "Reproduction" section below now succeeds:

```
HTTP 200 | total=2.453310s
finish_reason: length        ← only because we capped max_tokens=64 for the smoke
content: "Okay, the user asked me to list files, so I called the list_files function.
         The response came back as an empty array. That means there are no files to list…"
prompt_tokens: 268
completion_tokens: 64
```

`grep -c 'TypeError: Can only get item pairs' /private/tmp/prometa-inference-engine.err.log` holds at 6 (all pre-fix stacks; zero new occurrences since the restart at `15:45:03`).

### DeclarAI-side follow-ups

- This bug report doc was kept in-repo as a historical artifact (mirrors the `docs/prometa-feedback/agent-id-auto-registration.md` convention).
- No "Nemotron is single-turn-only" caveats need to be added to the UI — the workaround we considered while the bug was open never shipped to users.
- DeclarAI PR `auto_ml#18` (which contained this bug report) was landed with this resolution log appended.

---

## Symptom

From DeclarAI's perspective, the OpenAI SDK raises `openai.InternalServerError: Internal Server Error` on the **second** `/v1/chat/completions` call of any Nemotron tool round-trip (turn 1 returns `finish_reason=tool_calls` cleanly; turn 2 — with the appended `role=tool` result — fails). Single-turn calls and calls without tools both work.

## Root cause

Nemotron's embedded GGUF chat template at **line 150** does:

```jinja
{%- for tool_call in message.tool_calls %}
    {%- if tool_call.function is defined %}
        {%- set tool_call = tool_call.function %}
    {%- endif %}
    {{- '<tool_call>\n<function=' ~ tool_call.name ~ '>\n' -}}
        {%- if tool_call.arguments is defined %}
            {%- for args_name, args_value in tool_call.arguments|items %}     {# ← line 150 #}
                {{- '<parameter=' ~ args_name ~ '>\n' -}}
                ...
            {%- endfor %}
        {%- endif %}
    {{- '</function>\n</tool_call>\n' -}}
{%- endfor %}
```

The Jinja `|items` filter (`jinja2.filters.do_items`) requires its operand to be a `collections.abc.Mapping`. But per the **OpenAI tool-calling spec**, `tool_calls[i].function.arguments` is a **JSON-encoded string**, not a dict:

> `arguments` — The arguments to call the function with, as generated by the model in JSON format.

Every OpenAI-compatible client (DeclarAI included) round-trips the assistant turn back to the server with `arguments` exactly as the engine emitted it: a string. So on turn 2 the template hits `'{"file_id": 497}' | items` → `TypeError: Can only get item pairs from a mapping.` → uncaught exception in the FastAPI handler → HTTP 500.

The reason this works in HuggingFace `transformers` is that `apply_chat_template` parses `arguments` from JSON string → dict **before** rendering the template (`transformers/tokenization_utils_base.py::apply_chat_template`). The llama-cpp-python path goes through `llama_cpp.llama_chat_format.chat_completion_handler` → `chat_formatter` → `self._environment.render(messages=…)` with **no such coercion**, so the raw string reaches the template.

## Evidence — engine stack trace

From `/private/tmp/prometa-inference-engine.err.log` (6 identical occurrences):

```
File ".../src/inference_engine/api/chat.py", line 271, in _blocking_response
    result = await adapter.generate(messages, params)
File ".../src/inference_engine/adapters/llama_cpp.py", line 322, in generate
    result = await asyncio.to_thread(_run)
File ".../src/inference_engine/adapters/llama_cpp.py", line 320, in _run
    return self._llm.create_chat_completion(messages=msgs, stream=False, **kwargs)
File ".../llama_cpp/llama.py", line 2017, in create_chat_completion
    return handler(...)
File ".../llama_cpp/llama_chat_format.py", line 615, in chat_completion_handler
    result = chat_formatter(...)
File ".../llama_cpp/llama_chat_format.py", line 235, in __call__
    prompt = self._environment.render(...)
File ".../jinja2/environment.py", line 1295, in render
    self.environment.handle_exception()
File "<template>", line 150, in top-level template code
File ".../jinja2/filters.py", line 249, in do_items
    raise TypeError("Can only get item pairs from a mapping.")
TypeError: Can only get item pairs from a mapping.
```

## Evidence — DeclarAI request capture (turn 2)

Captured via temporary `[V44_PROBE]` instrumentation in `ai_assistant.views._call_llm` (now removed):

```
[V44_PROBE] === request === model=nemotron-3-nano:30b max_tokens=4096 temperature=0.4 n_tools=15 n_messages=6
[V44_PROBE]   msg[0] role=system    chars=7022 head='You are DeclarAI Assistant — …'
[V44_PROBE]   msg[1] role=system    chars=2423 head='Pipeline context summary …'
[V44_PROBE]   msg[2] role=system    chars=8240 head="The user's question matched the 'feature-engineering' skill …"
[V44_PROBE]   msg[3] role=user      chars=237  head='according to the project goal …'
[V44_PROBE]   msg[4] role=assistant chars=0    head=''                      # ← carries tool_calls
[V44_PROBE]   msg[5] role=tool      chars=4528 head='Data Dictionary (53 features): …'
openai.InternalServerError: Internal Server Error
```

The `msg[4]` assistant payload contains the engine-emitted tool call from turn 1, which we relay verbatim:

```json
{
  "role": "assistant",
  "content": "",
  "tool_calls": [
    {
      "id": "...",
      "type": "function",
      "function": {
        "name": "get_data_dictionary",
        "arguments": "{}"                <-- string, per OpenAI spec
      }
    }
  ]
}
```

Even the empty-dict case (`"{}"`) trips the template, because `"{}" | items` is still a string-on-mapping-filter error.

## Reproduction (minimal, from DeclarAI's machine)

```bash
curl -sS http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "nemotron-3-nano:30b",
    "messages": [
      {"role": "user", "content": "list files please"},
      {"role": "assistant", "content": "", "tool_calls": [
        {"id":"c1","type":"function",
         "function":{"name":"list_files","arguments":"{}"}}
      ]},
      {"role": "tool", "tool_call_id": "c1", "content": "[]"}
    ],
    "tools": [{"type":"function","function":{
      "name":"list_files","description":"list files","parameters":{"type":"object","properties":{}}
    }}]
  }'
```

Expected: 200 with a normal assistant turn.
Actual: 500 with the `TypeError` above.

## Why this is engine-side, not client-side

DeclarAI sends `arguments` as a JSON-encoded string because that is exactly what the engine returned on turn 1 — and what the OpenAI wire spec mandates. Coercing `arguments` to a dict in the client would break the OpenAI contract for every other model (templates that expect the string-shape would then choke on a dict). The translation between OpenAI-shape (string) and template-shape (dict) belongs to whoever owns the template — i.e. the inference engine.

## Recommended fix

Patch `LlamaCppAdapter._to_llama_messages` in `src/inference_engine/adapters/llama_cpp.py` (around line 250–273) to parse the JSON-string `arguments` into a dict before handing it to llama-cpp-python, falling back to the raw value on parse failure so non-JSON or already-coerced payloads keep working:

```python
import json

@staticmethod
def _coerce_tool_arguments(raw):
    """Translate OpenAI-spec JSON-string `arguments` into the dict shape
    HuggingFace-style chat templates (Nemotron-NIM, Qwen, etc.) expect
    when they iterate ``tool_call.arguments | items``.

    Idempotent: dicts pass through. Non-JSON strings pass through so
    OpenAI-strict templates that consume the raw string keep working.
    """
    if not isinstance(raw, str):
        return raw
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    return parsed if isinstance(parsed, dict) else raw

# inside _to_llama_messages:
entry["tool_calls"] = [
    {
        "id": tc.id,
        "type": tc.type,
        "function": {
            "name": tc.function.name,
            "arguments": LlamaCppAdapter._coerce_tool_arguments(
                tc.function.arguments
            ),
        },
    }
    for tc in m.tool_calls
]
```

This mirrors HuggingFace's behavior in `transformers.tokenization_utils_base.apply_chat_template` and is the same shape llama.cpp's own built-in Nemotron grammar produces internally.

## Test suggestion for the engine repo

Add a regression test in `tests/adapters/test_llama_cpp.py` that exercises `_to_llama_messages` with an `assistant` message carrying a string-form `arguments`, and asserts the rendered llama-cpp payload contains a dict.  A separate end-to-end test against any GGUF whose template uses `arguments | items` (Nemotron-NIM, Qwen-coder, GLM-4-tool) would catch future template regressions.

## What DeclarAI is doing in the meantime

- Removed the temporary `[V44_PROBE]` capture in `ai_assistant/views.py` now that diagnosis is complete.
- Nemotron remains selectable in the UI but is documented as **single-turn only** until this fix lands.
- No client-side workaround applied — per the engine-team contract established with the earlier Nemotron XML-leak fix, mutation of the OpenAI wire shape belongs on the engine side.

## Cross-reference

- Previous engine-side Nemotron fix (XML leak in `content` / missing `reasoning_content`): resolved last week, see engine-team thread.
- DeclarAI request-trace capture: removed in the same commit as this report (v2.44.0).
- `prometa-sdk` is **not** implicated here — the failure happens before the SDK sees the response.
