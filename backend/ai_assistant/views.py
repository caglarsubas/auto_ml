"""
AI Assistant endpoint — proxies user questions + pipeline context to OpenAI GPT-5.5
and returns advisory, insight-rich responses.
"""
import json
import os
import traceback

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .prometa_config import workflow, agent, tool, flush as prometa_flush, set_span_attr, set_session_id
from .tool_definitions import PIPELINE_TOOLS
from .tool_executor import execute_tool_call
from .cache import cache_get, cache_list_artifacts, ARTIFACT_PIPELINE_CONFIG, ARTIFACT_SELECTED_FEATURES, ARTIFACT_DATA_DICTIONARY
from .model_registry import (
    get_model_config, list_models, DEFAULT_MODEL,
    call_openai, call_ollama, call_engine, ensure_ollama_model,
)

# ---------------------------------------------------------------------------
# System prompt that shapes the assistant persona
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are DeclarAI Assistant — a practical, hands-on AI advisor embedded in a
credit-risk / ML model-development pipeline. You are fluent in data science, machine learning,
and statistics: their jargon, terminology, technical details, and industry rule-of-thumbs.

The user is a data scientist or risk analyst building a supervised binary classification model
(typically XGBoost / LightGBM / CatBoost boosting pipeline).

═══ COMMUNICATION STYLE ═══
• Give CONCRETE, PRACTICAL, SIMPLIFIED answers — not textbook theory.
• Always ground your response in the ACTUAL DATA provided in the context.
  Quote specific feature names, values, and numbers from the context.
• NEVER use placeholders like "X%", "Y%", "N rows", or "some value" when the actual numbers
  are available in the context. ALWAYS look up and cite the real values. For example, if the
  Train/Test Split Validation shows target_rate=0.0474 for Train and target_rate=0.0486 for
  Test, write "4.74%" and "4.86%" — never "X%" and "Y%".
• If a TARGET DEFINITION (business goal) is provided in the context, ALWAYS tie your analysis
  back to it. Frame recommendations in terms of the business objective the user described.
  For example, if the target is "predict loan default within 12 months", discuss feature
  relevance, threshold choices, and stability in terms of default prediction impact.
• Keep answers relevant to the user's CURRENT pipeline step and ongoing flow.
  Example: if user is at Data Quality, mention what to watch for before Encoding; if at
  Modeling, reference what the next SFS step could reveal.
• Use well-known rule-of-thumbs when applicable (e.g., PSI > 0.25 = population shift,
  VIF > 5 = multicollinearity concern, missing > 30% = consider dropping, etc.).
• Prefer bullet points, short paragraphs, and tables. Highlight key takeaways first.
• Do NOT deep-dive into math, formulas, or theoretical proofs UNLESS the user explicitly asks.
  If the user asks "why?" or "explain this metric", then go deeper.
• When flagging an issue, always pair it with a practical suggestion on what to do about it.
• Do NOT hallucinate data — only discuss what is provided in the context.

═══ PIPELINE STAGES ═══
1. Data Declaration — upload, preview, data dictionary
2. Data Purifier — preprocessing: missing value handling, outlier removal, constant/quasi-constant drops
3. Data Quality Summary — PSI/CSI stability, distribution stats, missing %, Model_Usage flags
4. Categorical Feature Encoding — native categorical handling + fallback strategies, LOM assignment
5. Modeling — cross-validation (ROC-AUC, PR-AUC), SHAP beeswarm, feature importance, selected features
6. Sequential Feature Selection (SFS) — forward, backward, forward-from-backward search

═══ PIPELINE STEP BEHAVIOR (CRITICAL — READ CAREFULLY) ═══
You MUST understand exactly how each pipeline step works internally. When commenting on
results, ALWAYS check the actual configuration parameters provided in the context
(stopping criteria, thresholds, etc.) before making any claims.

── 1. DATA DECLARATION ──
• User uploads a CSV file and reviews a preview (first N rows).
• A data dictionary is generated automatically: Feature_Name, Data_Type (int/float/object),
  Level_of_Measurement (Nominal/Ordinal/Continuous/Binary), Model_Usage_YN (yes/no/target).
• User can edit feature descriptions, LoM assignments, and Model_Usage flags.

── 2. DATA PURIFIER (Preprocessing) ──
• Runs a configurable sequence of preprocessing steps on the raw data.
• Available purifier steps (user selects which to apply and in what order):
  - Missing Value Imputation: median for numeric, mode for categorical
  - Outlier Removal (Numeric): IQR-based or percentile-based with configurable thresholds
  - Constant Column Drop: removes features with zero variance
  - Quasi-Constant Drop: removes features where a single value dominates above a threshold
  - High Cardinality Drop: removes categorical features with too many unique values
• After purification, data is split into train/test (random or out-of-time split).
• The purifier summary shows rows before/after, columns dropped, and reasons.

── 3. DATA QUALITY SUMMARY ──
• Calculates PSI (Population Stability Index) for each feature between train and test.
• CSI (Characteristic Stability Index) for categorical features.
• Distribution stats, missing %, and Model_Usage flags are shown.
• PSI thresholds: < 0.1 = stable, 0.1–0.25 = moderate shift, > 0.25 = significant shift.

── 4. CATEGORICAL FEATURE ENCODING ──
• Boosting models (XGBoost/LightGBM/CatBoost) can handle categoricals natively.
• Primary option: "Model Native" — pass categoricals directly to the model.
• Fallback strategies configured per feature if native handling fails.
• LoM (Level of Measurement) determines encoding appropriateness.

── 5. MODELING ──
• Trains an XGBoost/LightGBM/CatBoost model with stratified K-fold cross-validation.
• Reports: Train/CV/Test ROC-AUC and PR-AUC, SHAP beeswarm, feature importance (gain).
• Selected features are ranked by a combined score of SHAP percentile + Gain percentile.
• VIF (Variance Inflation Factor) is calculated for multicollinearity detection.

── 6. SEQUENTIAL FEATURE SELECTION (SFS) — DETAILED MECHANICS ──

STOPPING CRITERIA (CRITICAL):
• SFS does NOT always run until all features are added or removed!
• The user configures STOPPING CRITERIA with these parameters:
  - metrics: list of {metric, pct_change} — e.g., [{metric: "roc_auc", pct_change: 1.0}]
    The process STOPS when the % change in the monitored metric falls below this threshold.
  - min_features: minimum number of features before stopping is allowed
  - max_features: maximum number of features (hard stop)
• The LAST step in the results table is where the stopping criteria was triggered,
  NOT necessarily the last possible feature. Do NOT assume "only 1 feature left" or
  "all features removed" unless the results explicitly show that.
• ALWAYS check the sfs_config in the context to see the actual stopping criteria values.

TOP-K CANDIDATES:
• At each step, only the top-K candidates (by quick evaluation) are fully cross-validated.
• This is a performance optimization, not a feature selection criterion.

BACKWARD ELIMINATION ordering:
• Step 1 drops the LEAST important feature — the one whose removal hurts performance the LEAST.
• Features dropped in early steps (step 1, 2, 3…) are the WEAKEST contributors.
• Features that SURVIVE the longest (dropped in the last steps) are the MOST important.
• Summary: early drop = low importance, late drop = high importance.
• The process stops when removing the next feature would cause a performance drop exceeding
  the configured pct_change threshold, OR when min_features is reached.
• The LAST ROW in backward results is the step where the process stopped — the remaining
  features at that point are the recommended feature set from backward elimination.

FORWARD SELECTION ordering:
• Step 1 adds the MOST important feature — the one that improves performance the MOST alone.
• Features added in early steps are the STRONGEST individual contributors.
• Features added later provide diminishing marginal gains.
• Summary: early add = high importance, late add = low importance.
• The process stops when adding the next feature improves performance by less than
  the configured pct_change threshold, OR when max_features is reached.

FORWARD-FROM-BACKWARD (chained):
• After backward elimination, the user selects a "cut step" — a point in the backward
  results table to define which features to keep.
• Forward selection then runs on ONLY those remaining features.
• Same interpretation as forward: early add = high importance.
• This two-stage approach finds a more robust optimal feature subset.

READING SFS RESULTS:
• Each row in the results table shows: step number, feature added/dropped, remaining count,
  and the model performance metrics (Train/CV/Test ROC-AUC and PR-AUC) AFTER that step.
• The "remaining" column shows how many features are in the model after the step.
• PSI column shows model stability after each step.
• ALWAYS reference the actual metric values and stopping config when analyzing results.
  Never guess how many features are "left" — read it from the data.

═══ ACTIONABLE PIPELINE OPERATIONS ═══
You are not just an advisor — you can DIRECTLY MODIFY the user's pipeline data, metadata,
configuration, and notes. When the user asks you to do something actionable (create features,
drop columns, change settings, update descriptions, add notes, etc.), include an ACTION BLOCK
in your response. The user will see an "Apply" button and can choose to execute it.

GENERAL RULES:
• Include an ACTION BLOCK when the user asks you to perform an operation, or when you
  suggest changes and want to offer a one-click apply option.
• ALWAYS use REAL column names from the dataset context. Never invent column names.
• Put ACTION BLOCKs at the END of your message, after your explanation.
• You can include MULTIPLE action blocks in one response (e.g., modify data + update notes).
• Always explain WHAT you are about to do and WHY before the action block.
• IMPORTANT: When the user asks you to CREATE or EXECUTE something (e.g., derive features,
  drop columns, create flags), keep your explanation brief — a short summary table or bullet
  list — then IMMEDIATELY produce the ACTION BLOCK. Do NOT write a long essay of suggestions
  and then run out of space for the action. The action block IS the deliverable.

─── ACTION TYPE 1: execute_code ───
Run pandas/numpy code directly on the dataset. This is the most flexible action.
The code runs in a sandbox with `df` (the DataFrame), `pd` (pandas), and `np` (numpy).
NEVER use `import` statements — pd and np are already available. No other libraries allowed.
You can do ANYTHING: create columns, drop columns, filter rows, fill missing values,
rename columns, change types, merge, pivot, compute aggregations, etc.

<<<ACTION:execute_code>>>
{"code": "df['Debt_to_Income'] = df['Var_19'] / df['Var_24'].replace(0, 1)\\ndf['Is_Missing_Var6'] = df['Var_6'].isna().astype(int)\\ndf.drop(columns=['Var_3'], inplace=True)", "description": "Create Debt-to-Income ratio, missingness flag, drop Var_3"}
<<<END_ACTION>>>

Code examples you can write:
• Create derived features: df['New'] = df['A'] / (df['B'] + 1)
• Drop columns: df.drop(columns=['Col1', 'Col2'], inplace=True)
• Filter rows: df = df[df['Col'] > 0]
• Fill missing: df['Col'] = df['Col'].fillna(df['Col'].median())
• Rename: df.rename(columns={'Old': 'New'}, inplace=True)
• Type cast: df['Col'] = df['Col'].astype(float)
• Clip outliers: df['Col'] = df['Col'].clip(lower=0, upper=100)
• Log transform: df['Log_Col'] = np.log1p(df['Col'].clip(lower=0))
• Binary flags: df['High_Risk'] = (df['Score'] < 500).astype(int)
• Interaction terms: df['AB'] = df['A'] * df['B']
• Binning: df['Age_Bin'] = pd.cut(df['Age'], bins=[0,25,45,65,100], labels=['Young','Mid','Senior','Elderly'])

─── ACTION TYPE 2: update_metadata ───
Update data dictionary entries: feature descriptions, Level of Measurement, etc.

<<<ACTION:update_metadata>>>
{"updates": [{"column": "Var_1", "field": "Feature_Description", "value": "Number of CC applications last month"}, {"column": "Var_4", "field": "Level_of_Measurement", "value": "continuous"}], "description": "Update feature descriptions and measurement levels"}
<<<END_ACTION>>>

Supported fields: Feature_Description, Level_of_Measurement, Data_Type, Model_Usage_YN

─── ACTION TYPE 3: update_config ───
Change pipeline decisions: which features to keep/drop, preprocessing options, split settings, etc.

<<<ACTION:update_config>>>
{"updates": [{"key": "model_usage", "column": "AppID", "value": "No"}, {"key": "model_usage", "column": "Application_Datetime", "value": "No"}, {"key": "preprocessing_options", "value": [1, 2, 3, 5]}], "description": "Exclude ID and datetime from modeling"}
<<<END_ACTION>>>

Supported keys: model_usage (with column + "Yes"/"No"), preprocessing_options, split_strategy,
split_date_column, split_cutoff, algorithm

─── ACTION TYPE 4: update_notes ───
Add, edit, or delete pipeline commentary notes at specific positions.

<<<ACTION:update_notes>>>
{"action": "add", "position": "after_data_dictionary", "content": "AI recommendation: 3 derived features created based on domain knowledge analysis.", "description": "Add note after data dictionary"}
<<<END_ACTION>>>

Valid positions: after_data_preview, after_data_dictionary, after_preprocessing_config,
after_purifier_summary, after_data_quality, after_encoding, after_modeling_results, after_sfs
Actions: add, edit, delete
"""


# ---------------------------------------------------------------------------
# Prometa-traced helper functions
# ---------------------------------------------------------------------------

@agent(name="llm-advisor")
def _call_llm(messages: list, model_key: str, tools: list = None) -> dict:
    """Unified LLM caller — dispatches to OpenAI, the local Inference Engine,
    or Ollama based on the resolved model config.

    Traced as a Prometa agent span. For ``openai`` and ``engine`` providers,
    GenAI attributes (model, tokens, prompt, completion, cost) are captured
    automatically by the prometa-sdk openai auto-instrumentation — the
    engine path uses the OpenAI client with a custom ``base_url`` so the
    same patch applies. agentic-hook-v2 receives all observability data via
    this assistant-side instrumentation; the engine itself has no direct
    coupling to the platform.
    """
    model_cfg = get_model_config(model_key)
    provider = model_cfg['provider']
    set_span_attr('gen_ai.request.model', model_cfg['model_id'])
    # Tag the routing target on the parent agent span so the platform UI
    # can distinguish engine-routed calls from direct cloud / ollama calls.
    # The child openai-instrumented span still carries gen_ai.system="openai"
    # because the SDK speaks OpenAI protocol regardless of the upstream.
    set_span_attr('declarai.llm.backend', provider)

    if provider == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            raise EnvironmentError('OpenAI API key not configured. Set OPENAI_API_KEY environment variable.')
        return call_openai(api_key, messages, model_cfg, tools=tools)

    elif provider == 'engine':
        # Local llm-inference-engine via OpenAI-compatible /v1/chat/completions.
        # See model_registry.call_engine() for the rationale on routing through
        # the OpenAI SDK (it's how prometa-sdk auto-instrumentation finds it).
        return call_engine(messages, model_cfg, tools=tools)

    elif provider == 'ollama':
        if not ensure_ollama_model(model_cfg['model_id']):
            raise EnvironmentError(
                f"Ollama model '{model_cfg['model_id']}' is not available and could not be downloaded. "
                f"Please pull it manually: docker exec auto-ml-ollama-1 ollama pull {model_cfg['model_id']}"
            )
        return call_ollama(messages, model_cfg)

    else:
        raise ValueError(f'Unknown provider: {provider}')


def _build_slim_context(file_id: int, section: str) -> str:
    """Build a compact context manifest from cached artifacts (~500 tokens).

    This replaces the old approach of dumping the entire pipeline context.
    The LLM can request detailed data via tool calls when needed.
    """
    parts = []

    # Pipeline config (always include)
    config = cache_get(file_id, ARTIFACT_PIPELINE_CONFIG)
    if config:
        parts.append(f"Pipeline: {config.get('pipeline_type', '?')}")
        td = config.get('target_definition', '')
        if td:
            parts.append(f"Target: {td}")
        parts.append(f"Rows: {config.get('row_count_before', '?')} → {config.get('row_count_after', '?')} "
                      f"(removed: {config.get('rows_removed', 0)})")
        parts.append(f"Split: {config.get('split_strategy', '?')}")

    # Data dictionary (feature names so LLM knows what's available)
    dd = cache_get(file_id, ARTIFACT_DATA_DICTIONARY)
    if dd:
        dd_list = dd if isinstance(dd, list) else dd.get('features', [])
        dd_names = [f.get('Feature_Name', f.get('feature', '?')) for f in dd_list]
        parts.append(f"Data dictionary ({len(dd_list)} features): {', '.join(dd_names[:50])}")
        parts.append("Use get_data_dictionary tool for feature descriptions and details.")

    # Feature list (names + VIF flags only)
    sel_feats = cache_get(file_id, ARTIFACT_SELECTED_FEATURES)
    if sel_feats:
        feat_list = sel_feats if isinstance(sel_feats, list) else sel_feats.get('features', [])
        names = [f.get('feature', '?') for f in feat_list[:40]]
        high_vif = [f.get('feature', '?') for f in feat_list if (f.get('vif') or 0) > 5]
        parts.append(f"Selected features ({len(feat_list)}): {', '.join(names)}")
        if high_vif:
            parts.append(f"High-VIF features (>5): {', '.join(high_vif)}")

    # Available data (so the LLM knows which tools will return data)
    available = cache_list_artifacts(file_id)
    if available:
        parts.append(f"Cached artifacts available: {', '.join(available)}")

    parts.append(f"Current section: {section or 'general'}")
    parts.append("Use the provided tools to fetch detailed pipeline data when needed.")

    return '\n'.join(parts)


# Maximum number of tool-call rounds before forcing a final response
_MAX_TOOL_ROUNDS = 5


@workflow(name="declarai-chat")
def _chat_workflow(user_message: str, context: dict, section: str, history: list,
                   file_id: int = None, model: str = None) -> dict:
    """Core chat workflow with multi-turn tool calling.

    If file_id is provided and Redis has cached artifacts, uses the slim context
    + tool calling approach. Otherwise falls back to the legacy _format_context.
    Supports multiple LLM providers via model_key.
    """
    model_key = model or DEFAULT_MODEL
    model_cfg = get_model_config(model_key)

    # ── Workflow-level tracing attributes ──
    set_span_attr('declarai.section', section or 'general')
    set_span_attr('declarai.model', model_key)
    if file_id is not None:
        set_span_attr('declarai.file_id', file_id)
        set_session_id(f'declarai-file-{file_id}')

    # Build messages array for OpenAI
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    # Decide: tool-calling mode (slim context) vs legacy mode (full context dump)
    use_tools = False
    if file_id is not None:
        available = cache_list_artifacts(file_id)
        if available:
            use_tools = True

    if use_tools:
        slim = _build_slim_context(file_id, section)
        messages.append({
            'role': 'system',
            'content': f'Pipeline context summary (use tools for details):\n\n{slim}',
        })
    elif context:
        context_str = _format_context(context, section)
        messages.append({
            'role': 'system',
            'content': f'The user is currently viewing the following pipeline output '
                       f'(section: {section}):\n\n{context_str}',
        })

    # Add conversation history (last 20 messages to stay within token limits)
    for msg in history[-20:]:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})

    # Add current user message
    messages.append({'role': 'user', 'content': user_message})

    # Tool-calling loop (only for models that support function calling)
    tools = PIPELINE_TOOLS if (use_tools and model_cfg.get('supports_tools')) else None
    total_usage = {}

    for _round in range(_MAX_TOOL_ROUNDS + 1):
        result = _call_llm(messages, model_key, tools=tools)
        _merge_usage(total_usage, result.get('usage', {}))

        choice = result['choices'][0]
        finish_reason = choice.get('finish_reason', '')
        msg_obj = choice.get('message', {})

        # If no tool calls, we're done
        if finish_reason != 'tool_calls' and not msg_obj.get('tool_calls'):
            break

        # Resolve tool calls
        tool_calls = msg_obj.get('tool_calls', [])
        if not tool_calls:
            break

        # Append the assistant message with tool_calls to the conversation
        messages.append(msg_obj)

        # Execute each tool call and append results
        for tc in tool_calls:
            fn = tc.get('function', {})
            tool_name = fn.get('name', '')
            try:
                tool_args = json.loads(fn.get('arguments', '{}'))
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = execute_tool_call(file_id, tool_name, tool_args)
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.get('id', ''),
                'content': tool_result,
            })

        # On the last round, disable tools to force a text response
        if _round >= _MAX_TOOL_ROUNDS - 1:
            tools = None

    # Extract final response
    assistant_message = msg_obj.get('content', '') or ''

    # Cost, tokens, and conversation turns are handled by auto-instrumentation (v0.3.3+).
    # The Conversation panel reads gen_ai.prompt.user (pre-extracted by the SDK) and
    # gen_ai.completion from each LLM span.  No manual stamping needed.

    # Parse action blocks from the AI response
    actions, clean_message = _extract_actions(assistant_message)

    # If the model's entire reply was the action block, synthesize a brief message
    if not clean_message.strip() and actions:
        descs = [a['payload'].get('description', '') for a in actions if a.get('payload')]
        descs = [d for d in descs if d]
        if descs:
            clean_message = 'I\'ve prepared the following operation for you. Review the details below and click **Apply** to execute.'
        else:
            clean_message = 'I\'ve prepared an action for you. Review it below and click **Apply** to execute.'

    response_data = {
        'message': clean_message,
        'usage': total_usage,
    }
    if actions:
        response_data['actions'] = actions

    return response_data


def _merge_usage(total: dict, new: dict):
    """Accumulate token usage across multiple LLM calls."""
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        if key in new:
            total[key] = total.get(key, 0) + new[key]


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantView(APIView):
    """
    POST /api/ai-assistant/chat/
    Body: {
        "message": "user question",
        "context": { ... pipeline section data ... },
        "section": "data_quality|encoding|cv|shap|selected_features|sfs",
        "history": [ {"role": "user"|"assistant", "content": "..."}, ... ]
    }
    """

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            user_message = data.get('message', '').strip()
            context = data.get('context', {})
            section = data.get('section', '')
            history = data.get('history', [])
            file_id = data.get('file_id')  # enables Redis-backed tool calling

            if not user_message:
                return Response(
                    {'error': 'Message is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            model = data.get('model')  # optional model selector

            response_data = _chat_workflow(user_message, context, section, history,
                                           file_id=int(file_id) if file_id else None,
                                           model=model)
            return Response(response_data, status=status.HTTP_200_OK)

        except EnvironmentError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            traceback.print_exc()
            return Response(
                {'error': f'AI Assistant error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            prometa_flush()

@method_decorator(csrf_exempt, name='dispatch')
class AICachePushView(APIView):
    """
    POST /api/ai-assistant/cache/
    Body: {
        "file_id": 123,
        "artifacts": {
            "split_validation": { ... },
            "dq_summary": [ ... ],
            "pipeline_config": { ... },
            ...
        }
    }

    Pushes pipeline artifacts into the Redis cache so the AI assistant
    can retrieve them on demand via tool calls.
    """

    def post(self, request, *args, **kwargs):
        from .cache import cache_put_bulk, ALL_ARTIFACTS

        file_id = request.data.get('file_id')
        artifacts = request.data.get('artifacts', {})

        if not file_id:
            return Response({'status': 'error', 'error': 'file_id is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not artifacts:
            return Response({'status': 'error', 'error': 'artifacts dict is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Filter to known artifact types
        valid = {k: v for k, v in artifacts.items() if k in ALL_ARTIFACTS and v is not None}
        if not valid:
            return Response({'status': 'error', 'error': f'No valid artifact types. Known: {ALL_ARTIFACTS}'},
                            status=status.HTTP_400_BAD_REQUEST)

        success = cache_put_bulk(int(file_id), valid)
        return Response({
            'status': 'success' if success else 'warning',
            'cached': list(valid.keys()),
            'message': 'Artifacts cached' if success else 'Redis unavailable — artifacts not cached',
        })


@method_decorator(csrf_exempt, name='dispatch')
class AIActionExecuteView(APIView):
    """
    POST /api/ai-assistant/execute-action/
    Body: {
        "file_id": 123,
        "action_type": "execute_code" | "update_metadata" | "update_config" | "update_notes",
        "payload": { ... action-specific data ... }
    }
    """

    def post(self, request, *args, **kwargs):
        from .action_executor import dispatch_action

        try:
            file_id = request.data.get('file_id')
            action_type = request.data.get('action_type', '')
            payload = request.data.get('payload', {})

            if not file_id:
                return Response({'status': 'error', 'error': 'file_id is required'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not action_type:
                return Response({'status': 'error', 'error': 'action_type is required'},
                                status=status.HTTP_400_BAD_REQUEST)

            result = dispatch_action(int(file_id), action_type, payload)

            http_status = status.HTTP_200_OK if result.get('status') == 'success' else status.HTTP_400_BAD_REQUEST
            return Response(result, status=http_status)
        finally:
            prometa_flush()


# ---------------------------------------------------------------------------
# Shared helper — extract action blocks from AI-generated text
# ---------------------------------------------------------------------------

def _extract_actions(message: str):
    """Extract <<<ACTION:...>>>...<<<END_ACTION>>> blocks from the AI response.

    Returns (actions_list, cleaned_message) where actions_list is a list of
    parsed action dicts and cleaned_message has the raw blocks removed.

    The regex is intentionally lenient to tolerate common LLM formatting
    variations: 2-3 angle brackets, optional colons, trailing whitespace,
    code-fence wrappers around the JSON payload, etc.

    Also handles **truncated** responses where the model hit its token limit
    and the closing <<<END_ACTION>>> was never emitted.
    """
    import re
    # Match 2-3 angle brackets on each delimiter, optional whitespace/newlines
    pattern = r'<{2,3}\s*ACTION\s*:\s*(\w+)\s*>{2,3}\s*(.*?)\s*<{2,3}\s*/?\s*END_ACTION\s*>{2,3}'
    actions = []
    for match in re.finditer(pattern, message, re.DOTALL):
        action_type = match.group(1)
        payload_str = match.group(2).strip()
        # Strip optional code-fence wrapper (```json ... ```)
        payload_str = re.sub(r'^```(?:json)?\s*', '', payload_str)
        payload_str = re.sub(r'\s*```$', '', payload_str)
        try:
            payload = json.loads(payload_str)
            actions.append({'type': action_type, 'payload': payload})
        except json.JSONDecodeError:
            # If JSON parsing fails, skip this action block
            print(f"[AI] Failed to parse action block: {payload_str[:200]}")
    # Remove action blocks from the visible message
    clean = re.sub(pattern, '', message, flags=re.DOTALL).strip()

    # ── Fallback: truncated action blocks (no END_ACTION) ────────────
    # If no actions were found, the model may have omitted END_ACTION.
    # Try to salvage the action AND preserve any explanation text that
    # appears after the JSON payload (e.g., "What was added: ...").
    if not actions:
        trunc_pattern = r'<{2,3}\s*ACTION\s*:\s*(\w+)\s*>{2,3}\s*([\s\S]*)'
        trunc_match = re.search(trunc_pattern, clean)
        if trunc_match:
            action_type = trunc_match.group(1)
            tail = trunc_match.group(2).strip()
            # Strip optional code-fence wrapper
            tail = re.sub(r'^```(?:json)?\s*', '', tail)
            tail = re.sub(r'\s*```$', '', tail)
            # Try to find a complete JSON object by matching braces
            payload, json_end = _try_parse_truncated_json(tail)
            before_block = clean[:trunc_match.start()].strip()
            if payload is not None:
                actions.append({'type': action_type, 'payload': payload})
                # Preserve explanation text that comes after the JSON payload
                after_json = tail[json_end:].strip() if json_end is not None else ''
                parts = [p for p in (before_block, after_json) if p]
                clean = '\n\n'.join(parts)
            else:
                clean = before_block

    return actions, clean


def _try_parse_truncated_json(text: str):
    """Attempt to extract a valid JSON object from potentially truncated text.

    Scans for the first '{' and finds the matching '}' by counting brace
    depth.  If the text is truncated mid-JSON, tries to repair it by
    closing open strings and appending the missing '}'.

    Returns (payload, end_position) where end_position is the index in
    *text* just past the closing '}' of the extracted JSON, or None if
    parsing failed.  The caller uses end_position to preserve any
    explanation text that follows the JSON payload.
    """
    start = text.find('{')
    if start == -1:
        return None, None

    # First try: brace-counting to find the exact closing brace
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1]), i + 1
                except json.JSONDecodeError:
                    return None, None

    # Fallback: truncated — try closing open strings and braces
    fragment = text[start:]
    # Close any unclosed string
    if fragment.count('"') % 2 == 1:
        fragment += '"'
    # Close open braces
    open_braces = fragment.count('{') - fragment.count('}')
    if open_braces > 0:
        fragment += '}' * open_braces
    try:
        return json.loads(fragment), len(text)
    except json.JSONDecodeError:
        print(f"[AI] Could not salvage truncated action JSON: {fragment[:200]}")
        return None, None


def _format_context(context: dict, section: str) -> str:
    """Format pipeline context into a readable string for the LLM.

    Uses the actual field names produced by the Data_Quality backend and
    the frontend table columns so the LLM can reference concrete numbers.
    """
    parts = []

    def _fmt_val(v):
        if v is None:
            return '-'
        if isinstance(v, float):
            return f'{v:.4f}'
        return str(v)

    if section == 'data_quality':
        summary = context.get('summary', [])
        if summary:
            parts.append(f'Data Quality Summary ({len(summary)} features):\n')
            # Build a compact per-feature table with the real column names
            for row in summary[:50]:  # up to 50 features
                var = row.get('Variable', row.get('variable', row.get('index', '?')))
                vtype = row.get('Variable_Type', '?')
                psi = row.get('PSI')
                csi = row.get('CSI')
                decision = row.get('Datq_Decision', '?')
                model_usage = row.get('MODEL_USAGE', row.get('Model_Usage', 'Yes'))
                # Missing % — may be Train/Test split columns
                miss_tr = row.get('%_Missing_Change_Train', row.get('%_Missing_Value', None))
                miss_te = row.get('%_Missing_Change_Test', None)
                # Distribution stats (Train side)
                mean_tr = row.get('Mean_Change_Train', None)
                std_tr = row.get('STD_Change_Train', None)
                min_tr = row.get('Min_Change_Train', None)
                max_tr = row.get('Max_Change_Train', None)
                skew_tr = row.get('Skewness_Change_Train', None)
                # Alternative shift metrics
                ks = row.get('KS', None)
                jsd = row.get('JSD', None)

                def _fmt(v):
                    if v is None:
                        return '-'
                    if isinstance(v, float):
                        return f'{v:.4f}'
                    return str(v)

                line = f"  {var} [{vtype}]:"
                stability = f"PSI={_fmt(psi)}" if psi is not None else f"CSI={_fmt(csi)}"
                line += f" {stability}, Decision={decision}"
                if miss_tr is not None:
                    line += f", Missing(train)={_fmt(miss_tr)}"
                if miss_te is not None:
                    line += f", Missing(test)={_fmt(miss_te)}"
                if mean_tr is not None:
                    line += f", Mean(train)={_fmt(mean_tr)}"
                if std_tr is not None:
                    line += f", Std(train)={_fmt(std_tr)}"
                if min_tr is not None and max_tr is not None:
                    line += f", Range(train)=[{_fmt(min_tr)}, {_fmt(max_tr)}]"
                if skew_tr is not None:
                    line += f", Skew(train)={_fmt(skew_tr)}"
                if ks is not None:
                    line += f", KS={_fmt(ks)}"
                if jsd is not None:
                    line += f", JSD={_fmt(jsd)}"
                if model_usage and str(model_usage).lower() == 'no':
                    line += ", MODEL_USAGE=No (excluded)"
                parts.append(line)

        purifier = context.get('purifier_summary', {})
        if purifier:
            rows_before = purifier.get('rows_before', '?')
            rows_after = purifier.get('rows_after', '?')
            rows_removed = purifier.get('rows_removed', 0)
            total_cols_dropped = purifier.get('total_columns_dropped', purifier.get('total_dropped', '?'))
            parts.append(f"\n═══ Preprocessing Treatment Effect ═══")
            parts.append(f"  Rows: {rows_before} → {rows_after} ({rows_removed} removed, "
                         f"{round(rows_removed / max(1, rows_before if isinstance(rows_before, (int, float)) else 1) * 100, 1)}% loss)")
            parts.append(f"  Total columns dropped: {total_cols_dropped}")
            # Per-step breakdown
            dropped_by_step = purifier.get('dropped_by_step', [])
            if dropped_by_step:
                parts.append(f"  Purifier steps:")
                for step in dropped_by_step:
                    step_name = step.get('step', '?')
                    cols = step.get('columns', [])
                    rows_rm = step.get('rows_removed', 0)
                    note = step.get('note', '')
                    cols_preview = ', '.join(cols[:10])
                    if len(cols) > 10:
                        cols_preview += f' ... (+{len(cols) - 10} more)'
                    line = f"    - {step_name}: {len(cols)} columns dropped"
                    if rows_rm:
                        line += f", {rows_rm} rows removed"
                    if cols_preview:
                        line += f" [{cols_preview}]"
                    if note:
                        line += f" — {note}"
                    parts.append(line)

        split_val = context.get('split_validation', {})
        if split_val and isinstance(split_val, dict):
            splits = split_val.get('splits', [])
            if splits:
                parts.append(f"\n═══ Train/Test Split Validation ═══")
                for sp in splits:
                    name = sp.get('name', '?')
                    count = sp.get('count', '?')
                    target_mean = sp.get('target_mean', '?')
                    parts.append(f"  {name}: n={count}, target_rate={target_mean}")

        model_usage = context.get('model_usage', {})
        if model_usage:
            excluded = [k for k, v in model_usage.items() if str(v).lower() == 'no']
            if excluded:
                parts.append(f"\nExcluded from model (Model_Usage=No): {', '.join(excluded)}")

    elif section == 'encoding':
        plan = context.get('plan', [])
        if plan:
            parts.append(f'Encoding Plan ({len(plan)} categorical features):')
            for entry in plan[:30]:
                parts.append(f"  - {entry.get('feature', '?')}: "
                             f"LOM={entry.get('user_lom', entry.get('lom', '?'))}, "
                             f"unique={entry.get('nunique', '?')}, "
                             f"strategy={entry.get('fallback_strategy', '?')}")

    elif section == 'cv':
        cv = context.get('cv', {})
        model = context.get('model_info', {})
        if cv:
            parts.append("Cross-Validation Results:")
            parts.append(f"  ROC-AUC (mean ± std): {cv.get('roc_auc_mean', '?')} ± {cv.get('roc_auc_std', '?')}")
            parts.append(f"  PR-AUC (mean ± std): {cv.get('pr_auc_mean', '?')} ± {cv.get('pr_auc_std', '?')}")
            parts.append(f"  Number of folds: {cv.get('n_splits', '?')}")

            # Per-fold breakdown
            folds = cv.get('folds', [])
            if folds:
                parts.append("\n  ── Per-Fold Metrics ──")
                for i, fold in enumerate(folds):
                    parts.append(f"    Fold {i+1}: ROC-AUC={_fmt_val(fold.get('roc_auc'))}, "
                                 f"PR-AUC={_fmt_val(fold.get('pr_auc'))}, "
                                 f"best_iter={fold.get('best_iteration', '?')}")

            # Class balance from PR baseline
            pr_curve = cv.get('pr_curve') or {}
            baseline = pr_curve.get('baseline')
            if baseline is not None:
                parts.append(f"\n  ── Class Balance ──")
                parts.append(f"    Positive class rate (target rate): {baseline:.4f} ({baseline*100:.2f}%)")
                parts.append(f"    Class imbalance ratio: 1:{int(round(1/max(baseline, 1e-9)))}")

            # ROC curve operating points — TPR at key FPR thresholds
            roc_curve_data = cv.get('roc_curve') or {}
            fpr_grid = roc_curve_data.get('fpr', [])
            mean_tpr = roc_curve_data.get('mean_tpr', [])
            if fpr_grid and mean_tpr and len(fpr_grid) == len(mean_tpr):
                parts.append(f"\n  ── ROC Curve Operating Points (mean across folds) ──")
                parts.append(f"    (Read as: at X% false positive rate, we achieve Y% true positive rate)")
                for target_fpr in [0.01, 0.05, 0.10, 0.20, 0.30]:
                    # Find closest index in the fpr grid
                    best_idx = min(range(len(fpr_grid)), key=lambda j: abs(fpr_grid[j] - target_fpr))
                    tpr_at = mean_tpr[best_idx]
                    parts.append(f"    FPR={target_fpr*100:.0f}% → TPR={tpr_at:.4f} ({tpr_at*100:.1f}% of positives caught)")

            # PR curve operating points — Precision at key Recall levels
            recall_grid = pr_curve.get('recall', [])
            mean_prec = pr_curve.get('mean_precision', [])
            if recall_grid and mean_prec and len(recall_grid) == len(mean_prec):
                parts.append(f"\n  ── Precision-Recall Curve Operating Points (mean across folds) ──")
                parts.append(f"    (Read as: to catch X% of positives, we achieve Y% precision)")
                for target_recall in [0.10, 0.25, 0.50, 0.75, 0.90]:
                    best_idx = min(range(len(recall_grid)), key=lambda j: abs(recall_grid[j] - target_recall))
                    prec_at = mean_prec[best_idx]
                    parts.append(f"    Recall={target_recall*100:.0f}% → Precision={prec_at:.4f} ({prec_at*100:.1f}%)")
                # Compute approximate best F1 from the grid
                try:
                    f1_scores = []
                    for j in range(len(recall_grid)):
                        r, p = recall_grid[j], mean_prec[j]
                        if (r + p) > 0:
                            f1_scores.append((2 * p * r / (p + r), r, p, j))
                    if f1_scores:
                        best_f1, best_r, best_p, best_j = max(f1_scores, key=lambda x: x[0])
                        parts.append(f"\n    ** Best F1 score on PR curve: F1={best_f1:.4f} "
                                     f"(Precision={best_p:.4f}, Recall={best_r:.4f})")
                        if baseline is not None:
                            # Approximate threshold: for well-calibrated models, threshold ≈ baseline * precision / (baseline * precision + (1-baseline)*(1-precision))
                            parts.append(f"    ** Approximate optimal threshold for F1: ~{best_r:.3f} recall level "
                                         f"(with target rate {baseline:.4f}, threshold likely near {baseline:.3f}–{min(0.5, baseline*3):.3f})")
                except Exception:
                    pass

            # Micro-averaged PR (pooled across all folds)
            micro = cv.get('pr_curve_micro') or {}
            if micro.get('ap') is not None:
                parts.append(f"\n  ── Micro-Averaged PR (pooled across folds) ──")
                parts.append(f"    Average Precision (micro): {micro['ap']:.4f}")

        if model:
            parts.append(f"\n  ── Model Info ──")
            parts.append(f"  Model type: {model.get('model_type', '?')}")
            parts.append(f"  Number of features: {model.get('features', '?')}")
            parts.append(f"  Validation AUC (hold-out): {model.get('score', '?')}")

    elif section == 'shap':
        features = context.get('features', [])
        if features:
            parts.append(f'SHAP Beeswarm — top {len(features)} features by |impact|:')
            for f in features[:20]:
                parts.append(f"  - {f.get('feature', '?')}: "
                             f"|impact|={f.get('impact', '?')}, "
                             f"signed_impact={f.get('signed_impact', '?')}")

    elif section == 'selected_features':
        features = context.get('features', [])
        if features:
            parts.append(f'Selected Features ({len(features)} total, sorted by Combined Score):')
            for f in features[:30]:
                parts.append(f"  - {f.get('feature', '?')}: "
                             f"combined_score={f.get('combined_score', '?')}, "
                             f"SHAP_percentile={f.get('shap_percentile', '?')}, "
                             f"Gain_percentile={f.get('gain_percentile', '?')}, "
                             f"VIF={f.get('vif', '?')}, "
                             f"usage={f.get('usage', 'keep')}")
        # VIF decomposition (pairwise correlations the user has inspected)
        vif_decomp = context.get('vif_decomposition', {})
        if vif_decomp:
            parts.append(f'\n═══ VIF Decomposition (pairwise correlations) ═══')
            for feat_name, decomp in vif_decomp.items():
                parts.append(f'  {feat_name} (overall VIF={_fmt_val(decomp.get("vif"))}):')
                for c in decomp.get('top_correlations', []):
                    parts.append(f"    ↔ {c.get('feature','?')}: |corr|={_fmt_val(c.get('correlation'))}, "
                                 f"signed_r={_fmt_val(c.get('signed_correlation'))}, "
                                 f"vif_drop={_fmt_val(c.get('vif_drop'))}")

    elif section == 'sfs':
        # ── SFS Configuration (stopping criteria, etc.) ──
        sfs_cfg = context.get('sfs_config', {})
        if sfs_cfg:
            parts.append('═══ SFS Configuration ═══')
            sc = sfs_cfg.get('stopping_criteria', {})
            metrics_cfg = sc.get('metrics', [])
            if metrics_cfg:
                for m in metrics_cfg:
                    parts.append(f"  Stopping metric: {m.get('metric', '?')}, "
                                 f"pct_change threshold: {m.get('pct_change', '?')}%")
            parts.append(f"  Min features: {sc.get('min_features', '?')}")
            parts.append(f"  Max features: {sc.get('max_features', '?')}")
            parts.append(f"  Top-K candidates per step: {sfs_cfg.get('top_k', '?')}")
            cut_step = sfs_cfg.get('backward_cut_step')
            if cut_step is not None:
                parts.append(f"  Backward cut step (user-selected): {cut_step} "
                             f"({sfs_cfg.get('backward_cut_features', '?')} features remaining)")
            if sfs_cfg.get('stopped_early'):
                parts.append(f"  ⚠ SFS was stopped early by the user (partial results)")
        # ── SFS Results ──
        for direction in ['forward', 'backward', 'forward_from_backward']:
            steps = context.get(direction, [])
            if steps:
                last_step = steps[-1] if steps else {}
                remaining = last_step.get('remaining', last_step.get('selected_features', []))
                remaining_count = len(remaining) if isinstance(remaining, list) else remaining
                parts.append(f'\n{direction.replace("_", " ").title()} Selection '
                             f'({len(steps)} steps, {remaining_count} features remaining after last step):')
                for s in steps[:20]:
                    feat = s.get('feature_name', s.get('feature', '?'))
                    rem = s.get('remaining', '?')
                    if isinstance(rem, list):
                        rem = len(rem)
                    parts.append(f"  Step {s.get('step', '?')}: "
                                 f"{feat} — remaining={rem}, "
                                 f"CV ROC-AUC={s.get('cv_roc_auc', s.get('roc_auc', '?'))}, "
                                 f"Test ROC-AUC={s.get('test_roc_auc', '?')}, "
                                 f"PR-AUC={s.get('cv_pr_auc', s.get('pr_auc', '?'))}, "
                                 f"Model PSI={s.get('model_psi', '?')}")

    else:
        # 'general' or unknown section: render ALL available data keys using
        # the same formatters as specific sections (cumulative context).
        # ── Data preview if present ──
        data_preview = context.get('data_preview', {})
        if data_preview:
            parts.append(f"Dataset: {data_preview.get('file_name', '?')}")
            parts.append(f"  Total rows: {data_preview.get('total_rows', '?')}")
            parts.append(f"  Total columns: {data_preview.get('total_columns', '?')}")
            cols = data_preview.get('columns', [])
            if cols:
                parts.append(f"  Columns: {', '.join(str(c) for c in cols[:60])}")
        # ── Data dictionary if present (top-level, from declaration) ──
        dd = context.get('data_dictionary', [])
        if dd and isinstance(dd, list):
            parts.append(f"\nData Dictionary ({len(dd)} features):")
            for feat in dd[:40]:
                fname = feat.get('Feature_Name', '?')
                dtype = feat.get('Data_Type', '?')
                lom = feat.get('Level_of_Measurement', '?')
                usage = feat.get('Model_Usage_YN', '?')
                desc = feat.get('Feature_Description') or ''
                parts.append(f"  {fname}: dtype={dtype}, LoM={lom}, usage={usage}" + (f", desc={desc}" if desc else ""))
        # ── Data Quality summary if present ──
        summary = context.get('summary', [])
        if summary:
            parts.append(f'Data Quality Summary ({len(summary)} features):\n')
            for row in summary[:30]:
                var = row.get('Variable', row.get('variable', '?'))
                vtype = row.get('Variable_Type', '?')
                psi = row.get('PSI')
                decision = row.get('Datq_Decision', '?')
                parts.append(f"  {var}: type={vtype}, PSI={_fmt_val(psi)}, decision={decision}")
        purifier = context.get('purifier_summary', {})
        if purifier:
            parts.append(f"\nPurifier Summary: rows {purifier.get('rows_before','?')}→{purifier.get('rows_after','?')} "
                         f"(removed {purifier.get('rows_removed','?')}), cols dropped={purifier.get('total_columns_dropped','?')}")
        # ── CV results if present ──
        cv = context.get('cv', {})
        if cv:
            parts.append(f"\nCV Results: ROC-AUC={_fmt_val(cv.get('roc_auc_mean'))}±{_fmt_val(cv.get('roc_auc_std'))}, "
                         f"PR-AUC={_fmt_val(cv.get('pr_auc_mean'))}±{_fmt_val(cv.get('pr_auc_std'))}")
            pr_curve = cv.get('pr_curve') or {}
            baseline = pr_curve.get('baseline')
            if baseline is not None:
                parts.append(f"  Target rate: {baseline:.4f} ({baseline*100:.2f}%)")
        model_info = context.get('model_info', {})
        if model_info:
            parts.append(f"  Model: {model_info.get('model_type','?')}, features={model_info.get('features','?')}, score={_fmt_val(model_info.get('score'))}")
        # ── Selected features if present ──
        sel_feats = context.get('selected_features', [])
        if sel_feats:
            parts.append(f"\nSelected Features ({len(sel_feats)} total):")
            for f in sel_feats[:15]:
                parts.append(f"  {f.get('feature','?')}: combined={_fmt_val(f.get('combined_score'))}, VIF={_fmt_val(f.get('vif'))}")
        # ── VIF decomposition (pairwise correlations the user has inspected) ──
        vif_decomp = context.get('vif_decomposition', {})
        if vif_decomp:
            parts.append(f'\n═══ VIF Decomposition (pairwise correlations) ═══')
            for feat_name, decomp in vif_decomp.items():
                parts.append(f'  {feat_name} (overall VIF={_fmt_val(decomp.get("vif"))}):')
                for c in decomp.get('top_correlations', []):
                    parts.append(f"    ↔ {c.get('feature','?')}: |corr|={_fmt_val(c.get('correlation'))}, "
                                 f"signed_r={_fmt_val(c.get('signed_correlation'))}, "
                                 f"vif_drop={_fmt_val(c.get('vif_drop'))}")
        # ── SFS config if present ──
        sfs_cfg = context.get('sfs_config', {})
        if sfs_cfg:
            sc = sfs_cfg.get('stopping_criteria', {})
            metrics_cfg = sc.get('metrics', [])
            parts.append(f"\n═══ SFS Configuration ═══")
            for m in metrics_cfg:
                parts.append(f"  Stopping: {m.get('metric','?')}, pct_change threshold={m.get('pct_change','?')}%")
            parts.append(f"  Min features: {sc.get('min_features','?')}, Max features: {sc.get('max_features','?')}")
            parts.append(f"  Top-K: {sfs_cfg.get('top_k','?')}")
            cut_step = sfs_cfg.get('backward_cut_step')
            if cut_step is not None:
                parts.append(f"  Backward cut step: {cut_step} ({sfs_cfg.get('backward_cut_features','?')} features)")
        # ── SFS results if present ──
        sfs = context.get('sfs', {})
        if sfs:
            for direction in ['forward', 'backward', 'forward_from_backward']:
                steps = sfs.get(direction, [])
                if steps:
                    last_step = steps[-1] if steps else {}
                    remaining = last_step.get('remaining', last_step.get('selected_features', []))
                    rem_count = len(remaining) if isinstance(remaining, list) else remaining
                    parts.append(f"\nSFS {direction.replace('_',' ').title()} ({len(steps)} steps, {rem_count} features after last step)")
        # ── Encoding plan if present ──
        enc = context.get('encoding_plan', [])
        if enc and isinstance(enc, list) and len(enc) > 0:
            parts.append(f"\nEncoding Plan ({len(enc)} categorical features)")
        # Fallback: if nothing specific was rendered, dump JSON summary
        if len(parts) == 0:
            try:
                ctx_str = json.dumps(context, indent=2, default=str)
                parts.append(ctx_str[:3000])
            except Exception:
                parts.append(str(context)[:3000])

    # ── Always append pipeline configuration if present ──
    pipeline_cfg = context.get('pipeline_config', {})
    if pipeline_cfg:
        parts.append(f"\n═══ Pipeline Configuration ═══")
        parts.append(f"  Pipeline type: {pipeline_cfg.get('pipeline_type', '?')}")
        parts.append(f"  Current step: {pipeline_cfg.get('current_step', '?')}")
        parts.append(f"  Detailed step: {pipeline_cfg.get('detailed_step', '?')}")
        parts.append(f"  Preprocessing initiated: {pipeline_cfg.get('preprocessing_initiated', False)}")
        parts.append(f"  Modeling available: {pipeline_cfg.get('modeling_available', False)}")

        # ── Target Definition (business goal) ──
        target_def = pipeline_cfg.get('target_definition', '').strip()
        if target_def:
            parts.append(f"\n═══ TARGET DEFINITION (Business Goal) ═══")
            parts.append(f"  The user defined the prediction target as:")
            parts.append(f"  \"{target_def}\"")
            parts.append(f"  → Use this business context to ground ALL your analysis and recommendations.")

        steps = pipeline_cfg.get('selected_purifier_steps', [])
        if steps:
            parts.append(f"  Selected purifier steps ({len(steps)}):")
            for s in steps:
                parts.append(f"    • {s}")

        split = pipeline_cfg.get('split_strategy', '?')
        split_details = pipeline_cfg.get('split_details', {})
        if split == 'oot':
            parts.append(f"  Split strategy: Out-of-Time (OOT)")
            parts.append(f"    Mode: {split_details.get('mode', '?')}, "
                         f"OOT%: {split_details.get('oot_percent', '?')}, "
                         f"Date column: {split_details.get('date_column', '?')}, "
                         f"Cutoff: {split_details.get('cutoff', '?')}")
        else:
            parts.append(f"  Split strategy: Random")
            parts.append(f"    OOS%: {split_details.get('oos_percent', '?')}")

        rows_b = pipeline_cfg.get('rows_before', 0)
        rows_a = pipeline_cfg.get('rows_after', 0)
        rows_rm = pipeline_cfg.get('rows_removed', 0)
        if rows_b:
            pct = round(rows_rm / max(1, rows_b) * 100, 1)
            parts.append(f"  Rows: {rows_b} → {rows_a} ({rows_rm} removed, {pct}% loss)")

        total_dropped = pipeline_cfg.get('total_columns_dropped', 0)
        parts.append(f"  Total columns dropped: {total_dropped}")

        dropped_by_step = pipeline_cfg.get('dropped_by_step', [])
        if dropped_by_step:
            parts.append(f"  Columns dropped per purifier step:")
            for step_info in dropped_by_step:
                sname = step_info.get('step', '?')
                cols = step_info.get('columns', [])
                rows_rm_s = step_info.get('rows_removed', 0)
                cols_preview = ', '.join(cols[:8])
                if len(cols) > 8:
                    cols_preview += f' ... (+{len(cols) - 8} more)'
                line = f"    - {sname}: {len(cols)} cols"
                if rows_rm_s:
                    line += f", {rows_rm_s} rows removed"
                if cols_preview:
                    line += f" [{cols_preview}]"
                parts.append(line)

        exclusions = pipeline_cfg.get('model_usage_exclusions', [])
        if exclusions:
            parts.append(f"  Features excluded (Model_Usage=No): {', '.join(exclusions)}")

        # ── Data Dictionary (raw metadata per feature) ──
        dd = pipeline_cfg.get('data_dictionary', [])
        if dd:
            # Build a lookup for feature descriptions (used also in per-feature DQ lines above)
            dd_desc_map = {f.get('Feature_Name', ''): f.get('Feature_Description') for f in dd}
            has_any_desc = any(v for v in dd_desc_map.values())
            parts.append(f"\n═══ Data Dictionary ({len(dd)} features) ═══")
            if has_any_desc:
                parts.append("  (Business descriptions from uploaded data dictionary)")
            for feat in dd:
                fname = feat.get('Feature_Name', '?')
                dtype = feat.get('Data_Type', '?')
                lom = feat.get('Level_of_Measurement', '?')
                uniq = feat.get('Unique_Values', '?')
                miss = feat.get('Missing_Ratio', '?')
                mode_r = feat.get('Mode_Ratio', '?')
                usage = feat.get('Model_Usage_YN', '?')
                desc = feat.get('Feature_Description')
                line = f"  {fname}: type={dtype}, LOM={lom}, unique={uniq}, missing={miss}%, mode_ratio={mode_r}%, usage={usage}"
                if desc:
                    line += f" | DESCRIPTION: \"{desc}\""
                parts.append(line)

        # ── Encoding Plan ──
        enc = pipeline_cfg.get('encoding_plan', [])
        if enc:
            parts.append(f"\n═══ Encoding Plan ({len(enc)} categorical features) ═══")
            for e in enc:
                parts.append(f"  {e.get('feature', '?')}: LOM={e.get('lom', '?')}, "
                             f"unique={e.get('nunique', '?')}, "
                             f"strategy={e.get('strategy', '?')}, "
                             f"needs_ranking={e.get('needs_ranking', False)}")

        # ── Shared helpers for stats formatting ──
        num_metrics = ['Mean', 'Median', 'Std', 'Min', 'Max', 'Skewness', 'Kurtosis',
                       'Q01', 'Q05', 'Q25', 'Q75', 'Q95', 'Q99', 'Missing_Pct', 'Unique', 'N']
        cat_metrics = ['Mode', 'Mode_Pct', 'Num_Categories', 'Missing_Pct', 'Unique', 'N']

        def _render_stats_comparison(before_list, after_list, title, label_before='before', label_after='after'):
            """Render a before/after stats comparison block for a list of features."""
            b_map = {s.get('Feature_Name'): s for s in before_list} if before_list else {}
            a_map = {s.get('Feature_Name'): s for s in after_list} if after_list else {}
            all_f = list(dict.fromkeys(
                [s.get('Feature_Name') for s in (before_list or [])] +
                [s.get('Feature_Name') for s in (after_list or [])]
            ))
            if not all_f:
                return
            parts.append(f"\n═══ {title} ({len(all_f)} features) ═══")
            parts.append(f"  (Format: metric={label_before}/{label_after})")
            for fname in all_f:
                b = b_map.get(fname, {})
                a = a_map.get(fname, {})
                dtype = b.get('Data_Type') or a.get('Data_Type', '?')
                use_m = num_metrics if dtype == 'numeric' else cat_metrics
                line = f"  {fname} [{dtype}]:"
                m_parts = []
                for m in use_m:
                    bv = b.get(m)
                    av = a.get(m)
                    if bv is None and av is None:
                        continue
                    m_parts.append(f"{m}={_fmt_val(bv)}/{_fmt_val(av)}")
                if m_parts:
                    line += ' ' + ', '.join(m_parts)
                else:
                    if fname in b_map and fname not in a_map:
                        line += ' [DROPPED by preprocessing]'
                    else:
                        line += ' [no stats]'
                parts.append(line)

        # ── Per-Step Before/After Stats (e.g. outlier cleaning) ──
        step_stats = pipeline_cfg.get('preprocessing_step_stats') or []
        for ss in step_stats:
            step_name = ss.get('step', 'Unknown step')
            sb = ss.get('stats_before') or []
            sa = ss.get('stats_after') or []
            extra = ''
            qr = ss.get('quantile_range')
            if qr and isinstance(qr, list) and len(qr) == 2:
                extra = f' [{qr[0]*100:.0f}%-{qr[1]*100:.0f}%]'
            _render_stats_comparison(
                sb, sa,
                title=f"Before/After {step_name}{extra}",
                label_before=f'before {step_name}',
                label_after=f'after {step_name}',
            )

        # ── Overall Before/After Preprocessing Feature Stats ──
        stats_before = pipeline_cfg.get('feature_stats_before') or []
        stats_after = pipeline_cfg.get('feature_stats_after') or []
        if stats_before or stats_after:
            _render_stats_comparison(
                stats_before, stats_after,
                title='Before/After Entire Preprocessing',
                label_before='raw data',
                label_after='after all preprocessing',
            )

        # ── Pipeline Commentary Notes (user annotations) ──
        notes = pipeline_cfg.get('pipeline_notes', {})
        active_notes = {k: v for k, v in notes.items() if v and str(v).strip()}
        if active_notes:
            parts.append(f"\n═══ User Pipeline Notes ═══")
            for position, content in active_notes.items():
                label = position.replace('_', ' ').title()
                parts.append(f"  [{label}]: {content}")

    return '\n'.join(parts) if parts else json.dumps(context, default=str)[:3000]


# ---------------------------------------------------------------------------
# Model list endpoint
# ---------------------------------------------------------------------------

class AIModelListView(APIView):
    """
    GET /api/ai-assistant/models/
    Returns available LLM models for the frontend selector.
    """

    def get(self, request, *args, **kwargs):
        return Response({
            'models': list_models(),
            'default': DEFAULT_MODEL,
        })
