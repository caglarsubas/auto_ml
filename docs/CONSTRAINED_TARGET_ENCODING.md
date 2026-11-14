# Constrained target encoding

Use the Modeling encoding plan to select **Target Encoding** for a predictor.
Run preprocessing with the intended group or out-of-time split first. The
fit uses the frozen raw-input recipe and supports binary classification and
regression. For an out-of-time split, declare both the prediction-date column
and the date when each outcome becomes available. Add the entity column when
the same entity can occur more than once.

The encoder fits again inside each development training partition, including
the folds used for feature selection and tuning. Grouped encoding applies a
mapping learned from other groups to each held-out group. Out-of-time
encoding keeps equal timestamps together. Each learned mapping uses only
earlier rows whose outcome windows closed strictly before the first prediction
in the application block. When an entity column is declared, the mapping
excludes every entity in that block. Initial blocks with insufficient mature
history receive a fixed value of 0.5 for binary classification or zero for
regression. These values use no outcome observations. An invalid later
block or a population with no learned block fails. Missing split controls,
small group populations, and unsupported tasks require a revised declaration.
There is no shuffled fallback for a constrained encoder.

Declared target-encoded predictors retain their raw-recipe category values
through the purifier. This prevents data from a later block from influencing
category replacement in an earlier mapping. Other predictors continue through
the requested purifier rules. The encoder uses the canonical training label and
a smoothed mapping. For validation and scoring, it freezes a map from the
whole parent fit partition and uses that partition's mean for unseen values.
Missing values have their own key. Scoring CSV and Excel files read declared
target-encoded columns as text. CSV score receipts bind the text-column parser
and the offline verifier uses it. JSON scoring accepts category strings for
exact text identifiers. The fitted map uses the values present in the frozen
raw snapshot, including any normalization performed at ingestion.

The fold provenance download retains the ordered parent fit, inner fit and
application rows, warm-up and fitted maps. Scoring bundles retain the full
training map and its prior. The offline fold verifier checks the recorded
structure against the declared split. Independent reproduction of time, entity
and outcome eligibility requires the pinned raw snapshot.

Each new encoder fit is limited to 256 KiB of evidence. The existing
job-result and export limits also apply to aggregate evidence. Large cardinality
or extensive search may require smaller cohorts, fewer encoded columns or a
smaller search budget. Existing historical random encodings remain readable.
An imported pre-encoded CSV cannot establish leakage-free historical lineage.
