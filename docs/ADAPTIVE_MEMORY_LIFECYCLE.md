# Adaptive Memory Lifecycle

Status: experimental Cognitive Kernel capability on `feature/state-kernel-v2`.

## Principle

AgentOS models forgetting as **attention decay, not destructive deletion**.

Knowledge content, evidence, contradiction records, lineage and provenance remain immutable. What changes over time is how likely a memory is to consume retrieval and reasoning attention.

```text
HOT -> WARM -> COOL -> COLD -> ARCHIVE
 ^                              |
 |------ reinforcement ---------|
```

A tier is not a permanent identity. New evidence, explicit recall, renewed usage, or a strong current-context relation may reactivate old knowledge.

## Why

An ever-growing cognitive graph without decay eventually creates retrieval noise and unnecessary context/token/search cost. Conversely, physical deletion destroys auditability and prevents old but newly relevant knowledge from resurfacing.

The lifecycle therefore optimizes scarce cognitive attention while preserving historical truth.

## Reference semantics

- **Hot**: highly active; normal retrieval receives full weight.
- **Warm**: important but not dominant.
- **Cool**: lower-priority background knowledge.
- **Cold**: only strong relevance should usually surface it.
- **Archive**: excluded from ordinary retrieval by default; remains explicitly recallable and fully traceable.

Lifecycle state is deliberately stored separately from `KnowledgeCandidate`. Knowledge identity/provenance does not change merely because attention changes.

## Decay

Reference decay uses a configurable half-life over activation. Decay may be slowed or floored by:

- downstream dependency count;
- historical/audit value;
- explicit pinning;
- current use and relevance.

Superseded knowledge decays faster out of active cognition, but is not destroyed.

## Reinforcement and revival

Retrieval/use can increase activation. Strong relevance and explicit recall provide larger boosts. A Cold or Archive memory may therefore become Warm/Hot again.

This allows old experience to become cognitively important when the environment changes.

## Retrieval integration

The association engine can consume lifecycle state as a score multiplier. Archive is omitted from ordinary retrieval unless `include_archive=True`.

This preserves two distinct concerns:

```text
knowledge confidence = how strongly we believe/validate the claim
memory activation    = how likely it should consume attention right now
```

High confidence does not require perpetual Hot status. High activation does not grant truth authority.

## Governance invariants

1. Decay may lower attention, never erase provenance.
2. Archive is not deletion.
3. Supersession must remain auditable even when old versions become Cold/Archive.
4. Dependency-bearing knowledge must not silently decay below configured safety floors.
5. Retrieval activation must never be interpreted as validation/confidence.
6. Reactivation changes attention only; it does not self-promote Working/Project/Cross-project knowledge.
7. Physical deletion, if ever supported, requires a separate retention/governance policy and is outside this lifecycle.
8. Important historical or audit anchors may be pinned independently of ordinary semantic relevance.

## Cognitive compounding with pruning

The full learning loop becomes:

```text
Experience
 -> Association
 -> Synthesis
 -> Promotion
 -> Reinforcement
 -> Decay
 -> Attention pruning
 -> New evidence / recall
 -> Revival
 -> Re-synthesis
```

The goal is not "remember everything equally". It is to keep the most useful knowledge cognitively close while retaining the ability to recover older context when it becomes relevant again.
