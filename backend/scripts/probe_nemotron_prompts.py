"""One-shot probe: does Nemotron call tools under different system prompts?

Sends the same user query to the engine three times with different system
prompts and reports finish_reason + tool_calls + content shape.  Used to
diagnose the v2.40.0 lite-prompt mismatch surfaced by the UI smoke test.
Not part of the regular test suite.
"""
import os
import sys

from openai import OpenAI

from ai_assistant.views import _LITE_SYSTEM_PROMPT

# v2.44.0 probe: replicate the UI smoke-test conditions.  The UI question
# is more demanding than 'list features' and DeclarAI also injects the
# full tool catalog + slim context.
USER_Q_COMPLEX = (
    "according to the project goal and the feature descriptions we have, "
    "which new features can be derived from others in the aim of "
    "increasing the predictive performance of boosting algorithms. "
    "create these suggested features in our dataset."
)

# Approximate the real DeclarAI tool catalog - names from the lite prompt's
# TOOL ROUTING section so the model sees the same surface area.
_TOOL_NAMES = [
    'get_data_dictionary', 'get_feature_stats', 'get_selected_features',
    'get_vif_decomposition', 'get_shap_details', 'get_cv_results',
    'get_dq_summary', 'get_pipeline_config', 'get_pipeline_notes',
    'get_encoding_plan', 'get_purifier_options', 'get_sfs_results',
]
TOOLS_FULL = [
    {
        'type': 'function',
        'function': {
            'name': name,
            'description': f'DeclarAI pipeline tool: {name}',
            'parameters': {'type': 'object', 'properties': {}},
        },
    }
    for name in _TOOL_NAMES
]

# Synthetic slim context that approximates the size+shape of what DeclarAI's
# _chat_workflow injects post-data-dictionary: feature names, pipeline
# status, target definition.  Mirrors the UI screenshot where Var_1..Var_5
# were visible.
SLIM_CONTEXT = (
    "=== PIPELINE CONTEXT ===\n"
    "Section: Dictionary Declaration\n"
    "Target: Good_Bad_Flag (good/bad flag of credit applications within "
    "12 months of usage)\n"
    "Total features: 53  |  Excluded from model: 27\n\n"
    "Data Dictionary (Feature_Name | Description | Data_Type):\n"
    "  AppID | Primary Key | integer\n"
    "  Application_Datetime | Application date and timestamp | str\n"
    "  Target | Good_Bad_Flag | integer\n"
    + "".join(
        f"  Var_{i} | Synthetic description for Var_{i} "
        f"({'integer' if i % 3 else 'float64'}) | "
        f"{'integer' if i % 3 else 'float64'}\n"
        for i in range(1, 54)
    )
    + "\nPipeline Status: data_declaration=complete, data_purifier=pending\n"
)

# Synthetic skill content that approximates the feature-engineering skill
# DeclarAI auto-routes for derivation requests.  Contains code examples
# (which is what we suspect was derailing Nemotron in the UI run).
SKILL_SNIPPET = (
    "=== SKILL: Cross-Cutting Universal Feature Patterns ===\n"
    "Common derived features for credit-risk boosting models:\n"
    "  Debt_to_Income: df['Debt_to_Income'] = df['Var_19'] / "
    "df['Var_24'].replace(0, 1)\n"
    "  Utilization_Ratio: balance / limit\n"
    "  Age_Bucket: pd.cut(age, bins=[18,25,35,50,65,99])\n"
    "  Time_Since_Last_Default: months since most recent default\n"
    "  Application_Velocity: count of applications in last 30/60/90 days\n"
    "=== SKILL: Industry-Specific Patterns (Credit) ===\n"
    "  Behavioral aggregates (L1M / L3M / L6M / L12M)\n"
    "  Worst-status indicators (cycle delinquency max)\n"
    "  Bureau-derived: count of inquiries, oldest tradeline age\n"
    "INSTRUCTION: when user asks to derive features, propose 3-5 with "
    "rationale and emit ACTION BLOCK calling execute_code at the end.\n"
)
print(f"# slim_context chars   : {len(SLIM_CONTEXT)}", flush=True)
print(f"# skill_snippet chars  : {len(SKILL_SNIPPET)}", flush=True)


def main() -> int:
    client = OpenAI(
        api_key=os.environ.get('LLM_ENGINE_API_KEY', 'sk-engine-local'),
        base_url=os.environ.get(
            'LLM_ENGINE_BASE_URL',
            'http://host.docker.internal:8080/v1',
        ),
    )

    # v2.44.0 hypothesis confirmation: replay the UI conditions (lite prompt
    # + slim context + skill injection + complex user query + N tools) at
    # three max_tokens budgets to verify whether the failure is purely a
    # token-budget problem.  Each scenario is the SAME except for max_tokens.
    realistic_messages = [
        {'role': 'system', 'content': _LITE_SYSTEM_PROMPT},
        {'role': 'system', 'content': SLIM_CONTEXT},
        {'role': 'system', 'content': SKILL_SNIPPET},
        {'role': 'user', 'content': USER_Q_COMPLEX},
    ]
    scenarios = [
        ('F: realistic + max_tokens=4096',  realistic_messages, TOOLS_FULL, 4096),
        ('G: realistic + max_tokens=8192',  realistic_messages, TOOLS_FULL, 8192),
        ('H: realistic + max_tokens=16384', realistic_messages, TOOLS_FULL, 16384),
    ]

    rows = []
    for label, msgs, tools, max_tok in scenarios:
        try:
            r = client.chat.completions.create(
                model='nemotron-3-nano:30b',
                messages=msgs,
                tools=tools,
                tool_choice='auto',
                timeout=300,
                max_tokens=max_tok,
            )
        except Exception as exc:
            rows.append({
                'label': label,
                'max_tok': max_tok,
                'finish_reason': f'ERROR: {type(exc).__name__}',
                'tool_calls': 0,
                'content_chars': 0,
                'reasoning_chars': 0,
                'tool_ok': False,
                'content_head': str(exc)[:200],
            })
            continue
        m = r.choices[0].message
        fr = r.choices[0].finish_reason
        tc = m.tool_calls or []
        c_len = len(m.content or '')
        rc_len = len(getattr(m, 'reasoning_content', None) or '')
        tool_ok = bool(tc) and fr == 'tool_calls'
        rows.append({
            'label': label,
            'max_tok': max_tok,
            'finish_reason': fr,
            'tool_calls': len(tc),
            'content_chars': c_len,
            'reasoning_chars': rc_len,
            'tool_ok': tool_ok,
            'content_head': (m.content or '')[:240],
        })

    print(f"{'scenario':36s}  {'max_tok':>7s}  {'finish':>14s}  "
          f"{'tcalls':>6s}  {'content':>7s}  {'reason':>6s}  result")
    print('-' * 100)
    for r in rows:
        print(
            f"{r['label']:36s}  {r['max_tok']:>7d}  "
            f"{r['finish_reason']:>14s}  {r['tool_calls']:>6d}  "
            f"{r['content_chars']:>7d}  {r['reasoning_chars']:>6d}  "
            f"{'PASS' if r['tool_ok'] else 'FAIL'}"
        )
    print()
    for r in rows:
        if not r['tool_ok']:
            print(f"{r['label']} content head:\n  {r['content_head']!r}\n")

    return 0 if all(r['tool_ok'] for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
