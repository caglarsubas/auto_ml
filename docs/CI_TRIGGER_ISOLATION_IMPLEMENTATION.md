# CI trigger isolation — P114

P113 push-main run [39363097400](https://github.com/caglarsubas/auto_ml/actions/runs/39363097400)
was cancelled after nightly run [39363175020](https://github.com/caglarsubas/auto_ml/actions/runs/39363175020)
started on the same commit. Both selected the same workflow/ref concurrency key
with cancellation enabled. The nightly run ultimately qualified that commit;
the cancelled push did not supply a passing result.

Include the trigger in the CI concurrency key. Push, scheduled and manual runs
on one ref can now complete independently. Keep cancellation enabled within
each workflow/ref/trigger so newer commits still supersede stale work. Distinct
pull requests and workflows retain separate groups.

The existing backend-lint job also runs a standard-library policy guard. Its
21 representative comparisons cover trigger isolation, within-trigger
supersession, workflow/ref separation and case-insensitive group identity.
The guard supports this workflow's simple scalar/context substitutions only;
unsupported expressions or fields fail for explicit review. It is not a general
YAML or GitHub expression interpreter.

Local qualification reproduces three collisions on frozen main and passes all
21 checks on the fixed workflow. Eight negative controls reject omitted trigger,
workflow or ref identity, per-commit/per-run keys that defeat supersession,
disabled cancellation, unsupported expressions and duplicate fields. Ruff passes.
Actionlint 1.7.12 has no new findings; its two existing SC2034 warnings are
retained and match frozen main after line-number normalization.

The six CI jobs, native/scientific/browser/physical fixtures, assertions, retry,
coverage, resource, skip and timeout budgets remain unchanged. No product runtime
code or customer installation is modified. This changes cancellation grouping,
not GitHub account concurrency limits or scheduling guarantees. Local comparisons
are policy evidence; they do not claim a live post-fix push/nightly overlap.
Exact-head all-six checks, complete native/private reports, guarded merge and
independent push-main qualification remain required. D07/release/customer gates
remain open. See the [source receipt](evidence/p114-qualification-2026-10-20.json).

Reference: [GitHub concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
