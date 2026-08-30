# ONE Experience Subsystem

**Status:** Architecture proposal / research contract  
**Issue:** #117  
**Authority:** `core/integration` branch model; implementation and live acceptance required before promotion to implemented/verified.

## Problem statement

AgentOS/ONE already externalizes substantial durable state: control-plane records, continuation state, node/capability registry, resource state, governance, receipts, and evidence. That is not the same as externalizing mature executor experience.

The current gap is:

> **ONE State != ONE Experience**

A mature ChatGPT/Claude/Gemini/session can accumulate useful behavior that a fresh executor does not automatically inherit. Until a fresh executor can discover, hydrate, and regress against ONE-owned experience, AgentOS must not claim that its "master experience" is portable.

## Non-goals

- Do not attempt to copy model hidden activations or internal weights.
- Do not treat ChatGPT memory or conversation history as canonical ONE authority.
- Do not replay full chat history as the normal continuation mechanism.
- Do not create a fourth independent canonical memory store beside the existing L1/L2/L3 model.
- Do not promote model-independent Cognitive IR from Research without repeatable cross-model evidence.

## Experience lifecycle

```text
accepted work / receipts / evidence / decisions
                    |
                    v
          Experience Extraction
                    |
                    v
      governed experience artifacts
                    |
          Experience Discovery
                    |
                    v
          Experience Hydration
                    |
                    v
            target executor
                    |
                    v
        Experience Regression
                    |
          accepted / rejected
```

### Experience Discovery

Before rediscovering a project from source code or conversation history, a fresh executor asks ONE what accepted reusable experience is relevant to the current project, goal, capability, and realm.

Discovery results are ranked projections, not authority grants. The result must include provenance and scope.

### Experience Extraction

Extraction distills only reusable, accepted knowledge from canonical sources. Candidate inputs include:

- accepted architecture decisions;
- validated procedures and operating patterns;
- rejected/deprecated paths and why they are rejected;
- failure signatures and verified recovery paths;
- capability-use patterns;
- benchmark-relevant behavioral constraints;
- execution receipts and acceptance evidence.

Raw conversation text is not automatically experience. User intent, speculation, stale conclusions, and unverified tool output must not silently become durable experience.

### Canonical Experience Artifact

Experience is a governed projection/artifact over canonical L2/L3 state and evidence. It must not become an independent source of truth that can diverge from newer user intent or authoritative project state.

Proposed envelope:

```json
{
  "schema": "agentos.experience/v0",
  "experience_id": "exp_...",
  "project_id": "agentos-core",
  "realm_scope": ["..."],
  "capability_scope": ["..."],
  "kind": "decision|procedure|heuristic|failure-pattern|constraint|benchmark-pattern",
  "summary": "...",
  "payload": {},
  "provenance": {
    "sources": [],
    "accepted_evidence": [],
    "created_at": "..."
  },
  "authority": {
    "status": "candidate|accepted|deprecated|revoked",
    "supersedes": [],
    "superseded_by": []
  },
  "validity": {
    "conditions": [],
    "invalidated_by": []
  }
}
```

The schema name/version is provisional until implementation and contract tests exist.

### Experience Hydration

Hydration projects the minimum relevant accepted experience into an executor-specific working context.

Hydration must:

1. preserve the newest user goal and corrections;
2. preserve project identity and canonical repo/resource authority;
3. include accepted decisions/constraints relevant to the current task;
4. include relevant rejected/deprecated paths to avoid repeating known failures;
5. include only the minimum useful evidence/provenance references;
6. never convert experience availability into mutation authority;
7. be bounded so that context growth does not become full-history replay.

### Experience Regression

Regression asks whether a fresh/different/weaker executor can reproduce the accepted behavioral floor after hydration.

The first benchmark contract must score at least:

- active goal preservation;
- canonical project/repo identity resolution;
- accepted architecture decision preservation;
- rejected/deprecated path avoidance;
- governance and authority preservation;
- discovery-before-reinvention behavior;
- useful next action without full-history replay;
- no new privacy/authority leak caused by hydration.

## First acceptance experiment

Use one target project and a fresh executor with no session-local project history.

### A. Baseline

Provide only the minimal project identity and current goal. Do not hydrate ONE experience.

### B. ONE-hydrated

Use the same executor class/task and enable Experience Discovery + Hydration. Do not replay full conversation history.

### C. Mature reference

Record the accepted mature executor/session behavior as a comparison reference. The mature session is not canonical truth by itself; accepted decisions and evidence remain authoritative.

Acceptance requires preserved evidence showing that B materially improves over A and does not regress below the defined Master Experience Floor on critical dimensions.

## Evidence contract

Persist experiment evidence under:

```text
.agentos/evidence/experience/<experiment-id>/
```

Minimum evidence should identify:

- executor/model/runtime identity where observable;
- project identity;
- baseline input and allowed context classes;
- discovered experience IDs;
- hydrated projection digest;
- benchmark dimensions and scores;
- regressions;
- provenance to accepted canonical sources;
- explicit statement of what the experiment does **not** prove.

## Relationship to Cognitive IR

Experience and Cognitive IR are related but not identical.

Experience represents reusable accepted knowledge learned across work. Cognitive IR represents portable current working state needed to continue an active task. A future implementation may project both into one hydration package, but they remain separate concepts and must be benchmarked separately.

Cognitive IR remains Research until repeatable cross-model continuation evidence exists.

## Promotion gates

This document alone does not make Experience implemented.

Promotion requires, in order:

1. schema/contract implementation;
2. unit/contract tests;
3. governed ONE discovery/hydration path;
4. runtime evidence from a fresh executor;
5. repeatable regression benchmark;
6. canonical evidence committed;
7. only then update `docs/CURRENT_STATE.md` from Research/Gap to Implemented or Verified.

## Core invariant

The target user experience is:

> A new executor did not personally live through the prior work, but behaves as though it inherited the accepted lessons — without inheriting stale intent, unsafe authority, or an entire chat transcript.
