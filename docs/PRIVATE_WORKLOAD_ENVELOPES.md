# D07-T07 — Observed private-installation workload envelopes

P166 is test-qualified for the disclosed synthetic native profile. The fixed
66-task inventory is 6 done/53 open/7 blocked (9.1%/80.3%/10.6%).

The first measurement protocol covers the currently qualified numeric native
binary classification and regression development/search profile: 30, 300 and 1,000 rows;
2, 16 and 32 predictors; random, grouped and temporal validation; two declared
candidates, 16 boosting rounds and one native thread per fit. It measures actual
installed HTTPS upload, preview, queued training/search, immutable candidate
export, queued scoring and byte-verified offline scoring parity. Paired submissions
exercise the configured two-job admission/worker profile without assuming they
always overlap. All original installation/recovery assertions and limits remain.

Two separately initialized roots repeat the same seeded synthetic cases. PR and
independent main repeat the protocol again. Reports bind the exact source commit,
image IDs, limits, input hashes, model/result evidence, wall times, observed
concurrency, sampled container CPU/memory/PIDs and recovery costs. Existing
installed recovery drills provide measured backup, restore/adoption, natural-lease
recovery and duplicate-drain intervals without changing their faults or clocks.

Resource observations use bounded Docker CLI stats for exactly owned containers.
Linux CLI memory excludes cache according to Docker's documented convention;
CPU percentages are retained as CLI observations. Samples are not exact peaks,
and sampling overhead is included in workflow wall time. See
[Docker stats](https://docs.docker.com/reference/cli/docker/container/stats/).

These are repeatable observations on the synthetic Ubuntu 24.04 ARM64 four-CPU/
16 GiB reference profile. They establish the tested envelope and known admission
boundaries, not customer throughput, latency guarantees or capacity. Legacy
training/SFS/HPO migration and its broader envelopes remain D07-T05 work;
customer-observed capacity and operational acceptance remain separate gates.

## Recorded observations

[PR #268](https://github.com/caglarsubas/auto_ml/pull/268) and its independent
[automatic main run](https://github.com/caglarsubas/auto_ml/actions/runs/41782352443)
passed all six checks. [Exact receipts and artifact digests](evidence/p166-qualification-2026-11-04.json)
retain every observation. Four fresh roots completed 24 profiled training/search/
export/scoring cases, in addition to all original installation workflows.

Ranges below summarize these four roots; they are observations, not performance
objectives or guarantees. Workflow time includes paired queueing, sequential
scoring/export checks and observer overhead.

| Task | Rows / predictors | Validation | Workflow seconds | Training execution seconds | Training queue seconds |
|---|---|---|---|---|---|
| classification | 30 / 2 | random (2 folds) | 11.890–12.209 | 0.114–0.128 | 4.471–4.644 |
| classification | 300 / 16 | group (3 folds) | 9.979–10.235 | 0.221–0.250 | 2.410–2.834 |
| classification | 1000 / 32 | temporal (2 folds; oot) | 9.974–10.197 | 0.291–0.320 | 2.245–2.569 |
| regression | 30 / 2 | random (2 folds) | 16.573–17.138 | 0.125–0.148 | 4.406–4.576 |
| regression | 300 / 16 | group (3 folds) | 14.749–15.138 | 0.237–0.267 | 2.305–2.743 |
| regression | 1000 / 32 | temporal (2 folds; oot) | 14.762–14.862 | 0.294–0.322 | 1.919–2.266 |

| Service | CPU quota | Memory limit MiB | Sampled CPU % | Sampled memory MiB | Sampled PIDs |
|---|---|---|---|---|---|
| api | 2 | 2048 | 0.010–18.890 | 232.100–234.900 | 4–4 |
| worker | 2 | 2048 | 0.030–27.070 | 362.000–396.300 | 4–5 |
| dispatcher | 2 | 2048 | 0.020–1.020 | 216.000–216.600 | 3–3 |
| ingress | 1 | 256 | 0.000–2.380 | 4.020–5.039 | 2–2 |
| postgres | 2 | 2048 | 0.000–21.110 | 45.510–49.070 | 8–9 |
| job-broker | 1 | 512 | 0.290–0.450 | 4.402–5.422 | 6–6 |
| cache | 1 | 128 | 0.260–0.340 | 3.625–4.133 | 6–6 |

Observed simultaneous training jobs: two in every paired case; configured ceiling: two. All
1,001-row preview requests were refused before queue submission. Inputs and
predictions matched exactly between the two roots within each CI run. This
protocol exercises admission; it does not measure saturation throughput.

Recovery costs below come from the unchanged fault-injection drill: two original
40-row/two-predictor classification/regression workflows, four completed jobs and
three pending/cancelled jobs. They include verification/fault overhead, natural
180-second lease expiry and 21 duplicate deliveries. No customer RPO/RTO is claimed.

| Recovery measurement | Observed seconds (PR–main range) |
|---|---|
| Encrypted coordinated backup | 3.037–3.329 |
| Restore with faults to adoption | 31.730–34.240 |
| Adoption to pending terminal outcomes | 123.931–127.988 |
| Duplicate drain and final checks | 12.247–12.506 |
| Entire restore cycle | 172.893–174.180 |

Encrypted archive size: 424,292–427,608 bytes.

D07-T07 increases done by 1.515 percentage points, from 5/66 (7.6%) to
6/66 (9.1%). Broader legacy workloads, full D07, customer capacity, release and
customer acceptance remain separate.

Resource samples cover only the seven resident installation services listed above.
Transient offline-scoring containers, the host kernel, image builds and image
transfer are outside those samples. Offline parity checks retain their fixed
one-CPU/1-GiB isolated-container ceilings. Per-service CPU quotas are ceilings,
not reserved host capacity; no aggregate machine peak is inferred.
