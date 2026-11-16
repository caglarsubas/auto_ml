# Exact scoring parity

D04-T02 checks the values passed to final assessment against the scores from the corresponding immutable scoring package. It uses approved model state from the matching DeclarAI runtime. The assessment still records its holdout access and evidence status. Independent refit and assessment reproduction belong to D09.

| Model family | Score types exercised |
|---|---|
| XGBoost | Binary probabilities with isotonic calibration, multiclass probabilities, regression |
| LightGBM and CatBoost | Binary probabilities with Platt calibration, multiclass probabilities, regression |
| Logistic regression and scorecard | Binary probabilities with Platt calibration |
| Isolation forest | Anomaly rankings |

The 12-case matrix fits real models, applies their recorded preparation, and captures predictions passed to the assessment metrics. It compares exact bundle scores at absolute tolerance `1e-9` and relative tolerance `1e-7`. The cases cover reversed positive labels, class order, numeric imputation, missing and unseen categories, leading zeros in category labels, reversed rows and columns, repeated rows, and uneven chunks. The matrix includes native categories, one-hot and ordinal encoders. Additional regressions exercise raw purifier replay and candidate-local encoding, target-encoding replay, and required-transform and calibrator removal. These are synthetic correctness tolerances. Workload and production-use qualification remain separate.

New exact scoring packages bind input schema, fitted imputation, encoders, class mapping, and calibration to the recorded execution and assessment. Scoring uses the recorded feature sequence and preserves input row order. An incomplete artifact, a changed score contract, or an unavailable required transform stops scoring. CSV scoring uses recorded text columns before type inference and rejects embedded NUL characters and surplus fields that would silently become row labels.

Synchronous, durable queued, and offline scoring use the bundle scorer. The offline verifier can check reversed rows, reversed columns, and every requested chunk size using the recorded runtime and input bytes. Historical packages retain their original version and independent replay requirements. Publishing a new exact package from an older fit with an unstable native integer category or WOE level mapping requires a refit. The portable XGBoost candidate scorer covers binary classification and regression with its documented numeric-input schema.

See [offline score verification](OFFLINE_SCORING_IMPLEMENTATION.md) and [durable CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md) for invocation and receipt details.
