# Portable Media Capability Contract v0 (draft)

Status: specification only; NOT a deployed image generator, asset bridge or publisher. Applies to Mio, Folk and any independently authorized persona. Do not hard-code Oracle, GitHub, ChatGPT, Threads or a provider as owner of a persona or media asset.

## Ownership boundaries
- Persona package: portable identity, versioned approved references, event/wardrobe IDs, disclosure rules, access grants and publication intent. A persona is not an executor.
- Media capability: `media.generate`, `media.edit`, `asset.ingest`, `asset.read`, `asset.export` and `social.publish` are separately resolved contracts. A model adapter, storage adapter, runner and platform publisher may live on different nodes.
- Control plane selects an authorized provider by capability, supported input/output types, cost/consent and availability. Never silently downgrade an image intent to text or regenerate a different asset.
- A node may cache or execute but cannot become the only copy of portable persona state. Credentials stay with the authorized account/provider, never in export bundles.

## Artifact envelope (portable metadata)
```json
{
  "schema": "agentos.media.asset.v0",
  "asset_id": "asset:<opaque-id>",
  "owner_scope": "persona:<owner>/<persona-id>",
  "event_id": "<stable-event-id>",
  "content": {"mime": "image/jpeg", "sha256": "<64-lowercase-hex>", "byte_length": 0},
  "locations": [{"kind": "artifact", "uri": "<portable-or-exportable-handle>", "expires_at": null}],
  "provenance": {"source": "generated|user_upload|licensed_source|composite", "generator": "<provider-optional>", "inputs": ["<authorized-reference-asset-id>"], "scene_source": "<asset-id-or-null>"},
  "rights": {"owner": "<owner-id>", "license": "<documented-rights>", "publication_allowed": false, "commercial_allowed": false},
  "integrity": {"background_preserved": null, "identity_reference_checked": null, "human_approved": false},
  "state": "draft"
}
```
No public URL or provider-specific filesystem path is the sole canonical identity of an asset; exports include original bytes, envelope and hashes. URI expiration requires refresh through `asset.read` / `asset.export`. Do not export licensed third-party image bytes unless license permits. No source credentials in metadata.

## Task request and provider-neutral response
```json
{
  "schema": "agentos.media.request.v0",
  "intent_id": "<idempotency-key>",
  "persona_ref": "<authorized-persona-id-and-version>",
  "operation": "media.edit",
  "input_assets": ["<source-scene-asset-id>", "<approved-identity-asset-id>"],
  "constraints": {"preserve_background": true, "do_not_add_objects": true, "identity_consistent": true, "season_and_activity": "hot-weather-hiking", "format": "image/jpeg"},
  "delivery": {"target": "asset.ingest", "publication": "separate"}
}
```
Response MUST be `asset_id` + immutable SHA-256 + receipt ID, or a structured failure with capability/provider and retry-safe status. Completion of image generation does not imply successful ingestion, human approval or publication.

## State machine
`requested -> generated -> ingested -> verified -> approved -> publish_requested -> platform_confirmed`; any step may enter `failed` without falsifying later states. Verify target identity, image dimensions/MIME/SHA, reference likeness, source-scene preservation and rights before approval. `social.publish` consumes an approved exact asset ID and intent ID; before retry, reconcile prior platform object/receipt to avoid duplicates. Confirm public IMAGE media, object ID and permalink. Never post a substitute asset on failure.

## Portability + Folk tenancy test
1. Export Mio package without platform credentials: references, metadata, authorized asset bytes, event history and stable IDs. Import to a different node, remap asset locations, verify SHA and continue without rewriting persona logic.
2. Create a separate Folk persona on the same media adapters, enforcing owner-scope checks; Folk MUST NOT read Mio's private references, memories or asset bytes.
3. Run image generation on a non-Oracle provider, store through a different adapter and publish through a third: no provider paths in persona package or social publisher.
4. Revoke publication permission; generation and export remain distinct, publication fails closed. If the image source cannot be preserved or a reference is unavailable, fail with actionable status instead of inventing a background.
5. A ChatGPT chat attachment is not presumed accessible from Oracle. Import must carry authorized actual bytes and checksum via a verified bridge. No simulated completed receipt.

## Rollout acceptance (NOT YET VERIFIED)
Implement adapter schemas and contract tests in shared runtime; add artifact ingestion and SHA verification; integrate ONE approved Mio hiking JPEG through an authorized bridge; inspect public image readback and permalink; then test Folk isolated import. The current hiking post has NOT been published merely by writing this contract.
