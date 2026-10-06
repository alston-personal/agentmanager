# AgentOS External Benchmark Growth Proof Plan

## Goal

Use independent public agent benchmarks to measure two separate effects:

1. **AgentOS system uplift**: raw/base model vs AgentOS Cold.
2. **AgentOS growth uplift**: AgentOS Cold vs AgentOS Experienced.

A public benchmark score alone is not Growth Proof. Growth Proof requires that the only intentional difference between Cold and Experienced is validated accumulated AgentOS experience.

## Experimental arms

For every supported benchmark, run at least:

- **A — Raw / reference agent**: benchmark's standard or minimally augmented model harness.
- **B — AgentOS Cold**: same model/provider/version and comparable tool budget, but no accumulated validated cognition.
- **C — AgentOS Experienced**: same as B, with validated accumulated AgentOS experience enabled.

Preferred extension:

- **D — Cross-model Experienced**: transfer the same AgentOS cognition to a second model/provider to test G4.

## Primary measurements

Report both absolute benchmark score and deltas:

- Raw score
- AgentOS Cold score
- AgentOS Experienced score
- System uplift = Cold - Raw
- Growth uplift = Experienced - Cold
- Cross-model transfer uplift where available

Also capture:
- task success rate
- human intervention count
- retries/actions
- elapsed time
- cost per successful task
- regressions
- invalid/hacked task count

## Benchmark priority

### P0 — OSWorld-V2.1

Reason:
- directly exercises computer-use / GUI agents;
- long-horizon desktop tasks align with AgentOS GUI Worker and heterogeneous executor thesis;
- official release pins code, tasks, assets, websites, and provider images, making controlled comparison possible.

Pin all official release components to the same supported release. Never compare runs that mix benchmark releases.

Target proof:
- Raw vs Cold: AgentOS GUI/runtime uplift.
- Cold vs Experienced: G3.
- Another compatible executor/model with same learned deltas: G4.

### P0 — GAIA

Reason:
- general assistant benchmark with multi-step reasoning, search/tool use, and autonomous task completion;
- useful as an external general-agent validity check rather than only a desktop benchmark.

Target proof:
- Raw vs Cold system uplift.
- Cold vs Experienced G3 only when benchmark contamination and answer leakage are ruled out.

### P1 — SWE-bench Verified / compatible coding benchmark

Reason:
- tests coding agent execution and repair;
- fits AgentOS coding executor / provider routing once that runtime is stable.

Target proof:
- compare reference coding harness against AgentOS Cold;
- then test whether validated debugging/recovery experience improves held-out tasks.

## Anti-gaming / validity rules

A run is not comparable unless these are recorded or fixed:

- benchmark release / task manifest hash;
- model provider, model name, and version/date where available;
- system prompt / agent policy version;
- tool set and permissions;
- max steps / token / time budget;
- executor and machine image;
- website/task asset version;
- network/search policy;
- AgentOS cognitive store snapshot/hash;
- whether benchmark tasks or answers were ever present in the learning corpus.

Forbidden:
- learning from held-out benchmark answers and then scoring those same tasks as growth;
- benchmark-specific hardcoded solutions;
- changing model strength between Cold and Experienced without accounting for it;
- silently increasing tool or time budgets;
- suppressing failed/regressed tasks;
- mixing benchmark releases.

## Growth Proof mapping

- **External score > raw model**: system/harness evidence only.
- **Experienced > Cold under controlled conditions**: candidate G3.
- **Experienced delta transfers across model/executor**: candidate G4.
- **Age 0 < Age N < Age M across frozen benchmark releases without leakage**: candidate G5.

## Receipt

Every benchmark comparison should emit or reference `agentos.growth-proof-receipt/v1` with:

- benchmark name and immutable release id;
- benchmark manifest/task hashes;
- raw/cold/experienced arm configs;
- AgentOS experience snapshot hash;
- metrics per arm;
- system uplift and growth uplift;
- regressions;
- contamination declaration;
- evidence paths;
- verdict.

## Immediate execution order

1. Integrate OSWorld-V2.1 adapter/runner.
2. Establish a small smoke subset to validate environment parity.
3. Run Raw and AgentOS Cold first.
4. Freeze the benchmark environment.
5. Accumulate validated AgentOS experience only from non-held-out work.
6. Run AgentOS Experienced on the same frozen held-out suite.
7. If G3 uplift is real, repeat on a second executor/model for G4.
8. Add GAIA as a second independent external validity surface.

Do not optimize specifically for leaderboard position until the Cold-vs-Experienced causal comparison is already trustworthy.
