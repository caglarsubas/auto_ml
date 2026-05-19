"""
AI Assistant endpoint — proxies user questions + pipeline context to OpenAI GPT-5.5
and returns advisory, insight-rich responses.
"""
import json
import os
import re as _re
import traceback
from typing import Optional

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .prometa_config import (
    workflow, agent, tool, flush as prometa_flush,
    set_span_attr, set_session_id, set_customer_id, set_request_model,
    model_route, plan_generate,
)
from .tool_definitions import PIPELINE_TOOLS
from .tool_executor import execute_tool_call, _load_skill_traced
from .skill_registry import get_skill
from .cache import cache_list_artifacts
from .model_registry import (
    get_model_config, list_models, DEFAULT_MODEL,
    call_openai, call_engine, MODEL_REGISTRY,
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
• The catalog has EXACTLY 34 numbered options (IDs 1..34) drawn from these
  ten transform families:
    - col_dedup, row_dedup, zero_var_drop, perfect_corr_drop  (standalone toggles)
    - corr_drop                  (5 thresholds: 0.95, 0.90, 0.85, 0.80, 0.75)
    - sparsity_drop              (6 thresholds: 0.99, 0.95, 0.90, 0.85, 0.80, 0.75)
    - missing_drop               (6 thresholds: 0.99, 0.95, 0.90, 0.85, 0.80, 0.75)
    - combined_drop              (6 thresholds: 0.99, 0.95, 0.90, 0.85, 0.80, 0.75)
      [combined = max(zero_ratio, miss_ratio); drops cols at-or-above threshold]
    - outlier_quantile_clip      (3 quantile pairs: [0.01-0.99], [0.05-0.95], [0.10-0.90])
    - cat_outlier_merge          (4 thresholds: 0.001, 0.005, 0.01, 0.05)
  Within each parametric group ONLY ONE option may be selected at a time
  (UI radio-style mutual exclusion).  Standalone options never disable
  each other.
• Do NOT invent step names from generic ML toolkits — only the kinds listed
  above exist in this catalog.  Use the ``get_purifier_options`` tool to
  fetch the canonical IDs, labels, and thresholds whenever the user asks
  what's available, what a step does, or asks you to set/change a specific
  purifier behavior.
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

═══ DOMAIN SKILLS (invoke_skill / get_skill_file tools) ═══
You have access to bundled domain-knowledge skills via two tools:
• ``invoke_skill(skill_name)`` — returns the skill's main playbook PLUS a
  listing of supplementary files (references, scripts, templates).
• ``get_skill_file(skill_name, path)`` — returns the contents of one of those
  supplementary files (e.g., ``references/feature_engineering_best_practices.md``,
  ``scripts/feature_engineering_pipeline.py``).  Only call this if you actually
  need the deeper material; the main playbook is usually enough.

WHEN TO INVOKE A SKILL:
• ``feature-engineering`` — Call this skill BEFORE proposing or executing any
  feature-engineering action (creating new columns, ratios, aggregations,
  WOE/IV bins, RFM, velocity features, etc.).  The skill ships authoritative
  patterns by domain (banking/credit, fraud, telecom, insurance, trading,
  healthcare) and a leakage-prevention checklist.  After receiving the skill
  body, ground your suggestions in the patterns it lists and cite the
  domain-specific section you're applying.  Use ``get_skill_file`` when you
  need a longer reference or an example implementation script.

GENERAL RULES:
• A single ``invoke_skill`` call per user turn is enough — its content stays
  in the conversation for the rest of the multi-turn loop.
• Prefer ``get_skill_file`` over speculating; the file you ask for is small
  and bounded.  If the user explicitly asks for a different methodology,
  follow the user.
• Prefer skills over your own intuition when they conflict.

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

Supported keys:
• model_usage (with column + "Yes"/"No") — exclude/include a column from modeling.
• feature_usage (with column + "keep"/"drop", optional reason) — set the Selected
  Features table's per-feature Keep/Drop flag.  Dropped features are passed as
  `excluded_features` to SFS but the column STAYS in the dataset and downstream
  modeling artifacts (selected_features, shap_details, encoding_plan) remain valid.
  Example: {"key": "feature_usage", "column": "Var_3", "value": "drop", "reason": "VIF=9.39"}
• preprocessing_options, split_strategy, split_date_column, split_cutoff, algorithm

─── ACTION TYPE 4: set_ordinal_ranking ───
Record the rank order of distinct category values for ordinal-labelled features.
This is the dedicated follow-through path for an ordinal LoM change — it tells the
encoding pipeline HOW to convert the categories into a monotonic integer scale.

<<<ACTION:set_ordinal_ranking>>>
{"updates": [{"column": "Var_36", "ranking": ["0", "1", "2", "3", "8", "L", "Others"]}, {"column": "Var_2", "ranking": ["A", "P", "R"]}], "description": "Reflect risk severity progression for account-status codes."}
<<<END_ACTION>>>

Rules for set_ordinal_ranking:
• `ranking` must be a list of >= 2 unique string values, each value appearing exactly once.
• Each entry covers ONE feature; batch multiple features in a single updates[] array.
• Values are matched as strings against the column's distinct categories at encoding time.
• Do NOT use execute_code to "manually map" ordinal categories with df[col].map({...}) —
  that bypasses the encoding pipeline, breaks the encoding report, and produces a column
  the modeling step can't trace.  Always use set_ordinal_ranking instead.

─── ACTION TYPE 5: start_sfs ───
Initiate Sequential Feature Selection.  This is the ONLY supported way for you to
actually kick off SFS — never claim "SFS started / triggered / initiated" in your
chat reply without emitting this action.  The action mirrors the user clicking the
"Start SFS" button: it populates the SFS form fields (methods, stopping criteria,
n_jobs, top_k, per-feature drop flags) and starts the engine.

<<<ACTION:start_sfs>>>
{"methods": ["backward"], "stopping_criteria": {"metrics": [{"metric": "roc_auc", "pct_change": 1.0}], "min_features": 5, "max_features": 15}, "excluded_features": ["Var_3"], "n_jobs": 3, "top_k": 5, "description": "Start backward SFS, excluding Var_3 (VIF=9.39)"}
<<<END_ACTION>>>

Rules for start_sfs:
• `methods`: non-empty list drawn from {"forward", "backward"}.  Use ["backward"]
  alone for redundancy/multicollinearity pruning, ["forward"] for greedy build-up,
  or both for forward-after-backward chaining.
• `stopping_criteria.metrics`: at least one of {"roc_auc", "pr_auc"} with a
  `pct_change` threshold (e.g. 1.0 = stop when % change in CV metric drops below 1%).
• `stopping_criteria.min_features` / `max_features`: hard bounds on the resulting
  feature subset size.
• `excluded_features`: features the SFS engine should skip entirely — equivalent
  to setting feature_usage='drop' via update_config.  When you want SFS to skip
  a feature, prefer the update_config feature_usage path so the Selected Features
  UI also reflects the drop; use this list only as a redundant safety net.
• `n_jobs` / `top_k`: parallel worker count (1–16) and top-K CV candidates
  per step (1–50).  Sensible defaults: n_jobs=3, top_k=5.

─── ACTION TYPE 6: start_data_purifier ───
Kick off the preprocessing/data-purifier step (the FIRST run-step in the pipeline).
This is the dedicated path to fire the "Run Preprocessing" button.  It mirrors the
manual click exactly: applies the user's selected purifier checkboxes + chosen
train/test split, produces the `processed_file` that all downstream steps consume.

<<<ACTION:start_data_purifier>>>
{"purifier_options": [1, 2, 5, 7], "split": {"strategy": "random", "percent": 25}, "description": "Run preprocessing with low-variance pruning + missing-value imputation, 25% random OOS"}
<<<END_ACTION>>>

Rules for start_data_purifier:
• `purifier_options`: optional list of integer IDs (1–34) matching the
  preprocessing checkboxes.  Omit or pass [] to use whatever is currently
  selected in the UI (the SharedService cache).  Invalid IDs are dropped.
• MAPPING USER INTENT → IDs: when the user describes a purifier behavior
  in natural language (e.g. "set outlier interval to 0.05/0.95", "drop
  columns with >=95% missing", "add the 0.85 correlation cutoff"), CALL
  ``get_purifier_options`` FIRST to look up the matching integer ID, then
  emit start_data_purifier with that exact ID.  Never guess IDs from
  memory — the catalog is authoritative.  Use the optional ``kind`` filter
  to narrow the catalog (e.g. kind='outlier_quantile_clip' for the three
  numeric outlier options).
• `split.strategy`: 'random' or 'oot'.  When 'oot', `split.date_column` is
  REQUIRED and `split.cutoff` (ISO datetime) is optional (cutoff mode vs
  percent mode).  Omit `split` entirely to fall back to the form's current values.
• Pre-conditions you MUST check via tool calls before firing:
  - file_id is set (data uploaded)
  - data dictionary has been reviewed (target column flagged, IDs / datetimes
    excluded via model_usage='No')
• Don't auto-fire after every config tweak — only when the user explicitly
  asks "run preprocessing" / "start the purifier" / "preprocess the data".

─── ACTION TYPE 6b: update_purifier_selection ───
EDIT the Data-Purifier checkbox UI WITHOUT running the pipeline.  Use this
when the user is THINKING about, REVIEWING, or REORGANIZING the purifier
setup — when they want to see the new checkbox state before deciding to
run.  Compared to start_data_purifier, this action is the "preview" sibling:
patch the form, let the user click Run Preprocessing themselves.

Two payload forms — pick whichever is more natural for the user's intent:

WHOLESALE form (you know the exact final option set):
<<<ACTION:update_purifier_selection>>>
{"purifier_options": [1, 2, 3, 4, 7, 23, 28, 32], "description": "Consolidate IDs 11+17 into ID 23 (mathematically equivalent, prevents threshold drift)"}
<<<END_ACTION>>>

DIFF form (incremental tweak — add and/or remove specific IDs):
<<<ACTION:update_purifier_selection>>>
{"add": [23], "remove": [11, 17], "description": "Replace separate sparsity (ID 11) + missing (ID 17) drops with combined-drop (ID 23) at the same 0.95 threshold"}
<<<END_ACTION>>>

Rules for update_purifier_selection:
• Choose EXACTLY ONE form: `purifier_options` (wholesale) XOR `add`/`remove` (diff).
  Mixing the two returns an error.
• Group conflicts are validated on the wholesale form: only ONE member per
  group (corr_drop / sparsity_drop / missing_drop / combined_drop /
  outlier_num / outlier_cat) may be selected.  If you violate this you get
  a structured error listing the conflicting group + IDs — fix it and
  retry on the next turn.
• `add`/`remove` may not name the same ID twice — that returns an error.
• Empty wholesale list `[]` clears all selections (legitimate use case
  when the user says "clear the purifier selection").
• MAPPING USER INTENT: same rule as start_data_purifier — call
  ``get_purifier_options`` FIRST when the user describes purifier behavior
  in natural language, then emit with the catalog-authoritative IDs.

WHEN TO USE update_purifier_selection vs start_data_purifier — DECISION RULE:
  • User says "run preprocessing", "start the purifier", "preprocess the
    data", "go ahead and run" → fire start_data_purifier (one-shot apply +
    run).
  • User says "change the options to…", "consolidate these steps",
    "swap 11+17 for 23", "let's review the purifier setup", "tweak the
    selection", "what if we add…", or you (the AI) are PROACTIVELY
    proposing a checkbox change → fire update_purifier_selection.  The user
    can then click Run themselves OR ask you to run it in the next turn.
  • When in doubt, prefer update_purifier_selection — it is safer (no
    surprise pipeline runs) and the user can always say "now run it"
    in the next turn.

─── ACTION TYPE 7: apply_encoding ───
Apply the encoding plan and produce the encoded file that modeling consumes.
This is the dedicated path to fire the "Apply Encoding" button.  Encoding
converts categorical features to numeric form per the plan you've reviewed —
nominal→one-hot/label, ordinal→ordinal-rank-encoded, etc.

<<<ACTION:apply_encoding>>>
{"use_native": true, "description": "Apply encoding plan with native library (LightGBM-friendly)"}
<<<END_ACTION>>>

Rules for apply_encoding:
• `use_native`: optional boolean, default true.  True = native encoding library
  (preserves type info for boosting algorithms); false = sklearn fallback.
• Pre-conditions you MUST verify via tool calls (especially get_encoding_plan)
  before firing:
  - processed_file exists (data purifier has run)
  - encoding plan has been analyzed (plan length > 0)
  - EVERY feature with needs_ranking=true has a non-empty `ranking` array.
    If any ordinal feature lacks a ranking, fire set_ordinal_ranking FIRST
    (next turn) and DEFER apply_encoding — otherwise the encoding pipeline
    silently downgrades to label_encoding and the ordinal signal is lost.
• Only fire on explicit user request ("apply encoding", "run encoding",
  "encode the categoricals").

─── ACTION TYPE 8: start_modeling ───
Train the chosen algorithm on the encoded file and produce modeling artifacts
(selected features, SHAP details, ROC-AUC/PR-AUC metrics, training data
snapshot for SFS).  This is the dedicated path to fire the "Start Modeling"
button — the bottom-left button in the pipeline UI.

Before v2.26.0 you would tell users "I cannot 'start' the modeling engine
directly (that is a button in your UI)".  That is no longer true.  Use this
action when the user asks to start modeling.

<<<ACTION:start_modeling>>>
{"algorithm": "lightgbm", "encoding_use_native": true, "description": "Start modeling with LightGBM"}
<<<END_ACTION>>>

Rules for start_modeling:
• `algorithm`: optional string.  When provided, the frontend sets
  selectedAlgorithm to it before firing.  Omit to use the form's current value.
• `encoding_use_native`: optional boolean, default true.
• Pre-conditions you MUST verify via tool calls before firing:
  - file_id is set
  - processed_file exists (data purifier has run)
  - encoding has been applied OR the encoding plan is fully ready (every
    needs_ranking feature has a ranking; if not, run set_ordinal_ranking +
    apply_encoding first across multiple turns)
  - Model_Usage_YN has been reviewed for IDs / timestamps / leakage columns
    (you should have already proposed update_config model_usage='No' for any
    AppID / Application_Datetime / Created_At type columns).  If you haven't,
    do that FIRST and defer start_modeling to the next turn.
• Only fire on explicit user request ("start modeling", "run modeling",
  "train the model").  Don't auto-chain after preprocessing/encoding.

─── ACTION TYPE 9: update_notes ───
Add, edit, or delete pipeline commentary notes at specific positions.

<<<ACTION:update_notes>>>
{"action": "add", "position": "after_data_dictionary", "content": "AI recommendation: 3 derived features created based on domain knowledge analysis.", "description": "Add note after data dictionary"}
<<<END_ACTION>>>

Valid positions: after_data_preview, after_data_dictionary, after_preprocessing_config,
after_purifier_summary, after_data_quality, after_encoding, after_modeling_results, after_sfs
Actions: add, edit, delete

═══ PROCEDURAL CHAINING — PIPELINE-FLOW RULES YOU MUST FOLLOW ═══

The pipeline UI enforces certain dependent steps that the analyst would otherwise have
to click through manually.  When you change a parameter that triggers a follow-up step,
YOU are responsible for completing the chain — do NOT leave the pipeline in a half-
configured state that requires the user to finish your work.

── RULE 1: LoM = ordinal MUST be followed by set_ordinal_ranking ──
Whenever you set a feature's `Level_of_Measurement` to `ordinal` via update_metadata,
the encoding plan immediately flips its `needs_ranking` flag to true and the UI starts
rendering a "Set Ranking" button next to that feature.  Without a ranking the encoding
step silently downgrades to label_encoding and the ordinal signal you intended is
LOST — the boosting model can't learn the monotonic relationship.

Required behaviour:
  1. In the SAME turn (or at the very latest the next turn), emit a set_ordinal_ranking
     action covering every feature whose LoM you just flipped to ordinal.
  2. Inspect each feature's actual distinct category values BEFORE proposing a ranking.
     Call `get_encoding_plan` — the response includes a `unique_values=[...]` list and
     any existing `ranking=[...]`.  If you already have the encoding plan in the slim
     context, read it from there instead of re-fetching.
  3. Propose a ranking based on the SEMANTICS of the category strings, not alphabetic
     order.  Examples of good orderings:
       • Risk-severity codes: ["Active", "Past_Due_30", "Past_Due_60", "Charged_Off"]
       • Education levels: ["None", "High_School", "Bachelor", "Master", "PhD"]
       • Account-status: ["0", "1", "2", "3", "8", "L", "Others"] (numeric → letters → catch-all)
  4. ALWAYS apply your best-guess ranking IMMEDIATELY via set_ordinal_ranking — do not
     wait for user confirmation before applying.  The user is reading your chat reply
     while the pipeline UI updates live; an unset ranking is a worse default than an
     informed guess.
  5. In the SAME chat reply, ask the user a short confirmation question — "I ranked
     Var_36 as 0 → 1 → 2 → 3 → 8 → L → Others (numeric ascending, letters last).
     Does this match your domain understanding?" — so they can correct you on the next
     turn if needed.  The user MAY ignore the question; that does not block the
     pipeline because the ranking is already applied.

── RULE 2: Never invent encoding shortcuts via execute_code ──
The encoding plan's `ranking` field is the ONLY supported path for ordinal encoding.
Do NOT:
  • write `df['Var_36'] = df['Var_36'].map({'Low': 0, 'High': 1})` via execute_code,
  • create a parallel `Var_36_rank` column,
  • use pd.Categorical(..., ordered=True) inside execute_code.
Any of these break the encoding report and produce a column the modeling step cannot
trace back to the original feature.  Always use set_ordinal_ranking.

── RULE 3: One action block per turn ──
You may emit AT MOST ONE action block per chat reply.  If a user request requires
multiple actions (e.g. update_metadata then set_ordinal_ranking), pick the most
upstream one for the current turn and explicitly state in your reply that the
follow-up action will fire on the next turn.  The frontend exposes the result of
each action back to you so you can inspect what happened before committing the next.

── RULE 4: Feature drop discipline — feature_usage, NOT execute_code ──
When the user asks to "drop" / "exclude" / "remove" a feature for modelling or
SFS purposes (e.g. due to high VIF, low SHAP, redundancy, multicollinearity),
NEVER use execute_code with df.drop().  That path:
  • permanently mutates the dataset file (irreversible without backup),
  • silently invalidates the cached selected_features / shap_details /
    encoding_plan / feature_stats artifacts,
  • leaves the Selected Features table in the UI showing stale rows that
    reference a column the dataset no longer has.

The correct path is `update_config` with the `feature_usage` key:
  <<<ACTION:update_config>>>
  {"updates": [{"key": "feature_usage", "column": "Var_3", "value": "drop", "reason": "VIF=9.39"}], "description": "Mark Var_3 for SFS exclusion (multicollinearity)"}
  <<<END_ACTION>>>

This sets the Selected Features table's Keep/Drop dropdown for Var_3 to "drop"
with the supplied reason.  When you subsequently emit start_sfs, the SFS engine
receives Var_3 in `excluded_features` and skips it — same as if the user had
clicked the dropdown manually.  The dataset column is preserved, all cached
modeling artifacts remain valid, and the decision is reversible (the user can
flip it back to "keep" with a single click).

execute_code remains the correct tool for genuine feature engineering — creating
derived columns, applying transformations, computing aggregations, etc.  It is
NOT the tool for "I don't want this feature in modeling."

── RULE 5: SFS start discipline — emit start_sfs or stay silent ──
Sequential Feature Selection is a long-running backend process.  It must be
KICKED OFF via the dedicated `start_sfs` action — there is no other path.

NEVER write any of the following without immediately emitting a start_sfs
action in the same reply:
  • "I am triggering SFS..."
  • "SFS Status: Initiated"
  • "Starting the Sequential Feature Selection process..."
  • "I have started SFS in the background."

If you have not emitted start_sfs, you have NOT started SFS, and the user will
see your claim contradicted by an idle SFS panel.  When the user asks to start
SFS, default the config to:
  • methods=["backward"] for multicollinearity / redundancy pruning,
  • stopping_criteria.metrics=[{"metric":"roc_auc","pct_change":1.0}],
  • min_features=5, max_features=15,
  • n_jobs=3, top_k=5,
unless the user specifies otherwise.  ALWAYS emit start_sfs alongside any
claim that SFS is running.

── RULE 6: Pipeline orchestration discipline (v2.26.0+) ──
You can now FIRE every pipeline run-step (data purifier, encoding, modeling,
SFS) directly via dedicated actions.  The old "I cannot click that button"
disclaimer is OBSOLETE and must NEVER appear in your replies.  When the user
asks to "run preprocessing" / "apply encoding" / "start modeling" / "start
SFS", emit the matching action.

Discipline:

(a) Pre-condition gating.  Before firing any start_* / apply_* action, verify
    its pre-conditions via tool calls.  Each action's docstring (above) lists
    them.  If a pre-condition is unmet (e.g. user asks "start modeling" but
    no processed_file exists), STATE WHAT'S MISSING and propose the upstream
    action instead — don't fire blindly and let the engine error.

(b) One action per turn (RULE 3 still binds).  When the user asks for a
    multi-step run ("preprocess and then start modeling"), pick the most
    UPSTREAM action this turn and explicitly say the next will fire after
    you see the result.  The frontend reports each action's outcome back
    to you on the next turn — chain on confirmed success, not on hope.

(c) Explicit-request gating.  Don't auto-orchestrate the entire pipeline
    from a single ambiguous prompt like "build a model".  Walk the user
    through each gate: confirm the data dictionary is reviewed, confirm
    the purifier options, confirm the encoding plan, confirm the algorithm.
    Only then fire start_modeling.

(d) Honesty about state.  If you fire start_modeling and it succeeds, the
    chat panel will append a "✅ Modeling started." message.  Don't repeat
    that claim in your own text — describe what you did and what you'll
    check next turn (e.g. "I'll review the modeling results once they
    finish").

(e) Recovery from past stale prompts.  If your context window contains an
    earlier "I cannot start modeling" turn, IGNORE that lesson and act on
    the current rules.  The capability gap from v2.25.0 is closed.
"""


# ---------------------------------------------------------------------------
# Prometa-traced helper functions
# ---------------------------------------------------------------------------

@agent(name="llm-advisor")
def _call_llm(messages: list, model_key: str, tools: list = None) -> dict:
    """Unified LLM caller — dispatches to OpenAI or the local Inference Engine
    based on the resolved model config.

    Traced as a Prometa agent span. For both providers, GenAI attributes
    (model, tokens, prompt, completion, cost) are captured automatically by
    the prometa-sdk openai auto-instrumentation — the engine path uses the
    OpenAI client with a custom ``base_url`` so the same patch applies.
    agentic-hook-v2 receives all observability data via this assistant-side
    instrumentation; the engine itself has no direct coupling to the
    platform.
    """
    model_cfg = get_model_config(model_key)
    provider = model_cfg['provider']
    # v2.30.0 (Phase 2): canonical helper instead of manual set_span_attr.
    # The SDK helper auto-bubbles to parent spans and gets normalization
    # for free as the platform evolves.  Wire shape is unchanged —
    # gen_ai.request.model still reaches the cost panel, AML F1 (model_route)
    # detector, and trace UI exactly as before.
    set_request_model(model_cfg['model_id'])
    # Tag the routing target on the parent agent span so the platform UI
    # can distinguish engine-routed calls from direct cloud calls.
    # The child openai-instrumented span still carries gen_ai.system="openai"
    # because the SDK speaks OpenAI protocol regardless of the upstream.
    set_span_attr('declarai.llm.backend', provider)

    # v2.31.0 (Phase 3a): emit a Prometa AML ``model.route`` span around
    # the provider dispatch.  DeclarAI today doesn't run a complexity-
    # based cascade — the user picks the model in the UI — so the
    # routing_reason is ``user_selected`` and the candidates set is the
    # curated static MODEL_REGISTRY (the dropdown the user chose from).
    # When/if a real cascade lands (rate-limit fallback, cost-capped
    # routing) the same call site takes a richer routing_reason without
    # any surface change.  See prometa_config::model_route docstring.
    candidates = [cfg['model_id'] for cfg in MODEL_REGISTRY.values()]
    with model_route(
        chosen=model_cfg['model_id'],
        candidates_considered=candidates,
        routing_reason='user_selected',
    ):
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

        else:
            raise ValueError(f'Unknown provider: {provider}')


def _enrich_dd_with_descriptions(file_id: int, dd_list: list) -> list:
    """Backfill missing ``Feature_Description`` entries from the DataDictionary DB.

    The Redis cache for the data dictionary can be written by multiple paths
    (the declaration endpoint enriches descriptions, but the frontend bulk-push
    in some components may overwrite the cache with description-less rows).
    The DB (DataDictionary table) is the source of truth; use it as a fallback
    so every consumer — slim system context AND the get_data_dictionary tool —
    sees descriptions whenever they exist.

    Cheap (single DB query for the file_id), idempotent, and safe to call
    on every chat turn.
    """
    if not dd_list:
        return dd_list
    needs = [
        (f.get('Feature_Name') or f.get('feature'))
        for f in dd_list
        if not (f.get('Feature_Description') or f.get('description'))
    ]
    if not needs:
        return dd_list
    try:
        from declaration.models import DataDictionary
        rows = DataDictionary.objects.filter(
            data_file_id=file_id, column_name__in=[n for n in needs if n]
        ).values_list('column_name', 'description')
        desc_map = {col: desc for col, desc in rows if desc}
    except Exception:
        return dd_list
    if not desc_map:
        return dd_list
    for f in dd_list:
        name = f.get('Feature_Name') or f.get('feature')
        if name and not (f.get('Feature_Description') or f.get('description')):
            d = desc_map.get(name)
            if d:
                f['Feature_Description'] = d
    return dd_list


def _build_slim_context(file_id: int, section: str) -> str:
    """Build a compact context manifest from cached artifacts (~500 tokens).

    This replaces the old approach of dumping the entire pipeline context.
    The LLM can request detailed data via tool calls when needed.

    Every underlying Redis read is performed through an instrumented raw
    reader (``read_pipeline_config``/``read_data_dictionary``/...) so each
    fetch appears as its own ``cache-read:<artifact>`` span in the trace
    waterfall — symmetric with the spans emitted when the LLM itself
    invokes a tool via ``tool-call``.
    """
    # Local import to avoid circular dependency at module load time.
    from .tool_executor import (
        read_pipeline_config,
        read_data_dictionary,
        read_selected_features,
        read_sfs_status,
        _format_sfs_status_line,
    )

    parts = []

    # ── v2.35.0: SFS run-state preamble (BEFORE pipeline config) ──
    # Surface SFS-running / stopped / interrupted / errored status at
    # the very top of the slim context so the LLM cannot miss it.
    # See the rationale block in tool_executor.read_sfs_status — this
    # closes the "assistant unaware SFS is running" bug from the
    # 2026-05-19 ToDoS screenshot.  Benign statuses (not_started /
    # completed) emit no banner so we don't waste tokens on the
    # common case.
    sfs_status_payload = read_sfs_status(file_id)
    sfs_status_line = _format_sfs_status_line(sfs_status_payload)
    if sfs_status_line:
        parts.append(sfs_status_line)

    # Pipeline config (always include)
    config = read_pipeline_config(file_id)
    if config:
        parts.append(f"Pipeline: {config.get('pipeline_type', '?')}")
        td = config.get('target_definition', '')
        if td:
            parts.append(f"Target: {td}")
        parts.append(f"Rows: {config.get('row_count_before', '?')} → {config.get('row_count_after', '?')} "
                      f"(removed: {config.get('rows_removed', 0)})")
        parts.append(f"Split: {config.get('split_strategy', '?')}")

    # Data dictionary — embed feature descriptions inline so every model
    # (native tool-callers AND text-mode models that may skip tool calls)
    # sees the business context without needing a follow-up call.
    # The raw reader already performs the DB backfill for missing descriptions.
    dd_list = read_data_dictionary(file_id)
    if dd_list:
        described = [(f.get('Feature_Name') or f.get('feature') or '?',
                      (f.get('Feature_Description') or f.get('description') or '').strip())
                     for f in dd_list]
        any_desc = any(d for _, d in described)
        if any_desc:
            parts.append(f"Data dictionary ({len(dd_list)} features) — business descriptions:")
            for name, desc in described[:60]:
                parts.append(f"  • {name}: {desc}" if desc else f"  • {name}: (no description)")
            if len(dd_list) > 60:
                parts.append(f"  … and {len(dd_list) - 60} more (use get_data_dictionary for the rest).")
        else:
            names = [n for n, _ in described]
            parts.append(f"Data dictionary ({len(dd_list)} features): {', '.join(names[:50])}")
            parts.append("No business descriptions found for these features. "
                         "Tell the user that uploading a dictionary file (or editing descriptions in the UI) "
                         "would unlock domain-aware feature engineering.")

    # Feature list (names + VIF flags only)
    sel_feats = read_selected_features(file_id)
    if sel_feats:
        feat_list = sel_feats if isinstance(sel_feats, list) else sel_feats.get('features', [])
        names = [f.get('feature', '?') for f in feat_list[:40]]
        high_vif = [f.get('feature', '?') for f in feat_list if (f.get('vif') or 0) > 5]
        parts.append(f"Selected features ({len(feat_list)}): {', '.join(names)}")
        if high_vif:
            parts.append(f"High-VIF features (>5): {', '.join(high_vif)}")

    # Available data (so the LLM knows which tools will return data).
    # ``cache_list_artifacts`` is already instrumented with ``redis-list``.
    available = cache_list_artifacts(file_id)
    if available:
        parts.append(f"Cached artifacts available: {', '.join(available)}")

    parts.append(f"Current section: {section or 'general'}")
    parts.append("Use the provided tools to fetch detailed pipeline data when needed.")

    return '\n'.join(parts)


# Maximum number of tool-call rounds before forcing a final response
_MAX_TOOL_ROUNDS = 5

# Actionable fallback shown when the model genuinely returns no content AND
# no actions across the entire workflow.  Pre-v2.27.2 this surfaced as the
# bare "No response received." string in the chat UI; v2.27.2 makes the
# backend the single source of truth for empty-response copy so the
# frontend, the action-correction retry path, and any future API consumer
# see the same actionable message.
_EMPTY_RESPONSE_FALLBACK = (
    "I couldn't compose an answer for that prompt. Please try rephrasing "
    "your question — for example, ask about a specific feature, metric, "
    "pipeline step, or purifier option."
)

# Fallback shown when the tool-loop budget is exhausted AND the synthesis
# pass also fails to produce text.  Different copy from the generic empty
# fallback because the user CAN see (in tracing) that real work happened.
_TOOL_BUDGET_EXHAUSTED_FALLBACK = (
    "I gathered the requested context across multiple tool calls but ran "
    "out of room to write a full reply. Please ask a more focused "
    "follow-up question (e.g., zoom in on one feature, one metric, or "
    "one pipeline step) and I'll answer it directly."
)

# ---------------------------------------------------------------------------
# Skill auto-routing — map user intent to a bundled skill
# ---------------------------------------------------------------------------
# Conservative keyword/phrase matching.  Designed to fire on clear intent
# (\"derive new features\", \"feature engineering\", \"create features\", etc.)
# while NOT firing on pure analytical questions (\"why is feature X important?\").

_FEATURE_ENGINEERING_PATTERNS = [
    r'\bfeature[\s\-]?engineer\w*\b',
    r'\b(derive|derived|deriving|generate|generating|create|creating|engineer|engineering|construct|build)\b'
        r'.{0,40}\b(new\s+)?features?\b',
    r'\bnew\s+features?\b.{0,40}\b(from|out\s+of|based\s+on)\b',
    r'\b(ratio|interaction|aggregation|aggregate|woe|iv|rfm|velocity|rolling\s+window|lag\s+features?)\b',
]
_FEATURE_ENGINEERING_RE = _re.compile('|'.join(_FEATURE_ENGINEERING_PATTERNS), _re.IGNORECASE)


def _auto_route_skill(user_message: str) -> Optional[str]:
    """Return the name of a skill to auto-load for this user message, or None.

    Currently only the ``feature-engineering`` skill is auto-routed.  The
    function is the single source of truth for intent detection so tests
    can pin behaviour without mocking the LLM.
    """
    if not user_message:
        return None
    if get_skill('feature-engineering') and _FEATURE_ENGINEERING_RE.search(user_message):
        return 'feature-engineering'
    return None


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
        # v2.30.0 (Phase 2): per-span customer_id override.  Joins every
        # span emitted from this chat turn — and its child agent / tool /
        # cache spans via parent-attribute inheritance — under one
        # correlation key for AML scoring, Session Explorer aggregates,
        # and the platform's correlation-id resolver.  See
        # ai_assistant/prometa_config.py::set_customer_id docstring for
        # the file_id ↔ customer_id mapping rationale.
        set_customer_id(str(file_id))

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

    # ── Skill auto-routing (model-agnostic) ──
    # Native function-callers can hit invoke_skill themselves, but text-mode
    # models (e.g., Gemma in text tool-calling mode) often skip tool calls.
    # Detect feature-engineering intent in the user message and pre-load the
    # skill body so EVERY model sees the playbook before answering.
    # The skill loader is a @prometa_tool span itself, so the auto-route is
    # still visible in the trace chain.
    auto_skill = _auto_route_skill(user_message)
    if auto_skill:
        skill_body = _load_skill_traced(auto_skill)
        messages.append({
            'role': 'system',
            'content': (f"The user's question matched the '{auto_skill}' skill — "
                        f"its playbook has been pre-loaded below.  Ground your "
                        f"answer in these patterns and cite the relevant section.\n\n"
                        f"{skill_body}"),
        })
        set_span_attr('declarai.skill.auto_routed', auto_skill)

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

    # ── v2.27.2 synthesis pass ──────────────────────────────────────────
    # Pre-v2.27.2 the loop could exit with an assistant message that has
    # `tool_calls` populated but `content=null`.  This happened when the
    # model kept calling tools through round 5 (the no-tools forced
    # round): we executed those tool calls inside the loop body, then
    # broke naturally without ever asking the model to verbalize a
    # final answer.  The user saw the literal string "No response
    # received." and the tracing showed real tool work that produced
    # no visible output.  Root cause: there was no synthesis pass after
    # the budget cap.
    #
    # Fix: when the loop exits with empty content but tool work was
    # done, run ONE more no-tools call to force the model to summarize
    # what it found.  All tool results are already in `messages`, so
    # this is a cheap one-shot synthesis.  It produces a non-empty
    # answer in the vast majority of cases; if it still fails (network
    # error, model returns blank), `_TOOL_BUDGET_EXHAUSTED_FALLBACK`
    # ensures the user sees an actionable message instead of a blank
    # bubble.
    synthesis_required = (
        not assistant_message.strip()
        and any(m.get('role') == 'tool' for m in messages)
    )
    set_span_attr('declarai.chat.synthesis_pass', synthesis_required)
    if synthesis_required:
        try:
            messages.append({
                'role': 'system',
                'content': (
                    'You executed tool calls but did not produce a final '
                    'answer.  Using ONLY the tool results above plus the '
                    'pipeline context, write a concise reply to the user '
                    'now.  Do not call any more tools.'
                ),
            })
            synth = _call_llm(messages, model_key, tools=None)
            _merge_usage(total_usage, synth.get('usage', {}))
            synth_msg = synth.get('choices', [{}])[0].get('message', {}) or {}
            assistant_message = synth_msg.get('content', '') or ''
            set_span_attr(
                'declarai.chat.synthesis_chars',
                len(assistant_message),
            )
        except Exception as exc:  # pragma: no cover - network path
            set_span_attr('declarai.chat.synthesis_error', str(exc)[:200])
            assistant_message = ''

    # Cost, tokens, and conversation turns are handled by auto-instrumentation (v0.3.3+).
    # The Conversation panel reads gen_ai.prompt.user (pre-extracted by the SDK) and
    # gen_ai.completion from each LLM span.  No manual stamping needed.

    # Parse action blocks from the AI response
    actions, clean_message = _extract_actions(assistant_message)

    # v2.33.0 (Phase 3c): emit a Prometa AML ``plan.generate`` span (C2)
    # whenever the LLM's response yields ≥1 action block.  Pure
    # conversational replies don't produce plans, so the span is
    # conditional — emitting it for zero-action turns would inflate the
    # C2 detector's denominator with non-plans.
    #
    # plan_id encodes file_id + turn-time so the span is uniquely
    # addressable per chat turn (the SDK uses it as the canonical
    # ``plan.id`` span attribute).  Steps mirror the extracted action
    # blocks 1:1; depends_on=[] on every step because DeclarAI actions
    # are independent suggestions (the user applies any subset in the
    # chat-panel UI — no enforced ordering).  complexity_estimate is
    # the raw action count as a first-cut proxy for plan size.
    #
    # When PROMETA_ENDPOINT is unset or the SDK is unavailable, the
    # wrapper yields a _NoOpAMLHandle and the entire block is a
    # transparent no-op (no behavior change vs v2.32.0).
    if actions and file_id is not None:
        import time as _time
        plan_id = f'declarai-file-{file_id}-{int(_time.time() * 1000)}'
        plan_steps = [
            {
                'order': i + 1,
                'action': a.get('action_type', 'unknown'),
                'tool': a.get('action_type', 'unknown'),
                'depends_on': [],
            }
            for i, a in enumerate(actions)
        ]
        with plan_generate(plan_id) as _plan:
            _plan.emitted(
                steps=plan_steps,
                complexity_estimate=len(actions),
            )

    # If the model's entire reply was the action block, synthesize a brief message
    if not clean_message.strip() and actions:
        descs = [a['payload'].get('description', '') for a in actions if a.get('payload')]
        descs = [d for d in descs if d]
        if descs:
            clean_message = 'I\'ve prepared the following operation for you. Review the details below and click **Apply** to execute.'
        else:
            clean_message = 'I\'ve prepared an action for you. Review it below and click **Apply** to execute.'

    # ── Final empty-response guard (v2.27.2) ────────────────────────────
    # If we still have no message AND no actions, surface an actionable
    # fallback instead of an empty bubble.  Pick the copy based on
    # whether real tool work happened in this turn so the message is
    # contextually honest.
    if not clean_message.strip() and not actions:
        had_tool_work = any(m.get('role') == 'tool' for m in messages)
        clean_message = (
            _TOOL_BUDGET_EXHAUSTED_FALLBACK if had_tool_work
            else _EMPTY_RESPONSE_FALLBACK
        )
        set_span_attr('declarai.chat.empty_fallback', True)
        set_span_attr('declarai.chat.empty_fallback_kind',
                      'budget_exhausted' if had_tool_work else 'no_content')

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
