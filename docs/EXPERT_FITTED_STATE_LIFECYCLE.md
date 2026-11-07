# Expert fitted-state lifecycle

D08-T02 extends the dedicated operator-mediated Linux worker with fit, apply,
evaluate, score and replay stages. Every stage runs the approved module through
the pinned gVisor environment. The operator stages the authorized input
partition, and a reviewer approves its code, input, artifact, row order,
environment and limits.

## Fit and preserve state

A `fit` request uses the original request fields and a training feature
partition. The sandbox reads the stage from `/work/context.json` and its rows
from `/work/input.json`. It returns one JSON object with `table` and
`state_base64`. The table follows the worker's existing numeric output
contract. State is a bounded byte stream encoded with canonical Base64.

The controller validates the transport, table, row identity and output budget.
It records the state bytes without loading their serialized contents. Successful
fit publication creates a `fitted.json` artifact that binds the exact code,
environment, input partition, input digest, state digest and fit-output digest.
Cleanup must succeed before the worker publishes candidates or state.

The original successful fit can export the exact artifact bytes.

```sh
sudo python3 -I private_expert_worker.py --state /var/lib/declarai-expert --environment /opt/declarai-expert export /var/lib/declarai-intake/FIT_REQUEST --output /secure/expert-fitted.json
```

Retain the reported artifact digest independently when transferring the file.
The worker verifies stored candidate and artifact digests when returning a
completed job or exporting its state.

## Apply, evaluate and score

Stage the exported bytes as `fitted.json` in a fresh request directory.
Add `artifact_sha256` to `request.json` with the independently recorded
digest. `apply` and `evaluate` require an artifact. `score` supports the
existing stateless mode and the fitted mode. Each request still needs a fresh
preview and approval.

The worker verifies the project, code, environment and limits against the fit
artifact before claiming the job. The sandbox receives only the approved
input, context, code and read-only `/work/state.bin`. Expert Python can load
that file inside gVisor. Apply results retain row identity. Evaluation and
scoring return a single numeric `score` column. Each receipt cites the
applied artifact and original fit request.

Custom evaluation values remain expert candidate output. Trusted model
assessment and organizational review use their existing evidence and gates.
The application browser and MCP code-dispatch routes retain their current
unavailable-service response while their governed integration is developed.

## Clean replay

A `replay` request requires the exact fit partition, input bytes, code and
environment. Approve it in a newly pinned worker state directory to reproduce
an exported artifact independently of the original job history. The worker
runs the recipe's fit stage in a fresh sandbox with no state file mounted.
It compares both the reconstructed state digest and numeric fit-output digest
with the approved artifact.

Recipes with nondeterministic serialized state fail exact replay explicitly.
The current contract requires identical bytes. A changed partition, missing
artifact, changed state, changed code, different project or different
environment stops before execution.

## Deployment scope

This profile uses the dedicated worker's operator intake and review channel.
Labels record operator assertions. Updating the worker source changes the
environment fingerprint and requires a newly pinned state directory and
fresh approvals. Existing artifacts retain their recorded source and
environment. Their use requires the matching qualified environment.

D08-T03 qualifies the broader hostile-code, cancellation and isolation matrix.
Native application training, model promotion and production-use authority
continue to use their own declarations, jobs and review records.
