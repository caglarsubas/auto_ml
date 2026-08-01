# Assistant Usage and Action Guide

## What the Assistant Can Do

The DeclarAI assistant has four modes of help:

- Explain platform workflow and data-science concepts.
- Retrieve stable guidance from the knowledge bank.
- Inspect current pipeline data through live tools.
- Prepare executable actions that the user can apply.

These modes can combine in one turn. For example, a user may ask what VIF means,
which current features have high VIF, and whether to exclude one of them. The
assistant should retrieve glossary context, call the selected-features or VIF
tool, and then propose a reversible feature-usage action if appropriate.

## When Knowledge-Bank Retrieval Is Used

Knowledge-bank retrieval is used for stable documentation questions:

- "How does the platform work?"
- "What are the pipeline steps?"
- "What does PSI mean?"
- "Explain SFS stopping criteria."
- "What calculations are made in modeling?"
- "What assumptions does the purifier make?"
- "How should I use the assistant?"
- "Give me the glossary for SHAP, VIF, PR-AUC, and PSI."
- "Give me the model governance review checklist."

Retrieval uses hybrid ranking (vector + lexical) when `OPENAI_API_KEY` is
configured, otherwise lexical-only. Retrieved snippets are labeled `[KB1]`,
`[KB2]`, … in the system prompt. When the assistant relies on those facts, it
should cite the matching `[KBn]` marker in the reply. The chat UI also lists
the retrieved sources under the assistant message. The assistant must not invent
source labels that were not retrieved.

Knowledge-bank retrieval should not replace live pipeline tools when the user is
asking about current data, current settings, current metrics, or a current run.

## When Live Pipeline Tools Are Used

Live tools retrieve current artifacts for the loaded file. The assistant should
use tools when the user asks about:

- Current selected features, SHAP, gain, or VIF.
- Current SFS results or progress.
- Current data-quality summary, PSI, CSI, missingness, or drift.
- Current encoding plan, ordinal rankings, or unique values.
- Current pipeline configuration or purifier options.
- Current split validation or target rates.
- Current notes.

If a specific number, feature name, metric value, selected option, or status is
needed, the assistant should use a live tool instead of answering from memory.

## When Actions Are Proposed

Actions are proposed when the user asks to change something or run a pipeline
step. The assistant should explain what will happen and why, then emit one
action block at the end of the reply.

Supported action types:

- `execute_code`: create or modify dataset columns with pandas/numpy.
- `update_metadata`: update data dictionary fields.
- `update_config`: change model usage, feature usage, purifier selections,
  split settings, or algorithm choice.
- `set_ordinal_ranking`: rank ordinal category values and mark the feature as
  ordinal.
- `start_data_purifier`: run preprocessing.
- `update_purifier_selection`: change which purifier steps/options are selected
  before or after a purifier run (without inventing unsupported transformers).
- `apply_encoding`: apply the encoding plan.
- `start_modeling`: train the selected model.
- `start_sfs`: start Sequential Feature Selection.
- `start_hyperparameter`: start hyperparameter tuning.
- `apply_recommendation`: apply a platform recommendation card the user has
  already been shown (for example a suggested feature drop or encoding choice).
- `update_notes`: add, edit, or delete pipeline notes.

## One-Action Rule

The assistant should emit at most one action block per chat turn. If a workflow
requires multiple steps, it should choose the most upstream action first, then
wait for the resulting state before proposing the next action.

Example: if the user asks to rank an ordinal feature and then start modeling,
the assistant should first set the ordinal ranking. On the next turn, after the
ranking is applied and encoding is ready, it can apply encoding or start
modeling as appropriate.

## Reversible Configuration Before Destructive Mutation

When the user wants to exclude a feature from modeling or SFS, the assistant
should prefer `update_config` with feature usage set to `drop`. It should not
use `execute_code` to permanently delete the column unless the user explicitly
asks for dataset mutation.

This keeps cached artifacts valid and lets the user reverse the decision.

## Assistant Intent Labels

The backend classifies each free-text turn before LLM work:

- `A`: General information or data-science education.
- `B`: Platform or pipeline-flow explanation.
- `C`: Current status, metrics, results, settings, or data inspection.
- `D`: Configuration or data editing.
- `E`: Pipeline process execution.
- `R`: Knowledge-bank retrieval should be used.

Labels can be combined. A single question can be both `C` and `R` when it asks
for a current result and a definition.

## Good User Prompts

Good prompts are specific about whether the user wants explanation, inspection,
or action.

Examples:

- "Explain PSI and show which current variables have PSI > 0.25."
- "What does the backward SFS stopping criterion mean for my run?"
- "Set Var_17 to drop because of VIF, but do not start SFS yet."
- "Apply encoding after checking whether any ordinal rankings are missing."
- "Start backward SFS with ROC-AUC stopping at 1 percent change."

## Assistant Boundaries

The assistant should not invent feature names, metric values, or current
settings. It should use current pipeline tools for live data and knowledge-bank
retrieval for stable platform documentation.

The assistant should not claim that a process has started unless it emits the
matching action block. It should not silently chain multiple pipeline run steps
in one response.
