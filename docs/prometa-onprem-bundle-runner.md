# DeclarAI Prometa On-Prem Bundle Runner

Prometa builds, governs, signs, and observes. DeclarAI runs.

This repository now includes the DeclarAI-side runner foundation for signed
Prometa deployment bundles:

```text
backend/ai_assistant/prometa_runner/
```

It consumes the bundle from Prometa's:

```text
GET /api/agent-manifests/{id}/bundle
```

or from a local JSON file, then verifies and preflights the bundle before any
local MCP tool execution.

## Signature Verification

The runner expects the bundle envelope:

```json
{
  "content": {},
  "algorithm": "ed25519",
  "publicKey": "<base64 SPKI public key>",
  "signature": "<base64 detached signature>",
  "signed": true
}
```

Canonicalization is:

```text
json-stable-sort-keys-utf8-no-ascii-escape-v1
```

Python verification mirrors Prometa's TypeScript implementation:

- recursively sort object keys;
- preserve array order;
- serialize compact JSON with no spaces;
- encode as UTF-8;
- do not ASCII-escape non-ASCII text;
- reject NaN/Infinity.

The runner accepts Prometa's current envelope without a `canonicalization`
field as this algorithm, and also accepts the explicit field when Prometa adds
it. Unknown canonicalization values are rejected.

## Preflight Policy

Before a bundle can run, DeclarAI rejects:

- unsigned or unverifiable bundles, unless `--allow-unsigned` is used for local
  development;
- `content.manifest.deployable !== true`;
- missing `content.manifest.agentId`;
- tool scopes not granted by the bundle identity or bundle-level
  `grantedScopes`.

For tool calls, the runner enforces:

- `approvalRequired` / `approval_required` when Prometa carries it;
- `requiredGuardrails` / `required_guardrails` when Prometa carries it;
- fallback inference for current bundle shapes:
  - `declarai.action.*` requires `human_approval`;
  - high/critical risk tools require `risk_gate`;
  - `declarai.action.execute_code` also requires `dataset_backup`.

## Commands

Verify and summarize a local bundle:

```bash
cd backend
python manage.py run_prometa_bundle --bundle-file /path/to/bundle.json
```

Fetch, verify, and summarize from Prometa:

```bash
python manage.py run_prometa_bundle \
  --prometa-url https://prometa.internal \
  --manifest-id <manifest-id> \
  --token "$PROMETA_TOKEN"
```

Execute one bundled MCP operation locally:

```bash
python manage.py run_prometa_bundle \
  --bundle-file /path/to/bundle.json \
  --tool declarai.prepare.update_notes \
  --arguments '{"file_id":42,"payload":{"action":"add","content":"Review note"}}'
```

For direct actions:

```bash
export DECLARAI_MCP_ENABLE_DIRECT_ACTIONS=true
export DECLARAI_MCP_SCOPES=declarai.notes.write

python manage.py run_prometa_bundle \
  --bundle-file /path/to/bundle.json \
  --tool declarai.action.update_notes \
  --arguments '{"file_id":42,"payload":{"action":"add","content":"Review note"}}' \
  --approval-id approval-123
```

## Telemetry Correlation

The runner stamps Prometa bundle identity into the active MCP spans:

```text
gen_ai.agent.id
prometa.agent.id
prometa.agent_id
prometa.solution.id
prometa.solution_id
declarai.prometa.bundle.agent_id
declarai.prometa.bundle.solution_id
```

The existing MCP spans keep emitting:

```text
declarai.mcp.*
```

This lets Prometa join DeclarAI-run tool calls back to the Agent Registry row
that produced the signed bundle, then score those runs through AQL, AML,
policies, and audit.

## Boundary

Prometa never calls DeclarAI `tools/call`. This runner is the DeclarAI-owned
execution-plane primitive. A full autonomous loop can sit above it, but all MCP
tool execution should pass through this verifier and policy gate.
