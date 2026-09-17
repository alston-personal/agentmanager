# AgentOS Discussion Index

**Status:** Core #290 source candidate.

## Purpose

The Discussion Index answers **where did we discuss this?** across Nodes, executor surfaces and sessions. It is searchable provenance, not a continuation or memory authority.

Canonical hierarchy remains:

1. explicit current user intent and governance;
2. Canonical Project / ONE state (`agentos.ir/v1` and durable runtime state);
3. accepted Experience artifacts;
4. governed receipts/evidence;
5. Discussion Index provenance;
6. provider/local chat history.

A search hit may explain where a decision came from, but it cannot overwrite Canonical IR or Experience.

## Identity model

Discussion provenance preserves the full boundary:

```text
Realm -> Node -> Surface -> Executor adapter -> Backend/model -> Session/thread -> Discussion record
```

Missing backend identity is recorded as `unknown`. Extension/surface branding is never proof of the backend model.

## Storage model

The ONE-owned indexed projection is stored below Agent Data:

```text
<agent-data>/discussion-index/<project-id>/records.jsonl
```

`agentos.discussion-record/v1` contains:

- project / realm identity;
- Node, surface, executor adapter, backend and session/source provenance;
- bounded summary/topics/entities/keywords for retrieval;
- source and semantic digests;
- links to Canonical IR, Experience, issues, receipts and Employee assignments;
- `promoted_to` links when later accepted state supersedes/promotes the discussion;
- privacy storage class.

The indexed projection must not contain credentials or secret-like material.

## Optional Transcript Vault

Raw transcripts are deliberately **not** stored in the Discussion Index. A future separately governed Transcript Vault may preserve encrypted raw history when the provider/surface permits explicit export or capture.

The vault is optional. Canonical continuation must continue to work if raw transcript retention is disabled or the transcript is deleted.

## Ingestion model

Provider-specific adapters produce bounded discussion records. Sources may include:

- session/checkpoint handoff emitted by an executor adapter;
- permitted Node-local session harvest;
- ChatGPT/App checkpoint through ONE transport;
- explicit import from a user-owned transcript archive.

Imported history is evidence only. Promotion into Canonical IR or Experience requires the existing governed publication/acceptance path.

## Query model

The initial Core primitive supports bounded read-only keyword/topic retrieval with project, Node and surface filters and returns provenance + canonical links. A later retrieval adapter may add embeddings/semantic-vector ranking without changing the record authority model.

Example intent:

```text
找我們之前在哪裡討論過 Master Experience Floor？
```

Expected result is not merely an LLM-generated recollection. It should return matching discussion records with time, Node/surface/session provenance and references such as #117, accepted IR generations or Experience artifacts.

## Security and authority

- discussion evidence != canonical truth;
- search is read-only;
- raw provider transcript != continuation authority;
- no hidden model state is represented as retrievable memory;
- current user intent outranks stale indexed history;
- secrets/credentials are rejected from searchable projections;
- future raw transcript retention must be a separate private boundary;
- discussion records cannot self-promote into Canonical IR or Experience.

## Current implementation boundary

`agent_core.discussion_index` implements:

- `agentos.discussion-record/v1` validation;
- deterministic semantic digest;
- append-only idempotent JSONL persistence with conflict fencing;
- secret-like projection rejection;
- provenance-preserving read-only search;
- `promoted_to` and canonical reference projection.

This first slice intentionally does not claim provider-wide transcript ingestion or embedding-backed semantic retrieval. Those require real surface adapters and operating acceptance across at least two executor surfaces.
