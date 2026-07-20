"""
OpenAI function-calling tool definitions for the AI Assistant.

Each tool maps to a pipeline artifact stored in Redis.  The LLM decides
which tools to call based on the user's question and the slim context
manifest it receives.

The list also exposes ``invoke_skill`` which returns the markdown body of
a bundled domain-knowledge skill (see :mod:`ai_assistant.skill_registry`).
Skill bodies are large authoritative references (e.g. a feature-engineering
playbook) that the LLM should consult on demand rather than carry in every
system prompt.
"""

from .skill_registry import list_skills


def _invoke_skill_definition() -> dict:
    """Build the OpenAI tool definition for ``invoke_skill``.

    The description enumerates the discovered skills so the LLM knows which
    names are valid even without seeing the registry directly.
    """
    skills = list_skills()
    if skills:
        catalogue = '; '.join(f"{name}: {sk.description}" for name, sk in skills.items())
        skill_names = sorted(skills.keys())
    else:
        catalogue = '(no skills bundled yet)'
        skill_names = []
    return {
        "type": "function",
        "function": {
            "name": "invoke_skill",
            "description": (
                "Invoke a bundled domain-knowledge skill and receive its full "
                "guidance text plus a listing of supplementary files.  Skills "
                "encode best practices that are too long to ship in every "
                "system prompt.  Call this BEFORE proposing domain-specific "
                "feature engineering, encoding strategies, or anti-leakage "
                "rules so your suggestions reflect the latest playbook.  "
                "After this returns, call ``get_skill_file`` to fetch any "
                "supplementary file you need.  Available skills — " + catalogue
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to invoke.",
                        **({"enum": skill_names} if skill_names else {}),
                    },
                },
                "required": ["skill_name"],
            },
        },
    }


def _get_skill_file_definition() -> dict:
    """Build the OpenAI tool definition for ``get_skill_file``.

    The description lists every supplementary file that ships with each
    bundled skill so the LLM can pick a file in one shot — without having
    to call ``invoke_skill`` first if it already knows what it needs.
    """
    skills = list_skills()
    file_catalogue_lines = []
    skill_names = sorted(skills.keys())
    for name in skill_names:
        files = skills[name].list_files()
        if files:
            file_catalogue_lines.append(f"  • {name}: {', '.join(files)}")
        else:
            file_catalogue_lines.append(f"  • {name}: (no supplementary files)")
    catalogue = '\n'.join(file_catalogue_lines) if file_catalogue_lines else '  (no skills bundled yet)'
    return {
        "type": "function",
        "function": {
            "name": "get_skill_file",
            "description": (
                "Read a supplementary file from a bundled skill (e.g., a "
                "best-practices reference, an example pipeline script, an "
                "error-handling guide).  Use this AFTER ``invoke_skill`` to "
                "pull deeper material on demand without bloating the system "
                "prompt.  Path is the relative path inside the skill "
                "directory; only files ending in .md, .txt, .py, .json, "
                ".yml, .yaml are exposed.\n\n"
                f"Available files per skill:\n{catalogue}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill that owns the file.",
                        **({"enum": skill_names} if skill_names else {}),
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative path of the file inside the skill "
                            "directory (e.g., 'references/feature_engineering_best_practices.md')."
                        ),
                    },
                },
                "required": ["skill_name", "path"],
            },
        },
    }


PIPELINE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_split_validation",
            "description": (
                "Get the train/test split validation data: row counts, target=0 and "
                "target=1 counts, target mean (bad rate) per split (Full, Train, Test). "
                "Call this when the user asks about split balance, target rates, or "
                "train-test distribution."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dq_summary",
            "description": (
                "Get the Data Quality summary table with per-feature PSI, CSI, missing %, "
                "variable type, and Datq_Decision flags. Optionally filter by a specific "
                "feature name. Call this when the user asks about data quality, stability, "
                "PSI, missing values, or feature-level statistics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature": {
                        "type": "string",
                        "description": "Optional: filter to a specific feature name. Omit to get all features.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_feature_stats",
            "description": (
                "Get before/after preprocessing descriptive statistics for a specific feature "
                "(mean, std, min, max, missing %, quantiles). Call this when the user asks "
                "about how preprocessing changed a feature's distribution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature": {
                        "type": "string",
                        "description": "The feature name to get stats for.",
                    },
                },
                "required": ["feature"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vif_decomposition",
            "description": (
                "Get the VIF decomposition (pairwise correlations) for a specific feature. "
                "Shows which other features contribute most to its multicollinearity: "
                "|correlation|, signed correlation, VIF without that feature, and VIF drop. "
                "Call this when the user asks about collinearity, VIF, or which features are "
                "correlated with a given feature."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature": {
                        "type": "string",
                        "description": "The feature name to get VIF decomposition for.",
                    },
                },
                "required": ["feature"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_encoding_plan",
            "description": (
                "Get the categorical feature encoding plan: feature name, level of measurement, "
                "nunique, primary strategy, fallback strategy. Call this when the user asks "
                "about encoding, categorical handling, or feature cardinality."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_selected_features",
            "description": (
                "Get the list of selected features with their combined score, SHAP percentile, "
                "gain percentile, VIF, and usage (keep/drop). Call this when the user asks "
                "about feature importance, feature selection, or which features the model uses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Optional: return only the top N features by combined score. Omit for all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shap_details",
            "description": (
                "Get SHAP impact details for selected features: feature name, absolute impact, "
                "signed impact, and description. Call this when the user asks about SHAP values, "
                "feature impact, or beeswarm plot interpretation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Optional: return only the top N features by |impact|. Omit for all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sfs_results",
            "description": (
                "Get Sequential Feature Selection (SFS) results and configuration. "
                "Shows step-by-step feature additions/removals with CV metric at each step. "
                "Call this when the user asks about SFS, forward/backward selection, or "
                "feature selection progression."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["forward", "backward", "forward_from_backward"],
                        "description": "Which SFS direction to retrieve. Omit to get all available.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cv_results",
            "description": (
                "Get cross-validation results: ROC-AUC mean/std, PR-AUC mean/std, number of "
                "folds, per-fold scores, and PR curve data. Call this when the user asks about "
                "model performance, CV scores, or evaluation metrics."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_notes",
            "description": (
                "Get user-authored pipeline notes (annotations) attached to different "
                "sections of the pipeline. Call this when the user asks about their notes "
                "or wants to review what they wrote."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_codelines",
            "description": (
                "Get user-authored pipeline Codeline cells (inline code or natural-language "
                "intent attached to pipeline sections). Call this when the user asks about "
                "prior Codeline work, exploratory code, or intents they wrote in the flow."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_config",
            "description": (
                "Get the full pipeline configuration: target definition, pipeline type, "
                "split strategy, purifier steps, data dictionary, row/column counts, "
                "and model exclusions. Call this when the user asks about pipeline setup, "
                "configuration, or target variable."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purifier_options",
            "description": (
                "Get the canonical catalog of the 34 data-purifier options that the "
                "Run-Preprocessing UI exposes (column-/row-dedup, zero-variance drop, "
                "perfect-correlation drop, parametric correlation/sparsity/missing/combined "
                "drops with their thresholds, numeric outlier-quantile clipping at "
                "[0.01-0.99], [0.05-0.95], [0.10-0.90], and four categorical-outlier merge "
                "thresholds).  Each entry returns its integer ID (1..34), its UI label, "
                "its transform kind, its mutual-exclusion group, and any threshold or "
                "quantile range.  Default-selected IDs are also flagged.  CALL THIS "
                "BEFORE emitting a start_data_purifier ACTION whenever the user asks for "
                "a specific behavior in natural language (e.g. 'change outlier interval to "
                "0.05/0.95', 'drop columns with >95% missing', 'turn off correlation "
                "pruning').  Use the returned IDs verbatim in purifier_options.  Optional "
                "`kind` filter narrows the catalog to one transform family."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "col_dedup",
                            "row_dedup",
                            "zero_var_drop",
                            "perfect_corr_drop",
                            "corr_drop",
                            "sparsity_drop",
                            "missing_drop",
                            "combined_drop",
                            "outlier_quantile_clip",
                            "cat_outlier_merge",
                        ],
                        "description": (
                            "Optional: filter to a single transform kind. "
                            "Omit to retrieve all 34 entries."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_dictionary",
            "description": (
                "Get the data dictionary: all features with their name, description, "
                "data type, number of unique values, level of measurement, and model usage "
                "(excluded or included). Call this when the user asks about feature descriptions, "
                "variable meanings, data dictionary, what a feature represents, which features "
                "are available, or wants to derive new features from existing ones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature": {
                        "type": "string",
                        "description": "Optional: filter to a specific feature name. Omit to get all features.",
                    },
                },
                "required": [],
            },
        },
    },
    _invoke_skill_definition(),
    _get_skill_file_definition(),
]
