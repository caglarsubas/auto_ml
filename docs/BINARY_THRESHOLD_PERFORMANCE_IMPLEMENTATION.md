# Binary threshold evaluation performance (P60)

P60 removes repeated metric validation from supported binary threshold tables.
It follows PR #149, whose exact-head checks passed but whose independent main
qualification exceeded the existing 900-second PostgreSQL suite limit. The
original failure and partial receipts remain retained; no completed suite or
coverage result is inferred from them.

## Observed bottleneck and implementation

A disposable PostgreSQL profile of the unchanged 36 native-job cases recorded
128 threshold-table calls taking 27.997 seconds of 55.678 profiled seconds.
Database waits took 2.998 seconds. Repeated scikit-learn input/target validation
inside seven metric calls per threshold dominated the threshold work.

For nonempty, aligned, one-dimensional numeric binary outcomes, evaluation now
counts TP, FP, TN and FN directly and derives precision, recall, F1, F2,
accuracy and MCC. Threshold ordering, duplicate thresholds, inclusive `>=`
ties, default threshold values, zero-denominator conventions and row fields
remain unchanged. MCC uses floating factors to avoid fixed-width count overflow.
Other input shapes/types retain the existing scikit-learn validation path.
No fitted model, partition, target, objective or threshold-selection rule changes.

The same 36-case PostgreSQL profile passed after the change: threshold calls took
0.043 seconds, with total suite time changing from 53.700 to 46.215 seconds.
These are local measurements on separate fresh fixtures, not a controlled
capacity benchmark or a guarantee about CI runner speed. The total profile
also includes imports, coverage, real training, assessment and database work.

## Validation and boundaries

Twenty-eight new reference-parity cases compare every metric against the prior
scikit-learn calculation, including randomized and large samples, class absence,
boolean/integer/floating labels, ties, extreme and repeated thresholds, column
labels, nonfinite score comparisons and rejected inputs. The 65 focused
evaluation/cost/holdout checks pass. The full controlled SQLite suite passed
3,315 cases with six existing skips, zero failures, 75.13% line
coverage and 65.24% branch coverage in 288.554 seconds.
Exact-head private Linux qualification is required before adoption; their receipts are recorded with
the PR and in the source qualification evidence.

All existing scientific cases, assertions and data remain intact. Limits remain
120 seconds per test, 900 seconds for the PostgreSQL suite, 300 seconds for
native ownership, 50% minimum coverage, 15 maximum skips and two browser retries.
There is no new retry policy, reduced scope or weaker database durability setting.

D07 remains in progress. This change does not qualify customer deployment,
full installation lifecycle, backup/restore, upgrade/rollback, expert isolation,
release readiness or partner acceptance. The underlying repeated CI timing
variation is observed; its host-level cause has not been established.
