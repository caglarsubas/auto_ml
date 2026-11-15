# Immutable stage publication

Preprocessing publishes a directory for each request. The receipt binds the input digest, processed and raw CSVs, purifier recipe, split membership, fitted state, data quality summary and result. The status endpoint accepts an exact processed file or request UUID. Diagnostics for a version use its recorded partition. Versioned training binds the receipt to the execution manifest and retains it through candidate selection. Earlier flat inputs remain readable with historical provenance recorded as unverified.

An optional preprocessing request UUID lets a client recover the same published stage after an interrupted response. A retry with different inputs is rejected. The current result points to a verified immutable stage. The dataset lock protects adoption and refresh of compatibility files. Replaying an older request returns that version and checks the recorded predecessor before advancing the current pointer. Encoding publishes the CSV and its metadata together in a separate version directory.

Durable legacy workers publish from their isolated attempt directories. Publication exposes each complete execution as one directory and each search archive as an immutable file. The queue lease, recorded file hashes, adoption intent and current model checks fence publication. A missing acknowledgement can be repaired by verifying and reusing files that already match. A path occupied by different bytes blocks replay.

Evaluation publishes its two exact artifacts and manifest together. An assessment of an older execution remains available by its receipt ID. Updating the current evaluation, model card and compatibility pipeline requires the current execution to still match. Outcome access remains attributable when publication is interrupted.

An exact package build accepts an optional request UUID. Retries recover the package with the same ID and digest and can complete an interrupted adoption while its predecessor still owns the current pointer. A newer adoption wins when the current pointer changes. The browser retains the package request UUID while retrying the same execution and assessment. Historical callers can continue to create successive package versions.

Qualification uses concurrent runs on one dataset, interrupted writes and adoption, replay after a missing acknowledgement, and exact historical reads. The publication boundary assumes the supported shared filesystem and the existing database queue. Independent model reproduction and scoring parity have their own acceptance criteria.
