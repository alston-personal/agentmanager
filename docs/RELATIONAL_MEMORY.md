# AgentOS Relational Memory and Global Reconciliation

Status: experimental Cognitive Kernel foundation on `feature/state-kernel-v2`.

## Why this exists

A file can exist and still be cognitively disconnected.

The triggering failure case was concrete: AgentOS had a historical chronicle in `my-agent-data`, while the derived dual-mode fiction lived in `zeus-writer`. Both were readable, but there was no explicit machine-readable relation connecting them. A user had to supply the repository name before the system could find the novel.

The lesson is:

> A fact without relations is only partially remembered.

AgentOS therefore treats relational memory as a first-class cognitive layer.

## Separation from canonical state

Relational Memory is **not ProjectState**.

It contains cognitive claims such as:

```text
project:zeus-writer
  contains -> work:ai-fantasy-chronicles

work:ai-fantasy-chronicles
  fictionalized_from -> artifact:agentos-grand-chronicle

project:agentmanager
  documented_by -> artifact:agentos-grand-chronicle
```

These edges help discovery and synthesis. They do not grant write authority, mutate Project HEAD, or become truth merely because a graph edge exists.

## Entity identity

`agentos.entity/v1` keeps a stable entity identity with:

```text
entity_id
kind
canonical_name
aliases
refs
metadata
```

Aliases solve the human naming problem. The same project may be referred to as:

```text
Zeus Writer
Zeus-writer
同源雙模小說
小說專案
alston-personal/zeus-writer
```

Resolution is retrieval/discovery only. It does not itself prove identity or create authority.

## Relation claims

`agentos.relation/v1` is immutable and content-addressed. A relation carries:

```text
subject_id
predicate
object_id
evidence
confidence
status
valid_from / valid_to
metadata
```

Relation status follows candidate governance semantics:

```text
candidate
validated
superseded
rejected
```

Superseded/rejected relations remain auditable and are hidden from ordinary graph traversal by default.

## Graph behavior

The reference `InMemoryRelationGraph` supports:

- alias/ref resolution;
- explicit endpoint validation;
- inbound/outbound/bidirectional neighbor lookup;
- bounded cycle-safe graph traversal;
- inactive relation audit;
- discovery from conversational names into linked projects/artifacts.

A production implementation may use a graph database, relational database, search index, or another maintained backend. AgentOS owns the semantics, not commodity storage infrastructure.

## Global Cognitive Reconciliation

`CognitiveReconciliationPlanner` performs read-only inspection of the graph and emits review work. It does not rewrite memory.

Current issue classes include:

- `orphan_entity` — an entity exists but has no explicit relation;
- `ungrounded_relation` — a relation claim has no provenance evidence;
- `cross_project_relation_review` — a cross-project relation is not validated;
- `stale_derivative` — a source artifact evolved after a derived artifact was last updated.

The stale-derivative rule is the direct foundation for cases such as:

```text
AgentOS Grand Chronicle updated through August
        ↓
AI 奇幻編年史 still reflects April-era architecture
        ↓
reconciliation emits stale_derivative
        ↓
re-synthesis / human review is scheduled
```

The derived work is never silently rewritten.

## Relationship to adaptive forgetting

Relational Memory and Adaptive Memory Lifecycle are complementary.

```text
Memory lifecycle
= how active should this node be right now?

Relational memory
= what does this node mean in relation to other nodes?
```

A Cold/Archive node may be revived because a new active node strongly links to it. Conversely, an obsolete relationship can be superseded while both endpoint entities remain preserved.

## Relationship to cognitive compounding

The complete loop becomes:

```text
Experience
 -> Knowledge
 -> Entity resolution
 -> Relation graph
 -> Near/far association
 -> Synthesis
 -> Promotion
 -> Compaction
 -> Adaptive decay/revival
 -> Global reconciliation
 -> Re-synthesis
 -> new Knowledge / Relation candidates
```

The graph therefore behaves less like a static catalog and more like a governed set of cognitive synapses: links can be discovered, strengthened through evidence, superseded, deprioritized, revisited, and used to form higher-order abstractions.

## Governance invariants

- A relation is a claim, not canonical truth.
- Alias resolution is heuristic discovery, not authorization.
- Cross-project edges require stronger evidence before validation.
- Every durable relation should retain provenance.
- Missing provenance degrades to review/candidate state.
- Reconciliation emits reconsideration work; it does not mutate source or derivative artifacts.
- Superseded relation history remains inspectable.
- Relational traversal is bounded to prevent uncontrolled context expansion.
- Relation discovery must not expose credentials or source secrets.

## Current acceptance case

The reference tests encode the failure that motivated this layer:

```text
query: 同源雙模小說
 -> resolves project:zeus-writer
 -> contains AI 奇幻編年史
 -> fictionalized_from AgentOS Grand Chronicle
 -> detects source newer than derived work
 -> emits stale_derivative
```

The user should not need to remember and provide the repository name for this relationship to exist cognitively.
