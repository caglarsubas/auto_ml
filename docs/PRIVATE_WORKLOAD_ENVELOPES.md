# D07-T07 — Observed private-installation workload envelopes

P166 is in progress. The fixed 66-task inventory remains 5 done/54 open/7 blocked
until implementation, PR qualification and independent main evidence pass.

The first measurement protocol covers the currently qualified numeric native
classification/regression development/search profile: 30, 300 and 1,000 rows;
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
