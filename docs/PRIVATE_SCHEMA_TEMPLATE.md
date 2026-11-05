# Fresh schema evidence with reusable declaration rendering

P169 addresses repeated historical-model rendering in the private runtime
preflight. Publication-main run [42021620253](https://github.com/caglarsubas/auto_ml/actions/runs/42021620253)
failed the unchanged 900-second native process cap after both workers finished
all 7,738 cases. The workers finished 1.3 seconds apart; finalization did not
complete. That run remains failed, with its original artifact hash retained in
the [source and qualification contract](evidence/p169-schema-template-contract.json).

Each call still loads a fresh migration graph, rejects replacements, derives
its complete final state and compares an in-process byte key. Only rendering
an identical standard Django migration state is reused. One retained entry and
a 1 MiB key cap bound reuse. Custom/pre-rendered states, custom field modules
or model bases, unmigrated runtime models, oversized keys and serialization
failure use fresh rendering. Swappable setting values participate in the key.
Serialized bytes are never deserialized or obtained from model artifacts.

The desired contract is rebuilt on every call, including all field and
constraint refusals and the current required runtime names. PostgreSQL catalog,
migration history, role, TLS, authority, broker/cache and resource checks remain
fresh. A warm rendering cannot turn a changed physical catalog into success.
This is independent of expert-code execution; it supplies no expert sandbox.

Five additive regressions cover reuse, return-value independence, changed
required names/field declarations, pre-rendered/custom state mutations,
serialization fallback and fresh catalog refusal. All 290 prior qualification
source files in the immediate-main preservation inventory remain byte-identical;
older inventories and the original P168 conjunctive matrix remain mandatory.
The local pinned Linux/TLS/PostgreSQL probe passed 583 cases without failures
or skips. It is a focused check, not full CI or customer acceptance. Alternated
100-call component measurements under branch coverage reduced median derivation
from 1.624 to 0.572 seconds, with equal contracts. This is not a full-suite speed
or customer-capacity claim.

Full qualification contains 7,743 native cases, including the five additions,
six unchanged skips, the unchanged coverage threshold and 809 original RI
cases. The original fits, folds, assertions, installed clean/recovery/upgrade
drills, two loadfile workers, zero restarts, 900-second process and 60-minute
job limits remain required. Each PR and automatic main run must qualify
independently; a component benchmark does not waive a failed run.

D07-T06's previously accepted synthetic profile stays recorded at P168. The
fixed 66-task distribution remains 8 done / 51 open / 7 blocked
(12.1% / 77.3% / 10.6%), versus the iteration baseline 7 / 52 / 7:
done +1.515 percentage points. This maintenance correction adds no completion
credit. Full D07, customer operational acceptance and release remain open.
