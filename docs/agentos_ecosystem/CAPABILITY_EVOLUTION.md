# AgentOS Capability Evolution

Status: active architecture checkpoint
Date: 2026-08-27

## Why this document exists

Long exploratory conversations produce useful discoveries faster than a chat transcript can preserve them. AgentOS therefore treats architecture checkpoints as durable project state: when a discussion changes invariants, ownership, lifecycle, or the active execution plan, the result should be written into the repository rather than left only in conversation history.

The document is a checkpoint, not a frozen design. Future evidence may revise it through normal versioned commits.

## Core model

A capability is not merely a callable function. It is the semantic owner of a bounded kind of competence and of the experience needed to improve that competence.

A library or executor does not need to know that AgentOS exists. An adapter observes execution and turns abstract inputs, policy, outcomes, and provenance into `CapabilityExperience`. A capability-owned reducer/consolidator turns experience into candidate state. Evaluation and governance determine whether that candidate may become canonical.

Learning is therefore a property of execution, not a separately invoked action.

## Lowest semantic owner

Experience MUST converge to the lowest semantic owner that can explain it.

Examples:

- Layout profile/correction evidence -> Layout profile capability.
- Geometry repair evidence -> Layout geometry capability.
- How detection and geometry work together -> Layout reconstruction composite capability.
- Cross-domain lessons about how capabilities should evolve -> AgentOS meta-intelligence.

Raw domain history SHOULD NOT be promoted to the AgentOS root merely because it exists.

Upward promotion requires abstraction gain.

## Capability composition

Capabilities form a graph, not only a tree.

A composite capability C may use A and B without absorbing or deleting them. A, B, and C own different experience:

- A learns how A performs its own task.
- B learns how B performs its own task.
- C learns how to select, order, configure, recover, and evaluate A+B end-to-end.

The graph may later support relations such as `uses`, `composes`, `specializes`, and `supersedes`.

## Split and compose lifecycle

A capability that grows too broad may become a split candidate when evidence shows weak internal coupling, different evaluators, different failure modes, different update cadence, or independent improvement paths.

Two or more capabilities may become a composition candidate when evidence shows repeated co-usage, stable ordering/interface mapping, and a shared end-to-end objective.

Discovery of a candidate MUST NOT mutate production architecture directly. The safe lifecycle is:

`observe -> propose -> shadow -> evaluate -> governance -> promote/reject`

## Natural plasticity

The long-term design goal is that graph learning happens naturally from execution evidence rather than by a human explicitly saying "learn now" or "check relationships now".

Three distinct forms of learning are recognized:

1. Node/capability plasticity: a capability improves its own policy/state.
2. Edge/composition plasticity: evidence changes confidence in how capabilities should interact.
3. Graph/architecture plasticity: stable evidence can suggest split, composition, specialization, or replacement.

Automatic cognition and automatic hypothesis generation are allowed goals. High-impact production graph mutations remain governed and reversible.

Useful relations may strengthen; unused or harmful relations may decay. Provenance is retained even when attention/activation is reduced: forget attention, not provenance.

## Capability Runtime boundary

The generic AgentOS runtime owns protocol mechanics only:

`execution -> adapter -> CapabilityExperience -> reducer -> candidate state -> evaluator -> governance -> canonical state`

Domain intelligence remains inside the capability adapter/reducer/evaluator.

This prevents AgentOS root from becoming a monolithic learner that must understand every domain.

## LayoutLib reference implementation

LayoutLib is the first reference domain.

Current intended ownership:

- `layoutlib.profile-detection`: learns abstract parser/profile policy from layout features and correction outcome.
- `layoutlib.layout-reconstruction`: owns end-to-end composition experience.
- LayoutLib core itself remains a pure library.
- Browser local storage is edge cache/offline working memory, not the canonical intelligence owner.

The primary reward signal is human correction cost, not the mere act of pressing Analyze.

Raw layout images are not part of capability learning telemetry by default. Abstract features, policy, correction metrics, outcome, and provenance are sufficient for the current experiment.

## Canonical representation principle

For LayoutLib, Spatial IR is the canonical spatial description. Rendered 3D and interchange files are projections/adapters, not the source of truth.

General principle:

> Preserve semantics; derive presentation.

A consumer that understands the IR may use a native adapter. A consumer that does not understand it may receive an exported format such as OBJ, glTF/GLB, USD, or IFC.

Do not prematurely merge unrelated domain IRs into one giant universal schema. Share only the smallest proven common abstraction.

## Architecture-checkpoint discipline

Create or update a durable checkpoint when discussion produces one of the following:

- a new invariant or governance rule;
- a change in semantic ownership;
- a new capability boundary or graph relation;
- a major lifecycle decision;
- a parked branch that must be remembered but not executed now;
- a change in the active implementation sequence;
- experimental evidence that changes the architecture.

Not every conversational idea deserves a document. Checkpoints should capture decisions and falsifiable hypotheses, not raw transcript.

## Active focus

Keep execution narrow until the first closed loop is proven:

`Layout image -> Spatial IR -> user correction -> completion -> CapabilityExperience -> capability consolidation -> canonical policy -> fresh-node bootstrap`

Parked for later evidence-driven work: Character IR / IP Genome integration, trading strategy capabilities, full plasticity engine, Blender/Unity native adapters, and broad universal semantic-core extraction.
