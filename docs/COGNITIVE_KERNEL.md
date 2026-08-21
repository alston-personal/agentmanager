# AgentOS Cognitive Kernel

Status: experimental design and executable foundation on `feature/state-kernel-v2`.

## Purpose

The Cognitive Kernel is not a replacement for an LLM, vector database, browser bridge, memory product, or workflow engine. It owns the semantics that let accumulated experience become progressively more useful without allowing inference to silently become truth or authority.

The target loop is:

```text
Distributed raw experience
  -> ExperienceEvent IR
  -> governed Experience Compiler
  -> structured knowledge candidates
  -> indexing
  -> near retrieval + far structural analogy
  -> bounded synthesis envelope
  -> external synthesizer / agent / human
  -> governed knowledge candidate
  -> evidence + contradiction review
  -> Working -> Project -> Cross-project promotion
  -> hierarchical compaction / meta-synthesis
  -> dependency-aware re-synthesis when new input arrives
  -> new candidate knowledge
```

This is **cognitive compounding**: prior synthesis becomes reusable material for later synthesis, while provenance and governance remain stronger as persistence and propagation increase.

## Non-negotiable boundary

> Capability must never scale faster than governance.

The Cognitive Kernel can make increasingly powerful associations. That never grants increasing authority automatically.

- Retrieval results are disposable context, not truth.
- Synthesized output is a candidate, not durable memory.
- Durable memory is not canonical ProjectState.
- Cross-project promotion requires stronger evidence and governance than project-local memory.
- Re-synthesis planning cannot trigger external actions.
- Project HEAD remains exclusively owned by the State Kernel.

## Experience ingestion

Vendor integrations do not feed raw proprietary session objects directly into Cognitive Kernel logic.

Each source adapter normalizes into `agentos.experience/v1`:

```text
project_id
source_kind
source_ref
actor_kind
event_kind
content
occurred_at
trust_class
conversation_ref
parent_event_ids
artifact_refs
metadata
```

Examples of source kinds include ChatGPT web, Gemini web, Codex/IDE, GitHub, Oracle runtimes, A2A agents, MCP tools, and imported historical conversations.

The Experience Compiler may use any extractor/model to classify observations, decisions, hypotheses, rejected ideas, constraints, failures, lessons, and open questions. AgentOS then forces every extracted item back to Working/candidate status with exact supporting ExperienceEvent IDs and source hashes.

## Three memory layers remain

AgentOS keeps its memory semantics. External memory products may be storage/index providers; they do not define what the layers mean.

```text
L1 Working memory
  temporary observations, active reasoning material, candidate knowledge

L2 Project memory
  validated project-local facts, lessons, decisions, known debt and patterns

L3 Cross-project memory
  strongly validated reusable patterns and abstractions with wider propagation
```

Separately:

```text
Canonical ProjectState = what is operationally true now
Execution Journal      = what happened
Ephemeral StateView    = what one execution is allowed to see now
```

Promotion is immutable. When a candidate moves to a higher persistence/propagation layer, the promoted content-addressed knowledge object links to and supersedes the lower-trust version instead of mutating it in place.

## Indexing architecture

AgentOS does not own a general vector database.

The AgentOS-owned index projection contains stable semantic fields such as:

```text
knowledge_id
project_id
kind
status
abstraction_level
confidence
terms
concepts
structural_signatures
domain
```

Backends may be SQLite FTS, pgvector, Qdrant, Iranti, or another maintained search system.

The unique retrieval semantics are two-channel:

### Near association

Find directly related experience using terms/concepts/project relevance.

Example:

```text
new input: provider HTTP 403
 -> prior provider 403 / User-Agent / WAF lesson
```

### Far association

Find structurally similar experience from a different domain.

Example:

```text
multi-agent concurrent state mutation
              <structural analogy>
Git branches from a common base + conflict-aware merge
```

Far association should not merely return semantically similar text. It deliberately looks for shared structural signatures across domains.

## Governed synthesis boundary

The Cognitive Kernel builds a `SynthesisEnvelope` from selected near/far sources. The envelope is bounded and disposable.

A pluggable synthesizer can be:

- existing Provider Bridge model;
- Web Agent through an existing browser bridge;
- A2A remote agent;
- human collaborator;
- future workflow runtime.

The synthesizer may invent a novel hypothesis, but AgentOS normalizes it back to:

```text
status = candidate
abstraction_level = working
derived_from = exact source knowledge IDs
inherited evidence retained
contradictions retained
trigger provenance retained
```

A model cannot self-promote its output by claiming `validated` or `cross_project`.

## Re-synthesis on new input

Prior synthesis is not frozen forever.

The dependency graph tracks which synthesis records depend on which knowledge IDs. New input may create a `ResynthesisRequest` when:

- a source is superseded;
- new contradictory evidence targets a source;
- retrieval exposes a newly relevant association;
- a new cross-domain structural analogy enriches an earlier synthesis.

Priority is highest for contradiction/invalidation and lower for enrichment.

A `ResynthesisRequest` means only **reconsider this knowledge**. It does not mutate memory, ProjectState, or the external world.

## Hierarchical compaction and meta-synthesis

Already-synthesized knowledge can be synthesized again. The system does not need to reread all raw conversations every time.

```text
ExperienceEvent
  -> Working candidate
  -> Project knowledge
  -> project synthesis
  -> higher-order project synthesis
  -> Cross-project knowledge
  -> cross-project meta-synthesis
```

Every higher-order synthesis keeps lineage through `derived_from` / `supersedes`. The lineage resolver can walk those links back to original `exp_*` events or durable external evidence anchors.

Compaction is therefore lossy for prompt size but **not lossy for provenance**.

Cross-project meta-synthesis is planned only when validated cross-project candidates from multiple projects converge on shared concepts. It still produces a candidate requiring the normal promotion/governance path.

## Promotion semantics

Increasing persistence/propagation increases governance.

```text
Working -> Project
  requires confidence threshold + verified evidence + durable-memory controls

Project -> Cross-project
  requires higher confidence + multiple independent verified sources
  + contradiction review + cross-project governance controls
```

Superseded/rejected knowledge stays auditable and is excluded from normal retrieval by default rather than deleted.

## What makes this layer differentiated

Commodity components can already provide:

- embeddings/vector search;
- chat history;
- shared memory storage;
- agent protocols;
- browser automation;
- model inference.

AgentOS should reuse them.

The differentiated layer is the lifecycle:

```text
raw distributed experience
 -> governed structured knowledge
 -> indexed association
 -> cross-domain analogy
 -> re-synthesis
 -> evidence-aware promotion
 -> hierarchical compaction
 -> dependency-driven reconsideration
```

with explicit provenance, contradiction retention, supersession, confidence, and governance at every persistence boundary.

## Safety posture

The Cognitive Kernel is intentionally asymmetric:

```text
Freedom to think / associate / brainstorm: high
Authority to declare truth: low and gated
Authority to mutate canonical state: separate State Kernel gate
Authority to affect external systems: separate side-effect gate
```

This preserves creative exploration while preventing a stronger reasoning system from silently obtaining stronger authority.
