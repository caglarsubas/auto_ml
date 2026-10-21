# Incident evidence verification and operator runbook handoff

P125 adds offline verification of the P124 incident export and an investigation handoff for the Linux root installation operator. Use the trusted installation tool checkout. It reads the evidence file and writes a new private handoff; it does not open the plan, read credential deliveries, contact Docker, query PostgreSQL, call HTTP/MCP, reconcile jobs or repair services. Imported installation helpers provide only encoding and private filesystem operations in this path.

## Trust and invocation

Obtain the incident evidence SHA-256 from the separately retained P124 collection receipt. Obtain the plan manifest digest, installation ID and initialization ID from the trusted installation records. Do not copy these expected values from the file being verified and call them independent evidence. A matching checksum confirms consistency with those supplied records; it does not authenticate who created the file, prove current health or confer approval.

```sh
python3 scripts/private_queue_evidence.py /secure/operator-evidence/incident.json \
  --expected-sha256 SEPARATELY_RETAINED_EVIDENCE_SHA256 \
  --expected-plan-sha256 TRUSTED_PLAN_MANIFEST_SHA256 \
  --installation-id TRUSTED_INSTALLATION_ID \
  --initialization-id TRUSTED_INITIALIZATION_ID \
  --max-age-seconds 900 \
  --output /secure/operator-evidence/handoff.json
```

Both input and output require an existing root-owned `0700` directory with trusted, non-writable, ACL-free ancestors. Input must be a root-owned `0600` regular file, one hard link, no symlink or ACL. Reads are bounded to 263,168 bytes, including the wrapper; canonical evidence is limited to 262,144 bytes. Output uses P124's staged, fsynced, atomic Linux no-replace publication and `0600` permissions. It never replaces an existing target. Failure prints only `queue_evidence_verification_or_handoff_failed`; no raw file contents, driver errors or secrets are echoed.

The verifier rejects duplicate JSON keys, non-finite values, invalid UTF-8, unsupported schemas/fields, mismatched digests/context, invalid types/bounds, missing roles and contradictory service/truncation/authority flags. Observation timestamps must be UTC, ordered and no more than 30 seconds ahead of the verifier clock. This is a clock sanity check, not attestation. The selected age threshold (default 900 seconds, configurable 1–86,400) labels older evidence rather than discarding incident history; it is not a universal operational gate. Offline verification never refreshes the evidence.

P126 additionally reconciles queue metadata before creating a handoff. Failed/blocked totals must match their signals, active-lease categories are disjoint, and the incident union must fit the unfinished population while allowing overlapping expiry/attempt/lease signals. Each sampled row's flags are recomputed from its state, attempts, expiry and lease at the recorded queue observation time. Complete samples must match every aggregate signal; truncated samples must fit both the reported counts and the maximum contributions of omitted rows. The queue observation must fall within the enclosing collection interval. A freshly matching digest cannot override these checks.

The omitted remainder is checked separately after subtracting the sample: remaining incidents must have possible signal contributions, and remaining lease incidents must fit the remaining active-job population. A plausible global total cannot conceal an impossible unsampled remainder.

The handoff's verification metadata records `queue_consistency: cross_checked_metadata` for an observed snapshot and `unavailable` when there was no queue observation to check. `sample_order` separately records `newest_first`, `not_newest_first` or `unavailable`, comparing creation time then UUID. Out-of-order samples remain inspectable and unchanged, with an explicit limitation and investigation step. Counts for unavailable observations stay null. These necessary relationships cannot prove database truth, completeness beyond the bounded sample, collection authenticity, current health or recovery authority. Unknown state counts, disabled admission, historical failures and valid truncation remain explicit rather than being silently discarded or treated as healthy.

## Investigation handoff

The new `private_queue_operator_handoff_v1` file wraps `evidence` and its canonical SHA-256, just like the incident export. It binds the source digest, installation/initialization/plan/profile pins, original observation interval, verification time and age. It includes service attention references, observed/unavailable queue status, overlapping signal counts, explicit truncation and at most 50 project/job/dataset/revision references. Unavailable counts remain null. Source free-text guidance is never rendered as instructions; the handoff uses fixed instructions from the trusted tool.

1. Retain the original incident file, independently recorded digest, trusted installation pins and handoff under customer retention and controlled-egress policy. These identifiers are installation-confidential.
2. Compare the observation interval and age with the incident timeline. A stable or empty historical sample does not certify present health. Unstable, truncated and unknown-state evidence requires those limitations to accompany the investigation.
3. For service attention or unavailable queue observations, involve the installation owner. Correlate existing lifecycle readiness and API/database/worker/dispatcher/broker evidence through their authorized read-only workflows. This verifier performs no connectivity or live-health test.
4. For queue signals, involve the relevant project owner and inspect the existing revision-pinned operational handoff under project authority. Counts overlap and terminal failures may be historical. Do not infer broker delivery from queue metadata. Do not edit state, raise attempt limits, replay or recreate requests from the report.
5. Record a named investigation owner, findings, evidence references, unresolved limits and the separately authorized next action in the customer's incident process. The generated handoff does not fabricate ownership, decisions or sign-offs.
6. Preserve possible protected-outcome access for interrupted assessments and their exploratory status. Maintenance, bounded recovery, new requests, independent model review, production use and incident closure each retain their separate authority and evidence requirements.

Verification and handoff are separate from coordinated backup/restore, upgrade/rollback, customer deployment, release qualification and acceptance. All corresponding approval/health flags remain false. A new observation, maintenance action or job request must use its own approved workflow.

## Qualification

Additive tests cover independent pins, tampering, malformed/schema-conflicting evidence, age/unavailability/degraded observations, bounded revision-pinned samples, and unsafe file types/permissions/links. The existing owned Linux fixture verifies a real P124 export, invokes the actual handoff CLI, checks private/no-overwrite publication, rejects tampering and wrong context, and preserves the source and service states. Existing physical, private execution/recovery/restore and browser workloads remain mandatory with unchanged limits.
