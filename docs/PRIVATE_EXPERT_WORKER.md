# Dedicated gVisor expert worker

D08-T01 provides a one-job service for a dedicated Linux worker. An installation
operator stages only the feature rows authorized for one partition. A reviewer
approves the exact code, input bytes, ordered row identity, environment, project,
partition, mode and resource limits before dispatch. Browser and MCP expert-code
requests still fail closed. Application workflows that carry expert fitted state
through training, replay and scoring belong to D08-T02.

## Provision the worker

Use a dedicated Linux machine with cgroup v2 CPU, memory and PID controllers.
Provision a root-owned, sealed environment with the verified gVisor release,
including its sidecars, under `runtime/`. Place a fixed, secret-free Python
root filesystem under `rootfs/`, with an empty `rootfs/work/` directory.
Use root ownership throughout and remove setuid, setgid and group or world
write permissions. Normalize hard-linked files to independent inodes. Keep the root-only worker state separate from the environment,
application service credentials and dataset storage.

The qualification recipe pins gVisor release 20261102.0 by archive hash and the
Python rootfs image by digest. Production installation can stage those packages
offline. The worker pins the installed tree and its own source before any
approval. Replacing the environment requires a fresh state root and fresh
approvals. [gVisor installation](https://gvisor.dev/docs/user_guide/install/)

## Review and execute

Use a root-owned mode-0700 request directory containing three regular files.
`request.json` identifies the request, project and partition by canonical
UUIDs, gives the proposer label and selects `transform` or `score` as the mode.
`input.json` contains `columns`, `row_ids` and finite numeric `rows`. The
operator supplies the approved projection from the source system and keeps
outcomes and unrelated partitions outside the request. `code.py` reads
`/work/input.json` and writes one JSON table to stdout. Scorers return the
single column `score`. Results retain the input row IDs in the original order.

Use the local operator's trusted review channel. The recorded reviewer and
proposer labels are operator assertions. Review the actual staged code and
partition alongside the displayed digests. The approval expires after
15 minutes. A consumed request returns its existing receipt.

```sh
sudo python3 -I private_expert_worker.py --state /var/lib/declarai-expert --environment /opt/declarai-expert pin
sudo python3 -I private_expert_worker.py --state /var/lib/declarai-expert --environment /opt/declarai-expert preview /var/lib/declarai-intake/REQUEST
sudo python3 -I private_expert_worker.py --state /var/lib/declarai-expert --environment /opt/declarai-expert approve /var/lib/declarai-intake/REQUEST --expected REVIEWED_SHA256 --reviewer REVIEWER
sudo python3 -I private_expert_worker.py --state /var/lib/declarai-expert --environment /opt/declarai-expert execute /var/lib/declarai-intake/REQUEST
```

The worker launches the pinned `runsc` executable directly with Systrap and
network disabled. Each file-serving gofer has its own empty network namespace. Each sandbox has a read-only rootfs and input mount, an
unprivileged identity, an 8 MiB scratch filesystem and CPU, PID and memory
limits. The host cgroup disables swap for each sandbox. The supervisor enforces a 15-second deadline and a 256 KiB output
limit. The API and worker controller never import expert modules. The
controller accepts typed JSON and retains the validated output as an unadopted
candidate in the root-owned job state directory.

## Cancel and reconcile

From the trusted local operator channel, cancel an active job by its UUID.

```sh
sudo python3 -I private_expert_worker.py --state /var/lib/declarai-expert --environment /opt/declarai-expert cancel JOB_UUID --operator OPERATOR
```

The cancellation request records the operator label, request time and digest
of the claimed approval. It is accepted for the exact active job before
publication. Check the terminal receipt for `expert_cancelled`. The worker
stops runsc, verifies the cgroup has been removed and discards candidate
output. Cancellation of an already finished job is refused.

A missing or altered runtime stops execution. Controller loss and unverified
cleanup leave the active marker in place and fence subsequent execution.
Quarantine the worker and reconcile the exact job's bundle, runsc state and
host cgroup under operator control before removing the marker. Retain the
claim, review, cancellation and any terminal receipts. The consumed claim
continues to prevent re-execution.

The gVisor qualification recipe exercises unauthorized partition and control
file reads, host loopback and Unix socket access, privilege escalation, scratch
and memory pressure, CPU throttling, malformed output, and a pickle side
effect confined to the sandbox. It checks cancellation with live descendants,
controller loss and operator cleanup. A separately injected runsc deletion
failure verifies that the worker withholds publication and quarantines the job.

## Fitted artifact stages

The worker also supports the approved fitted-state lifecycle. Fit, apply,
evaluate, score and clean replay preserve the gVisor boundary and exact
artifact authority. See [Expert fitted-state lifecycle](EXPERT_FITTED_STATE_LIFECYCLE.md).
