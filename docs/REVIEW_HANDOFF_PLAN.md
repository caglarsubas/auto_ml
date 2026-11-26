# Observed developer-to-reviewer handoff

## Purpose and starting point

A credit-model developer hands an exact assessed model to an independent reviewer. The reviewer should be able to identify the business question, the population and its limits, reproduce the assessment, explain why the candidate was chosen, and record a defensible finding or disposition. The first observation identifies what costs people time and what could lead to a wrong decision.

The planning baseline is merged PR #311 at `4caf6ba22537e0edce75be150c2be222f1f6c778`. At that revision, 28 of 66 delivery tasks were done, 31 were open and seven were blocked. D12-T03 was ready. D09-T03 still needed an independent reviewer and exercise approval. D22-T02 needed participating partners and comparable baseline measurements. The formal agentic pilot retains both intake paths, governed execution, independent reproduction and the subsequent two-partner value gate.

## Delivery sequence

| Step and owner | Work | Exit evidence |
| --- | --- | --- |
| 1. Product and roadmap maintainers | Put observed handoff effort, review iterations, help requests and validation defects beside the task distribution. Show the remaining scope and evidence owner for D02, D03, D04 and D08 even when all mapped tasks have qualified. Use the canonical ledger for the Markdown and web tracker. | The rendered tracker and export agree with the ledger. Missing observations read “Unmeasured”. Counts and percentages reconcile to the same inventory. |
| 2. Frontend and accessibility engineering, D12-T03 | Exercise a representative developer and reviewer journey in the rendered product. Cover project entry, locating the exact job, progress or failure guidance, finding assessment evidence, recording a finding, and understanding current or invalidated approval. Check keyboard-only traversal, focus after dynamic transitions, names and state announcements with an actual screen reader. Fix barriers and rerun the affected journey. | Record browser, assistive technology, exact application revision, fixtures, stages traversed, actual announcements or equivalent assistive evidence, defects and retest. Track any uncovered stage explicitly. |
| 3. Independent Review Owner, D09-T03 | Nominate an independent reviewer, approve the synthetic scope and provision separately controlled development and outcome inputs. Use the prepared native numeric XGBoost binary and regression cases. Have the reviewer run clean reproduction and decide each finding or disposition. Collect the observation sheet below. | Attributable assignment, exact manifest, input and runtime bindings, original replay reports, actual dispositions and the owner's acceptance decision. A reviewer may legitimately withhold approval. |
| 4. Product and two design partners, D22-T02 | Agree representative work and capture each team's current guided and single-agent baseline as soon as participants and data scopes are available. Use equivalent cases and the same policy, data and compute budgets for the later agentic comparison. | Matched observations per team and method, severity and counts of defects, compute and intervention cost, and the comparison against the proposed 30% combined-effort target. Report each comparison and its limitations. |
| 5. Product, ML and independent review | Examine the observation evidence and agree the smallest useful change. A recurring inability to explain why the candidate changed points to a guided D10 paired comparison. Uncertainty about eligible applicants, booked borrowers or mature outcomes points to a D13 population/maturity view. Track accessibility or custody friction under its own owner when it explains the delay. | A recorded decision links the friction, its impact, the chosen scope and the same task to repeat afterwards. If evidence is mixed or incomplete, collect one more targeted observation. |

Steps 1 and 2 can proceed with engineering fixtures. Reviewer scheduling and baseline collection can start in parallel. The first use of current UI and the pinned D09 exercise may run on different application versions. Record each version and its evidence separately. Any exercise on a newer build needs its own verified artifacts and scope. Deep D10 or D13 implementation follows the recorded finding and any explicit change to the canonical queue.

### Reviewer session

The project owner approved both synthetic cases and declared independence from their training and adoption proposals. The operator prepares the isolated project, reviewer account, pinned runtime, two sealed cases, clean replay environment and evidence handoff. The scope owner or named delegate confirms the exact case bindings at handoff. The reviewer starts each prepared replay, inspects the result, explains the population and evidence limits, records a finding or disposition under their own account, and decides whether the evidence merits technical approval. The observer handles timekeeping and records requests for help. The controlled exercise record holds the identity and scope declaration.

### Classification checkpoint on 23 November 2026

In the first guided session, the named reviewer signed in. The classification evidence was sealed and the protected exploratory assessment was recorded on 60 synthetic rows. The launcher stopped while displaying the saved assessment because the older record lacked chronology metadata. The session paused before independent replay or a reviewer disposition. The regression case had yet to begin.

At that checkpoint, both case dispositions and the scope owner's exercise decision were pending. Effort, waiting time, review iterations, help requests and validation defects were unmeasured.

### Synthetic exercise acceptance on 26 November 2026

The assigned reviewer independently reproduced each frozen model, its protected assessment result and its ordered scores in a separate Linux VM. The reviewer approved each technical review under their named account. The scope owner then accepted the two linked case records for D09-T03. The operator verified the recorded decisions against the countersigned inputs, runtime, replay reports and assessment digests.

| Case | Reserved synthetic cases | Exploratory result | Technical review |
| --- | ---: | --- | --- |
| Binary classification | 60 | ROC AUC 0.48333 | Approved, revision 2 |
| Regression | 60 | RMSE 1.21544 | Approved, revision 2 |

The reviewer resumed classification from its saved assessment. During regression, the review session expired before the inputs could be sealed. After signing in again, the reviewer confirmed the identical saved request and completed the replay. The three guided sessions are recorded in the roadmap. At owner acceptance, active effort, waiting time, returns for revision, help requests and verified defect counts remained unmeasured.

This acceptance covers reproducibility of the synthetic review workflow. Applicant separation and completed follow-up rely on the fixture declaration. Predictive usefulness remains unproven. Partner effort comparisons and production approval require separate evidence. The controlled exercise record retains identities, full decisions and original artifacts.

### Running the reviewer journey regression

From `backend/`, run `python -m pytest -q -c pytest.ini ../scripts/tests/test_reviewer_terminal_journey.py` on Linux with the backend test dependencies installed. The test starts a temporary loopback API, creates two synthetic candidates, and drives the participant launcher through a real pseudo-terminal. It exercises local and server passphrase rejections, pause and sign-in, both protected assessments, a technical approval, an open finding, and withheld exercise acceptance. A fresh Python process reproduces each assessment from the manifest and the two CSV files. The test checks the persisted decisions against the replay reports and original assessment digests.

Both an operator-provisioned bundle and the test start with `scripts/review_exercise/Start Review.command` and `participant.py`. The Mac adapter, `review_installation.py`, reads `API`, `INSTALLATION` and `REPLAY_SHA` from the approved bundle's `case_inputs.py`, alongside `ROOT`, `EXPECTED` and `payload`. The bundle supplies `clean_guest.py` for the separate Linux VM replay. The test supplies its own installation and fixture account. Its decisions are synthetic regression evidence. D09-T03 completion requires the assigned reviewer's exercise records and the scope owner's decision.

## Observation method

1. The observer records the method, case, application revision, supported model profile, team or synthetic scope, and a sanitized evidence reference. Agree the task, allowable materials, finish condition and defect definitions before starting. Keep named identities and protected inputs in the authorized review record.
2. Give the developer the business declaration and ask for a package ready for independent review. Give the reviewer the handoff and ask them to identify the target, population limits, reason for the model choice, status of protected assessment, and what they would approve, challenge or leave unresolved. Let each person navigate and explain in their own words. Record any prompt or intervention.
3. Measure each person's active minutes. Exclude waiting for compute or scheduling from active time and record wait time separately. A review iteration is one formal return to the developer for revision and resubmission. A help request is one explicit request for assistance. A validation defect is one distinct, evidenced error in data scope, method, calculation, governance or handoff, deduplicated by finding. Record severity, origin and disposition. A legitimate challenge or an honestly disclosed limitation is not itself a defect.
4. Record elapsed time, active time by role, iterations, help requests, independently verified defects by severity, observed comprehension, and which stages required assistance. A partial or failed exercise keeps its observations and explanation. Missing or unobserved measures remain unknown. Keep the independent reviewer's accept, exception or decline decision in the authoritative review workflow.
5. For the later value test, compute combined effort as developer plus reviewer active minutes. For each partner and baseline calculate `100 × (baseline − observed) / baseline` with a positive measured baseline. Show individual pairs, completion, defects/severity, oversight and resource costs alongside any aggregate. Use comparable cases and alternate order where practical to reduce rehearsal effects. An engineering rehearsal or a single named exercise can identify friction. Two partner comparisons with comparable scope and recorded defects are needed to evaluate the agreed organizational value gate.

### Observation sheet

| Field | What the observer records |
| --- | --- |
| Scope and binding | Sanitized case and team reference, method, exact versions, equivalent-case group and authorized source of the signed record |
| Timing | Active developer and reviewer minutes, separate waiting or interrupted time, observation window |
| Review work | Formal returns, help requests, interventions and the stage where each occurred |
| Quality | Distinct defects and severity, correctness of the reviewer's explanation, unresolved questions and the actual disposition |
| Follow-up | Primary obstacle, supporting observation, proposed owner and measurable repeat exercise |

The roadmap maintainer adds one sanitized entry per observed session in `release_qualification.handoff_observations`. Give it a stable `id`, case and team labels, scope (`Independent exercise` or `Design partner`), method (`Guided`, `Single agent` or `Agentic`), status (`Completed`, `Partial` or `Failed`), a finding summary and a controlled evidence reference. In `measures`, enter `developer_minutes`, `reviewer_minutes`, `wait_minutes`, `review_iterations`, `help_requests` and `validation_defects`. Use zero for a measured absence and JSON null for missing observations. The tracker derives combined active minutes only when both roles have a measurement. Retain severity and individual dispositions with the referenced evidence.

## Delivery and decision rules

Each engineering change goes through its normal entry points, targeted regressions, the original PR checks and independent merged-main checks. Publish the ledger and live tracker with the verified revision. D12-T03 requires assistive-technology evidence for its representative journeys. D09-T03 requires the named exercise and owner decision. Partner value and acceptance advance only on matching partner evidence. The task distribution changes when a delivery task satisfies its existing criteria.

Retain a summary of the observer's findings suitable for the roadmap. Keep raw input files, identities, protected outcomes and review records in approved custody. After the first exercise, make the D10/D13 decision together with the evidence owner. Both the formal pilot and later production-use decisions retain their current controls.

## Engineering qualification on 19 November 2026

Two keyboard journeys used Chromium 147.0.7727.0 and GNOME Orca 43.1 on Linux with AT-SPI, Speech Dispatcher and eSpeak. The fixture ran the Angular build against Django, a Redis broker and a worker. Disposable developer and reviewer accounts had separate project roles. OS keyboard events activated controls and typed the finding. Browser instrumentation selected the disposable session and observed the DOM. Orca's speech output supplied the announcement evidence.

| Journey | What the operator observed |
| --- | --- |
| Developer | Opened training from its dataset, found the exact successful job and heard its state, then closed the panel and returned to the originating dataset control. In a 50-entry history the operator opened a blocked job and heard both its state and the instruction to inspect the operational handoff with the project owner. |
| Reviewer | Opened the dataset's review panel, selected a specific protected assessment, downloaded its reproduction manifest, and heard the instruction to retain the digest separately. The operator heard “Technical review: revoked”, expanded the assessment identity, entered a synthetic finding, and returned to the original dataset control. |

The initial exercise found two barriers. Opening and closing a panel could leave focus on its old trigger or the document body. Selecting a blocked job could leave its recovery instructions unannounced. The repaired build focused the named panel or selected receipt for an explicit opening and restored the dataset trigger on close. The full PR browser suite also exposed a duplicate status region during a delayed refresh. A single live region now covers loading and receipt state. The corrected build passed all eleven observed stages and all thirteen local browser scenarios, including the original delayed-refresh and keyboard-export test. These observations cover the exercised browser, assistive technology and synthetic workflows. Independent reviewer comprehension, other assistive technology combinations and partner effort remain unmeasured.

The SHA-256 of the qualification source inventory was `cd7e7a44be0701ada971a6734b9b27a5a102326b5c79499e9616c2106297a781`. The final source-drift check returned an empty list. The eleven-stage speech and keyboard receipt was `eda0c2ebb6e6252418611e13a3d5c21d9f4bbbc8a43ed5f193a14442b080e6f5`. To repeat the exercise, use the project-workspace, training-launch and native-assessment fixtures, activate the stages above by keyboard, and inspect the screen reader's actual output for the receipt state, recovery instruction, decision status and restored control.

### Independent main qualification

PR #312 passed all seven PR checks. On its merged revision, the PostgreSQL suite reached its 900-second limit twice. The attempts completed 5,618 and 5,221 of 7,893 collected cases. Both partial results are retained. [Original main CI](https://github.com/caglarsubas/auto_ml/actions/runs/44484255902)

The corrective fixture places the two test workers on the existing private Docker bridge. Their PostgreSQL and Redis connections use each service’s internal listener. A preflight checks the scratch database identity, TLS hostname verification and rejection of an incorrect password from the test container. The original published-port, backup and restore checks still run. The correction carries the same tests, workers, coverage requirements and 900-second limit and adds one transport regression. It earns no additional roadmap task credit.
