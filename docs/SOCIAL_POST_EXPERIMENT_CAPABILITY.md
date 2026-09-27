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
