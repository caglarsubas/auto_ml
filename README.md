# DeclarAI — Declarative Automated Machine Learning Platform

## Vision & Aim

DeclarAI is an **end-to-end, declarative machine learning platform** purpose-built for tabular data — with a particular focus on **credit scoring**, **risk modeling**, and **regulatory-grade model development**. The platform's guiding principle is that every modeling decision should be **explicit, auditable, and human-governed**: the user declares what they want, and the system executes it transparently.

The name *DeclarAI* reflects this philosophy: models are built through a series of **declarations** — not hidden automation — ensuring full traceability from raw data to deployed model.

### Core Principles

1. **Declarative over imperative** — The user declares pipeline steps, feature roles, purification rules, and algorithm choices. The system translates these into reproducible modeling workflows.
2. **Transparency at every layer** — Every feature gets a data dictionary entry, every preprocessing step shows what it dropped and why, every model explains its decisions through SHAP and gain importance.
3. **Human-in-the-loop** — Automation assists but never overrides. Feature usage (keep/drop with reason), Level of Measurement overrides, ordinal rankings, and split strategies are all user-controlled.
4. **Regulatory readiness** — The platform is designed with model governance in mind: audit trails, feature documentation, stability metrics (PSI/CSI), multicollinearity detection (VIF), and explainability (SHAP) are built in — not bolted on.
5. **Native categorical handling** — Modern gradient-boosting algorithms (XGBoost, LightGBM, CatBoost) handle categorical features natively. DeclarAI leverages this instead of forcing lossy encoding schemes, preserving information and reducing preprocessing complexity.

### Goals

- Provide a **guided, step-by-step model development pipeline** accessible to both data scientists and model validation teams
- Make **feature selection and importance ranking** rigorous and multi-metric (SHAP, gain, VIF, combined scoring)
- Ensure **every modeling artifact is explainable** and ready for internal review or regulatory submission
- Support the full lifecycle: data import → preprocessing → encoding → training → explainability → feature selection → evaluation → deployment

---

## Architecture

| Layer | Technology | Port |
|-------|------------|------|
| **Frontend** | Angular 18 · Angular Material · Plotly.js | `4300` |
| **Backend** | Django 5.1 · Django REST Framework · Python 3.12 | `8001` |
| **Infrastructure** | Docker Compose (2 services, hot-reload dev volumes) | — |
| **Database** | SQLite (development) | — |

---

## Pipeline Steps

The platform orchestrates model development through a **linear, progressive pipeline**. Each step unlocks the next only when its predecessor is complete.

### 1. Pipeline Declaration

The user selects a modeling pipeline type to frame the entire workflow:

| Pipeline | Description |
|----------|-------------|
| **Boosting Pipeline** | XGBoost / LightGBM / CatBoost with native categorical support |
| **Logit Pipeline** | Logistic regression (planned) |
| **Credit Scoring Pipeline** | Scorecard development workflow (planned) |
| **Anomaly Detection Pipeline** | Unsupervised anomaly detection (planned) |

### 2. Data Import & Declaration

- **File upload**: CSV (semicolon, comma, tab, space separators) and Excel (.xls, .xlsx)
- **Multi-file merge**: Column-wise (horizontal) or row-wise (vertical) concatenation with automatic duplicate column renaming
- **Header control**: Toggle whether the first line is a header; choose which sheet to read for Excel files
- **Auto-detection**: MIME-type validation, column type inference, date detection
- **Data Dictionary generation**: For every column, the system generates:
  - `Feature_Name` — column identifier
  - `Feature_Description` — user-editable description (persisted in DB)
  - `Data_Type` — inferred data type
  - `Level_of_Measurement` — nominal, ordinal, interval, ratio, or unknown
  - `Model_Usage` — Yes/No toggle to include/exclude from modeling
- **Data preview**: First rows displayed for validation after upload
- **Target variable declaration**: Explicit selection of the target column

### 3. Data Purification (Preprocessing)

A configurable, sequential purification pipeline. Each step reports exactly what it removed and why.

**Available purification options:**

| ID | Option | Description |
|----|--------|-------------|
| 1 | Column-wise duplicate drop | Remove identical columns |
| 2 | Row-wise duplicate drop | Remove identical rows |
| 3 | Zero-variance drop | Remove columns with no variation |
| 4 | Perfect-correlation drop | Remove one of two perfectly correlated features |
| 5–8 | Correlation threshold drop | Remove one of two features correlated above threshold (0.95 / 0.90 / 0.85 / 0.80) |

**Output:**
- Per-step breakdown: which columns were dropped, which option triggered it
- Total rows removed across all steps
- Row count before/after summary
- Processed file saved for downstream steps

**Train/Test Split Configuration:**
- **Random split** with configurable percentage
- **Out-of-Time (OOT) split** with date column selection, cutoff date, or percentage-based split

**Data Quality Metrics** (computed per feature on train/test splits):
- **PSI (Population Stability Index)** — 3-month and 6-month rolling time-series
- **CSI (Characteristic Stability Index)** — distribution drift detection
- **JSD (Jensen-Shannon Divergence)** — probability distribution comparison

### 4. Encoding Analysis

Before training, the system analyzes all categorical features and generates an **encoding plan** displayed in the modeling UI:

| Plan Column | Description |
|-------------|-------------|
| Feature | Column name |
| Description | From data dictionary |
| Level of Measurement | User-editable dropdown (nominal / ordinal) |
| Strategy | Native categorical (primary), with fallbacks |
| Unique Values | Category count |
| Fallback Strategy | Applied when native support is insufficient |
| Fallback Reason | Why the fallback was triggered |
| Ordinal Ranking | User-configurable category order (for ordinal features) |

**Fallback encoding strategies** (based on LoM and unique count):
- Nominal → Label Encoding
- Ordinal, nunique < 5 → One-Hot Encoding (null as new category)
- Ordinal, 5 ≤ nunique ≤ 10 → Ordinal Encoding (user-ranked categories)
- Ordinal, nunique > 10 → Target Encoding (category-target mean)

### 5. Modeling

Unified encoding + training in a single step. The algorithm selection auto-determines the encoding methodology.

**Supported algorithms:**

| Algorithm | Native Categorical | Implementation |
|-----------|-------------------|----------------|
| **XGBoost** | `enable_categorical=True` | `xgboost.XGBClassifier` |
| **LightGBM** | Built-in categorical type | Planned |
| **CatBoost** | Built-in categorical pools | Planned |

**Training details:**
- Automatic train/validation split (80/20) with stratification
- Binary classification: auto-detect 0/1 targets; fallback to factorization
- Multi-class support: up to 50 unique target classes
- NaN handling: numeric columns filled with mean; categorical NaNs handled natively
- All-NaN columns dropped automatically

**Cross-validation metrics** (5-fold stratified CV):

| Metric | Description |
|--------|-------------|
| **AUC-ROC** | Area under the ROC curve (mean ± std across folds) |
| **Accuracy** | Classification accuracy |
| **F1 Score** | Harmonic mean of precision and recall |
| **Precision** | Positive predictive value |
| **Recall** | Sensitivity / true positive rate |
| **Log-Loss** | Logarithmic loss (cross-entropy) |

**CV visualizations:**
- ROC curves per fold + mean curve with std band
- Precision-Recall curves per fold
- Micro-averaged PR curve

### 6. Explainability

#### 6.1 SHAP Beeswarm Plot

Interactive, Plotly-based SHAP beeswarm visualization:
- Up to 40 features displayed, sorted by mean |SHAP impact|
- Each dot = one sample; color = feature value (red = high, blue = low)
- Original categorical labels restored via encoding report (not encoded integers)
- Toggle null-value visibility
- Directional impact computation:
  1. Primary: Top-vs-bottom quantile mean SHAP difference
  2. Fallback: Spearman rank correlation between feature values and SHAP values
  3. Final fallback: Sign of mean SHAP value

#### 6.2 Selected Features Table

A comprehensive, **fully sortable** feature-ranking table:

| Column | Description |
|--------|-------------|
| **Feature** | Clickable → opens Feature Card modal |
| **Description** | From Data Dictionary |
| **\|Impact\|** | Mean absolute SHAP value (primary explainability metric) |
| **Signed Impact** | \|Impact\| × direction (positive = increases prediction) |
| **Gain** | Tree split gain importance from the boosting model |
| **VIF** | Variance Inflation Factor — multicollinearity detection |
| **SHAP %** | ECDF-rank percentile of \|Impact\| [0–1] |
| **Gain %** | ECDF-rank percentile of Gain [0–1] |
| **Combined** | Geometric mean: C = √(SHAP% × Gain%) |
| **Usage** | Keep / Drop with mandatory reason for drops |

**Combined Score — Unified Feature Ranking:**

The Combined Score solves the problem of ranking features when SHAP and Gain disagree. The methodology:

1. For each feature *i*, compute the absolute SHAP impact *s_i* and gain importance *g_i*
2. Convert each to an **ECDF-rank percentile** in [0, 1] — full precision, no early rounding:
   - *q_i^(S)* = ECDF-rank(*s_i*)
   - *q_i^(G)* = ECDF-rank(*g_i*)
3. Combine using the **geometric mean**: *C_i* = √(*q_i^(S)* × *q_i^(G)*)
4. Round only at display time (4 decimal places)

Properties:
- **Scale invariance** — SHAP and gain operate on different scales; ECDF normalization eliminates this mismatch
- **Robustness** — Resistant to heavy-tailed distributions common in SHAP values
- **Agreement-aware** — Geometric mean rewards features that rank high on *both* metrics; a feature that is top-1 on SHAP but bottom on gain will not dominate

**VIF (Variance Inflation Factor):**
- Calculated via `statsmodels.stats.outliers_influence.variance_inflation_factor`
- Measures multicollinearity: how well each feature is predicted by all other features
- Color-coded thresholds: ≤ 5 (normal), 5–10 (orange — high), > 10 (red — severe)
- Categorical features converted to numeric codes; zero-variance columns excluded
- Helps identify redundant features that inflate model variance

**Table Sorting:**
- Click any column header to toggle ascending ↑ / descending ↓
- Sort indicator (⇅ / ↑ / ↓) on every column
- Default: Combined Score descending
- Null values always pushed to end regardless of direction

#### 6.3 Feature Card

A per-feature deep-dive modal accessible by clicking any feature name in any table:
- **Data quality summary**: null count, unique values, data type, descriptive statistics
- **Distribution visualization**: histograms for numeric, bar charts for categorical
- **Importance context**: SHAP rank highlighted among all features
- **Data Dictionary info**: description, Level of Measurement, Model_Usage status

### 7. Sequential Feature Selection (SFS)

Automated feature selection using sequential forward and/or backward search:

- **Forward selection**: Starts with zero features, adds the best one at each step
- **Backward selection**: Starts with all features, removes the least useful at each step
- **Both directions** can run in the same session
- **Cross-validated scoring** at every step (AUC-ROC, accuracy, F1, etc.)
- **Real-time progress**: Progress bar with percentage, current metrics, completed steps
- **Step detail modal**: Per-step view showing:
  - Selected features at that step
  - CV-based performance metrics
  - SHAP importance changes from previous step
  - Gain importance per feature
  - Stability metrics (PSI/CSI)
- **Feature progression charts**: SHAP and Gain importance tracked across all steps
- **Fullscreen modal** for detailed analysis
- **Configurable stopping criteria**: Min/max feature count, percentage change thresholds per metric

### 8. Evaluation

Model performance evaluation (under development):
- Summary metrics display
- Comparison across model variants

### 9. Deployment

Model deployment interface (under development):
- Export and serve trained models

---

## AI Assistant observability (Prometa integration)

The backend's AI Assistant emits structured agent telemetry through
[`prometa-sdk`](https://github.com/prometa-ai/orchestra-python-sdk)
(≥ 0.10.1) to the **Prometa Agentic Lifecycle Intelligence Platform**
for tracing, evaluation, and lifecycle governance.

**Integration point**:
[`backend/ai_assistant/prometa_config.py`](backend/ai_assistant/prometa_config.py)
configures the SDK client at boot and exposes `@prometa_config.workflow / .agent / .tool`
decorators consumed throughout the assistant's action layer.
OpenAI client calls are auto-instrumented via
`prometa.integrations.openai.install()` — every
`client.chat.completions.create(...)` invocation emits a child span
carrying token usage, cost, prompt/completion text, and model name.

**Configuration** is via environment variables:

| Var | Default | Purpose |
|---|---|---|
| `PROMETA_ENDPOINT` | (off) | OTLP ingest URL, e.g. `https://prometa.example.com/api/v2/otlp/v1/traces` |
| `PROMETA_API_KEY` | (off) | Prometa tenant API key |
| `PROMETA_SOLUTION_ID` | `declarai-assistant` | Logical solution identifier in the platform's registry |
| `PROMETA_AGENT_NAME` | `declarai-agent` | Logical agent name (auto-registered) |
| `PROMETA_AGENT_ID` | `declarai-agent-staging` | Stable agent id/slug; use the Prometa bundle `agentId` for runner executions |
| `PROMETA_STAGE` | `staging` | `development` / `staging` / `production` |

Leaving `PROMETA_ENDPOINT` unset disables telemetry entirely
(no-op decorators, no network calls). The SDK and platform are
loosely coupled — DeclarAI's pipeline runs identically with or
without Prometa wired up.

**Available SDK helpers** (v0.5.0+):

- Lifecycle decorators (`@prometa.workflow / .agent / .tool / .task`)
  for span boundaries and parent/child relationships.
- Session grouping via `set_session_id(conversation_id)` so chat-style
  AI Assistant traces aggregate into a single Session Explorer row.
- Correlation-chain setters (`set_customer_id`, `set_user_id`,
  `set_request_model`, `set_tool_name`) that light up the platform's
  canonical correlation chain — opt-in extras that bridge AI Assistant
  telemetry to the org's CRM / data warehouse identifiers.
- Public span metadata setters (`set_attribute`, `set_attributes`) used by
  DeclarAI's wrapper to preserve producer-owned fields such as
  `declarai.mcp.*` while emitting tenant-neutral tool keys
  `gen_ai.tool.name` and `prometa.tool_name`.
- AML v0.4 instrumentation primitives (`guardrail`, `pii_filter`,
  `memory_read`, `record_retry_attempt`, …) for the platform's
  41-feature agent-maturity scoring.
- Assistant-answer feedback helpers (`record_user_feedback`,
  `set_user_feedback`) for thumbs, ratings, and redacted user comments.

See the [SDK README](https://github.com/prometa-ai/orchestra-python-sdk)
for the complete API surface and the platform's
[`correlation-id-design.md`](https://github.com/caglarsubas/agent-hook-v2/blob/main/resources/correlation/correlation-id-design.md)
for the chain semantics.

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Run
```bash
docker compose up --build -d
```

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:4300 |
| **Backend API** | http://localhost:8001 |

### Stop
```bash
docker compose down
```

### Rebuild after code changes
```bash
docker compose up --build -d
```

Both services mount source directories as volumes for hot-reload during development.

---

## Project Structure

```
auto-ml/
├── backend/
│   ├── backend/              # Django project settings, URL routing, CORS config
│   ├── declaration/          # Data import, data dictionary, target selection
│   │   ├── models.py         # Declaration (file upload), DataDictionary (per-column metadata)
│   │   ├── views.py          # File upload, merge, preview, data dictionary CRUD
│   │   └── serializers.py    # REST serialization
│   ├── preprocessing/        # Data purification pipeline
│   │   ├── views.py          # Purification apply, DATQ time-series, data quality
│   │   └── data_quality.py   # PSI, CSI, JSD calculations, train/test split logic
│   ├── encoding/             # Categorical encoding analysis
│   │   ├── encoding_utils.py # analyze_categorical_features(), fallback strategies
│   │   └── views.py          # EncodingAnalyzeView API endpoint
│   ├── modeling/             # Model training, SHAP, VIF, combined scoring, SFS
│   │   ├── views.py          # ModelingStartView, SFS endpoints, status polling
│   │   └── sfs_utils.py      # Forward/backward SFS with progress tracking
│   ├── feature_card/         # Per-feature explainability
│   │   └── views.py          # Feature statistics, distribution, quality summary
│   ├── evaluation/           # Model evaluation (planned)
│   ├── deployment/           # Model deployment (planned)
│   ├── tests/                # Test suite
│   │   ├── test_unit.py      # 25 unit tests
│   │   ├── test_functional.py # 13 functional tests
│   │   ├── test_regression.py # 6 regression tests
│   │   ├── test_integration.py # 4 integration tests
│   │   └── test_uat.py       # 5 UAT tests
│   ├── conftest.py           # Shared pytest fixtures
│   ├── pytest.ini            # Test configuration with markers
│   └── requirements.txt      # Python dependencies
├── frontend/
│   └── src/app/
│       ├── model-development/  # Pipeline orchestrator (step navigation, state management)
│       ├── declaration/        # Data import UI (file upload, data dictionary editing)
│       ├── preprocessing/      # Purification UI (option selection, results display)
│       ├── modeling/           # Training + explainability UI (encoding plan, SHAP, table, SFS)
│       ├── sfs/                # Sequential Feature Selection components
│       ├── feature-card/       # Feature detail modal
│       ├── evaluation/         # Evaluation UI
│       ├── deployment/         # Deployment UI
│       ├── services/
│       │   ├── data.service.ts   # HTTP client for all backend API calls
│       │   └── shared.service.ts # Cross-component state (BehaviorSubjects)
│       ├── home/               # Landing page
│       └── login/              # Authentication UI
├── docker/
│   ├── backend.Dockerfile      # Python 3.12, system deps, pip install
│   └── frontend.Dockerfile     # Node 20, Angular CLI, ng serve
├── docker-compose.yml          # Service definitions, port mapping, volume mounts
├── run_tests.sh                # Unified test runner with grouped reporting
└── ToDoS.txt                   # Development roadmap and pending items
```

---

## Technology Stack

### Backend

| Package | Version | Purpose |
|---------|---------|---------|
| Django | ≥ 5.1 | Web framework & ORM |
| Django REST Framework | ≥ 3.15 | REST API layer |
| pandas | ≥ 2.2 | DataFrame manipulation, data quality |
| numpy | ≥ 1.26 | Numerical computation |
| scipy | ≥ 1.11 | Statistical functions (PSI, JSD, distributions) |
| scikit-learn | ≥ 1.4 | Train/test split, CV, classification metrics |
| XGBoost | ≥ 2.0 | Gradient boosting with native categorical support |
| SHAP | ≥ 0.42 | TreeExplainer, beeswarm plots, feature attribution |
| statsmodels | ≥ 0.14 | Variance Inflation Factor (VIF) |
| mlxtend | ≥ 0.23 | Sequential Feature Selection utilities |
| matplotlib | ≥ 3.7 | SHAP summary plot rendering |
| openpyxl / xlrd | — | Excel file reading (.xlsx / .xls) |
| python-magic | ≥ 0.4 | MIME-type detection for uploaded files |
| django-cors-headers | ≥ 4.3 | Cross-origin requests (frontend ↔ backend) |
| openai | ≥ 1.0 | LLM client for AI Assistant action layer |
| [prometa-sdk](https://github.com/prometa-ai/orchestra-python-sdk) | ≥ 0.10.1 | Agent telemetry — emits OTLP traces, generic tool keys, agent correlation, and assistant-answer feedback to the Prometa platform |
| redis | ≥ 5.0 | Cache + session store for AI Assistant |

### Frontend

| Package | Version | Purpose |
|---------|---------|---------|
| Angular | 18.2 | Single-page application framework |
| Angular Material | 18.2 | UI component library (dropdowns, dialogs, progress bars) |
| Plotly.js | ≥ 2.35 | Interactive charts (beeswarm, ROC, PR, SFS progression) |
| mathjs | ≥ 13.1 | Numeric utilities |
| RxJS | ~7.8 | Reactive state management, observables, polling |
| xlsx | ≥ 0.18 | Client-side spreadsheet utilities |

---

## Testing

The project has a comprehensive test suite with 5 categories, enforced by a **pre-commit git hook** that blocks commits if any test fails.

```bash
# Run all tests inside Docker
docker exec auto-ml-backend-1 python -m pytest -v

# Run by category
docker exec auto-ml-backend-1 python -m pytest -m unit -v
docker exec auto-ml-backend-1 python -m pytest -m functional -v
docker exec auto-ml-backend-1 python -m pytest -m regression -v
docker exec auto-ml-backend-1 python -m pytest -m integration -v
docker exec auto-ml-backend-1 python -m pytest -m uat -v

# Unified runner with grouped reporting
./run_tests.sh
```

| Category | Count | Scope |
|----------|-------|-------|
| **Unit** | 25 | Models, serializers, utility functions |
| **Functional** | 13 | API endpoint behavior |
| **Regression** | 6 | Previously fixed bugs (str dtype, CSS, etc.) |
| **Integration** | 4 | Multi-component workflows |
| **UAT** | 5 | End-to-end user scenarios |
| **Total** | **53** | — |

**Important**: All CSV uploads in tests must include `column_separator: 'comma'` because the backend defaults to semicolon.

---

## Git Branching & Versioning

**Branch naming convention:**

```
feature/v{x}.{y}.{z}-{YYYYMMDD}-{short-description}
```

| Segment | Meaning |
|---------|---------|
| `x` | Core function changes/additions |
| `y` | Subsidiary function changes/additions |
| `z` | Bug-fix or hot-fix |

**Version History:**

| Version | Date | Highlights |
|---------|------|------------|
| **v2.8.0** | 2026-03-22 | VIF multicollinearity metric, ECDF-rank percentile scoring, Combined feature ranking (geometric mean), sortable Selected Features table, comprehensive README |
| **v2.7.0** | 2026-03-19 | Merged encoding into modeling step, native categorical SHAP fix, encoding plan UI in modeling component |
| **v2.6.1** | 2026-03-17 | Feature Card importance tab — highlight selected feature, auto-load on click |
| **v2.6.0** | 2026-03-15 | Gain column in feature table, SFS progression charts, fullscreen modal |
| **v2.5.0** | 2025-10-27 | Sequential Feature Selection (SFS) v1 |
| **v2.4.x** | 2025-10-15–19 | SHAP beeswarm plot, impact sign direction, Feature Card explainability tab, UI style fixes |

---

## Roadmap

- **Feature sorter** using combined impact and gain metrics as input to SFS
- **Export results** — CSV/Excel export of SFS results and feature tables
- **Stopping criteria** — %-change of metrics, min/max feature count selection in SFS
- **Parallel execution** — Multi-core SFS (n_jobs parameter)
- **Causality features** in the explainability tab
- **3-layer layout** — Left progress navigation, middle workspace, right assistant chat
- **LightGBM & CatBoost** — Full algorithm implementations (currently XGBoost only)
- **Logistic regression pipeline** — Scorecard-oriented workflow
- **Anomaly detection pipeline** — Unsupervised modeling support
