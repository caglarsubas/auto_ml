"""Repro probe: does Nemotron answer the data-purification question, or drift
back to the previous feature-engineering topic when that turn is in history?

Run from host:  python3 backend/scripts/probe_topic_drift.py
"""
import json
import sys
import urllib.request

URL = "http://localhost:8001/api/ai-assistant/chat/"

PRIOR_FEATURE_ANSWER = (
    "Proposed derived features to boost predictive performance:\n\n"
    "| Feature | Formula / transformation | Meaning | Why it helps the model |\n"
    "|---|---|---|---|\n"
    "| Debt_To_Income | Var_19 / Var_24 | Ratio of outstanding overdraft balance to monthly net income | Normalizes exposure by ability to pay |\n"
    "| Credit_Utilization | Var_19 / (Var_4 + 1) | Outstanding balance divided by previous credit limit | Strong credit-risk signal |\n"
    "| Income_Verification_Diff | Var_30 - Var_28 | Difference between verified income and declared net income | Flags income inconsistency |\n"
    "| Income_Verification_Ratio | Var_30 / Var_28 | Ratio of verified to declared net income | Scale-invariant inconsistency |\n"
    "| Legal_Action_Count | Var_3 + Var_11 + Var_37 | Count of legal-action flags across multiple sources | Aggregates sparse red flags |\n"
    "| App_Velocity_1m_6m | Var_8 / (Var_9 + 1) | Short-term vs long-term application velocity | Captures credit-seeking intensity |\n"
    "| Total_Recent_Applications | Var_8 + Var_9 + Var_10 | Sum of recent applications | Recent demand for credit |\n"
    "| OD_Utilization | Var_19 / (Var_20 + 1) | Overdraft utilization | Utilization-style risk signal |\n"
    "\nThe following action will create these engineered columns directly in the dataset."
)

CONTEXT = {
    "pipeline_config": {
        "target_definition": "good/bad flag of credit applications within the 12 months period of its usage",
        "pipeline_type": "boosting",
        "purifier_options": [1, 2, 3, 4, 7, 11, 17, 23, 28, 32],
    },
    "selected_features": [
        "FE_Debt_To_Income", "FE_Credit_Utilization", "FE_Income_Verification_Diff",
        "FE_Income_Verification_Ratio", "FE_Legal_Action_Count", "FE_App_Velocity_1m_6m",
        "FE_Total_Recent_Applications", "FE_OD_Utilization",
    ],
}

HISTORY = [
    {"role": "user", "content": (
        "according to the project goal and the feature descriptions we have, "
        "which new features can be derived from others in the aim of increasing "
        "the predictive performance of boosting algorithms. create these "
        "suggested features in our dataset.")},
    {"role": "assistant", "content": PRIOR_FEATURE_ANSWER},
]

PURIFICATION_Q = (
    "what are the data purification steps in the flow? how to sort them while "
    "implementing and configure them better according to the data and problem we have?")

PURIFICATION_TERMS = (
    "purif", "duplicate drop", "zero-variance", "sparsity", "missing-drop",
    "outlier", "correlation drop", "perfect-correlation", "row-wise", "column-wise",
)
FEATURE_DRIFT_TERMS = (
    "debt_to_income", "credit_utilization", "income_verification",
    "derived feature", "proposed derived", "legal_action_count", "boost predictive",
)


def classify(msg: str) -> str:
    low = msg.lower()
    pur = sum(t in low for t in PURIFICATION_TERMS)
    drift = sum(t in low for t in FEATURE_DRIFT_TERMS)
    if drift > pur:
        return "DRIFT (wrong topic: features)"
    if pur > 0:
        return "ON-TOPIC (purification)"
    return "UNCLEAR"


def run(i: int, with_history: bool):
    body = {
        "message": PURIFICATION_Q,
        "model": "nemotron-3-nano:30b",
        "file_id": 502,
    }
    body["section"] = "data_quality"
    body["context"] = CONTEXT
    if with_history:
        body["history"] = HISTORY
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001
        print(f"RUN {i} ({'hist' if with_history else 'nohist'}): ERROR {exc}")
        return
    msg = d.get("message", "") or ""
    usage = d.get("usage", {}) or {}
    print(f"RUN {i} ({'hist' if with_history else 'nohist'}): "
          f"{classify(msg)} | chars={len(msg)} "
          f"completion_tokens={usage.get('completion_tokens')} | "
          f"head={msg[:80]!r}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    for i in range(1, n + 1):
        run(i, with_history=True)
