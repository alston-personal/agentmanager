# Oracle host stall / Employee Worker historical-scan RCA

Date: 2026-10-12 to 2026-10-13  
Severity: P1 (Oracle control-plane availability)

## Impact

Oracle remained network-reachable at the TCP layer while user-space control paths stalled:
SSH banner exchange timed out, public AgentOS HTTP endpoints connected but returned no bytes,
and runner/control-plane work stopped making progress.

This host is a shared failure domain for ONE/Core, runners, GUI/browser work and other AgentOS
services, so one runaway workload could degrade many apparently unrelated capabilities.

## Evidence

Live forensics before remediation:

- root filesystem: 90–91% used
- Google Drive 5 TB rclone mount: present and healthy at observation time
- memory: about 12 GiB available; no contemporaneous OOM evidence
- I/O PSI avg300: some ~76%, full ~46%
- Employee Worker daemon: one Python thread at ~75.9% CPU, ~30 MiB RSS
- accumulated daemon CPU time: about 70 hours since 2026-10-08
- Employee wake files: 25,061
- Employee dispatch records: 25,054
- terminal checkpointed dispatches: 25,016
- unmatched wakes: 7
- Supervisor delivery / intent evidence: approximately 25k files each
- agent-data Git had a ~19 GiB packed-object footprint including giant unreachable objects

The current Google Drive mount was not the primary trigger of this incident.

## Root cause

The Employee Worker treated durable historical evidence as a hot query store.

First, each poll enumerated the entire wake tree and opened historical wake / dispatch JSON.
When work was observed the daemon did not apply polling backpressure.

After terminal-dispatch indexing and mandatory backpressure removed the JSON reread cost,
live attribution still showed ~40–50% CPU with no child runner. Seven unresolved product wakes
were repeatedly invoking Product Employee preclaim verification. Each verification scanned the
entire historical Supervisor deliveries directory and matching intent evidence. At ~25k evidence
files this produced repeated O(history × unresolved-wakes) filesystem and JSON work every poll.

The design therefore violated the scalability invariant that accumulated validated history must
not increase steady-state hot-path cost.

Contributors / amplifiers:

- no kernel CPU / I/O / memory boundary on the original worker
- stale immutable runtime generation remained active until governed convergence
- root storage pressure and giant Git packs reduced host margin
- Oracle currently carries multiple control-plane and execution workloads in one failure domain

## Remediation

PR #1789:
- cache terminal dispatch keys so terminal wakes are skipped before JSON reads
- mandatory poll backpressure after every cycle
- systemd cgroup boundaries: CPUQuota=50%, CPUWeight=20, IOWeight=20, MemoryMax=1G

PR #1892:
- cache only non-terminal wake paths and invalidate by employee-directory generation

PR #1908:
- build an exact, security-preserving Product Employee preclaim evidence index
- cache by Supervisor delivery / intent directory generation
- steady-state preclaim lookup becomes O(1) instead of rescanning all historical reconcile JSON

Storage remediation:
- giant unreachable agent-data Git pack reclaimed
- post-reclaim Git connectivity verified
- root filesystem returned to ~70–71%

## Live acceptance

Before remediation:
- Employee Worker CPU: ~75.9%
- I/O PSI avg300: some ~76%, full ~46%
- root filesystem: ~90–91%

After #1789 but before the preclaim evidence index:
- Employee Worker CPU: ~40–50%
- worker was frequently CPU-throttled at the 50% cgroup ceiling
- I/O PSI avg300 improved to roughly some ~25–28%, full ~14–16%

After #1908 exact immutable deployment:
- Employee Worker CPU over 10 s: 0.09%
- throttled periods: 0
- throttled usec: 0
- only the long-lived daemon was present in its cgroup
- 25,061 wake files and ~25k Supervisor evidence files remained intact
- Google Drive health: READY
- root filesystem: ~71%
- agent-data packed objects: ~1.11 GiB
- giant historical pack: absent
- post-reclaim health acceptance: PASS

This proves the performance recovery came from removing historical rescans, not from deleting
the durable wake/evidence history or disabling the worker.

## Preventive invariant

Durable history must be appendable and auditable without being replayed or rescanned on every
steady-state poll. Hot paths must use bounded indexes / queues and must have host-level resource
ceilings. A daemon-only Employee Worker should remain below the dedicated idle CPU SLO; the
health acceptance fails closed if it regresses above that ceiling.
