# Prediction scope qualification

P185 qualifies D01-T02 for the documented prediction entrypoints. New runs
record a version 2 prediction contract with the declared population and
exclusions, feature availability, horizon, and label maturity. A saved
pipeline requires an explicit declaration update before any of those choices
can change during training admission. The native preview shows the accepted
scope before submission. Reviews, model cards, candidate exports, and scoring
bundles carry the same versioned scope.

## Availability and population

- The declared input represents the eligible population. Population and
  exclusion text accompanies the evidence. Intake does not filter rows based on
  prose. Missing labels block training and assessment.
- The input policy declares features available at prediction time. Overrides may
  declare a named column available or excluded. Unknown columns, target
  overrides, validation controls marked available and contradictory overrides
  stop with a diagnostic. An excluded control may still be used for validation.
  A feature declared forbidden remains excluded if preprocessing removed it.
- Available predictors can be left unselected. Native training rejects a
  selected predictor prohibited by policy. Legacy training excludes prohibited
  columns from fitting and exact scoring verifies its frozen predictor scope
  and declaration against the run and assessment.

## Executable outcome windows

Native numeric out-of-time training supports an optional
`target_contract.outcome_window` profile. Supply 1–3650 `horizon_days`,
0–3650 `maturity_lag_days`, and a timezone-aware ISO `development_as_of`.
Use separate prediction and label-end columns with ISO dates or timestamps.
Each label-end must be at least the declared horizon after its prediction.
The effective maturity date is the label-end plus the lag. Every development
row must be mature by the development as-of time. Temporal training folds use
only labels that matured strictly before their validation boundary.

The protected assessment uses the same horizon and lag with the reviewer's
own assessment as-of time. The seal validates the window controls before
publishing protected input. Replay revalidates their maturity and requires
development labels to have matured before the assessment begins. Executable
windows are unsupported on random and grouped-only validation and in legacy
training. Temporal validation can additionally enforce entity separation.

Free-text scope remains available across supported tasks and validation
strategies. Its population, real-world availability and maturity claims require
attestation and review. The product does not derive a duration or a row filter
from prose. Credit vintages, delayed outcomes and selection-bias analysis are
separate D13 work.

## Evidence

Regression coverage checks saved-scope conflicts, availability and timestamp
errors, and fold purging using effective maturity. Protected replay refits a
native temporal regression model and reproduces the held scores and window
checks. The scoring parity matrix checks the declared scope through legacy
training, model cards, exact packages and batch scoring. The browser scenarios
verify the preview and queued contract with explicit availability overrides.

Existing version 1 artifacts retain their recorded hashes and semantics. Exact
offline replay uses the matching runtime recorded with the package. The tracker
reports the exact PR and independent merged-main qualification separately.
