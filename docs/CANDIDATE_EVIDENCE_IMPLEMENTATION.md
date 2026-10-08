# P05 — Candidate fit evidence and exact-version acceptance

SFS/HPO and accepted champion refits previously dropped CV evidence and retained some parent-specific fields. A fitted adapter could be published without checking that its development inputs matched the selected immutable execution. Acceptance could silently read mutable per-file search results, and the browser did not consistently submit the recorded winning configuration or show the new execution.

Native fits now record algorithm/task, ordered feature names, dtypes, exact row/value/label fingerprints, requested and effective fitter parameters, boosting and early-stopping budgets, validation use and package versions. Candidate publication checks this receipt against the selected parent's training and validation inputs before staging. Supported native adapter types are checked before loading customer inputs; expert adapters remain blocked until isolated execution is qualified. A failed refit clears its previous receipt. Historical loaded adapters must be refitted to acquire evidence.

Each candidate receives fresh training/validation metrics, gain importance, calibration where supported, and development CV using its selected features and recorded training budget. Fold receipts include their own native fits. Parent CV, scores, SHAP/leakage results and final assessment metrics are not inherited. Scorecard candidates retain their own WOE/IV/point evidence. Protected final assessment input is copied as bytes; candidate development does not deserialize its outcomes. Missing historical validation context produces an explicit unavailable record.

Candidate CV is **post-selection exploratory evidence**: selection and tuning have already used these development data. It is not confirmatory evidence, independent validation, a paired comparison or a confidence interval. The existing task/fold constraints and complete metric coverage checks remain in force for new recipes. Accepted configurations and candidates carry the actual parameters supplied to the native fitter; XGBoost/LightGBM receipts do not resolve every library default. Candidate CV freezes the recorded fitter parameters, including any selected class weight; it does not silently replace them with the initial model's automatic weighting policy. Initial CV still fits its automatic ratios within training folds. Full search/objective consistency remains open. Recorded versions are a foundation for reproduction, not a clean-environment reproduction runner.

Acceptance requires an explicit execution ID and ordered feature list. It creates a new version; a changed current parent returns a conflict, retaining a completed candidate without adopting it. No mutable search-file fallback is used to select accepted features or parameters. The browser submits the recorded primary-metric configuration and features, requires versioned tuning evidence, and displays the returned execution. Native fit details are expandable. Scoring packages include the fit receipt and retain their existing artifact integrity checks; prior executions and bundles remain usable.

Receipts are controller records and corruption checks, **not signatures, actor authentication or proof against a compromised controller/storage owner**. Native pickle/joblib loading remains within the existing trusted artifact boundary. This packet does not implement expert execution or qualify arbitrary Python, malicious serialization, signed evidence, production data egress or project role enforcement.

Qualification commands, exact source hashes and retained report hashes are recorded in [P05 qualification](evidence/p05-qualification-2026-10-08.json). Local tests, exact-head PR CI, merged main CI, production operation and customer acceptance remain separate states.

D02 and D04 remain partial. Full objective/early-stopping and SFS/search consistency, supervised encoding, paired change analysis, independently reproducible review packages, durable jobs/recovery, project roles/egress, production private operation, mandatory expert isolation and customer/value acceptance remain open. No milestone is closed or marked released/customer accepted.

| Local check | Result |
| --- | --- |
| Full CI-marked backend suite, four CPU affinities | 1,305 passed, six explicit skips; 65.27% coverage against the unchanged 50% gate |
| Frontend unit suite | 526 passed |
| Governed Chromium/authenticated API suite | 19 passed, no skips |
| Lint, migration drift, package consistency, skip budget, production build and browser TypeScript | Passed; existing build warnings and 158 lint warnings remain |
| Original checkout and cleanup | All 11 starting hashes unchanged; disposable services and credentials removed |
