# Social Post Experiment Capability

A reusable post-publish observation and learning loop for Threads accounts.

## Flow

publish receipt -> observe -> persist raw snapshot -> create learning observation -> choose next checkpoint -> repeat -> promote stable evidence into account/persona strategy

The capability is account-neutral. It is intended to be shared by:
- mio.milkcat
- oursong_alston
- huang_alston

Each run is scoped by explicit account handle, provider post id and experiment id. Runtime data is isolated under:

`runtime/social/post-experiments/<account>/<experiment-id>/`

## Evidence model

`snapshots.jsonl` is raw public observation evidence. `learning.jsonl` is derived experiment evidence. A single observation must not silently become a durable strategy rule. Promotion into persona/account strategy remains a separate evidence-backed step.

Default checkpoints are 60, 360 and 1440 minutes after publication. When a checkpoint finds a new public reply, the next checkpoint becomes a fast-follow two hours later instead of blindly waiting for the next fixed slot.

This capability does not publish content, does not reply to users, and does not expose credentials. It only reads the explicitly selected account/post and persists experiment evidence.

## v1-compatible evidence fields (source contract; not production-readback acceptance)

The existing `post_experiment.py` adds a `post.caption_sha256` only for a non-empty string that was actually returned by the provider. It retains the original `post.text` and existing v1 keys. Unicode and physical line breaks are hashed as UTF-8 exact bytes without rewriting or normalization; the hash is **not** evidence that the provider returned an untruncated full caption.

`learning_record` now carries the source caption digest, `platform=threads`, `maturity` (early <24h, developing 24h–7d, mature >=7d), `insights_status`, and `source_evidence_ready` only for a successful metrics read with numeric values. Unknown, nested, missing and rounded metrics remain preserved as observations with `metric_precision=provider_unverified`; no precision or sample size is inferred. `analysis_eligible=false` and `causal_claim_allowed=false` are **always** the defaults until independent completeness, version, comparable cohort and confound review. A provider response or an exceptionally successful post must never directly rewrite Persona IR or approved voice.

This is a backward-compatible source enrichment, not a new publishing adapter, account entitlement, correction ledger, cross-platform analytics service, autonomous polling loop or a Hermes ONE receipt. Existing experiment snapshots/JSONL, queue and Social Runtime remain canonical. Further edits must first verify actual runtime evidence and the existing owner #426.
