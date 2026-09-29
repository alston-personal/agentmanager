# Generic Video Generation Capability

`capability://media.video.generate` is the provider-neutral entry point for products such as IFTV.

Consumers describe the desired video job; the router selects or composes a governed provider. Provider-specific mechanics remain outside consumer code.

Initial provider:
- `capability://media.video.generate.minimax-h3` via `capability://compute.colab.execute`

Selection rules must consider:
- whether reference images are available/required;
- duration and provider limits;
- continuity requirements;
- current quota/runtime availability;
- cost/quality preference.

Fallback is never allowed to silently switch into a materially different cost or quality class. Every successful generation keeps the underlying provider receipt.

IFTV is the first intended consumer. Its initial adapter supports `VIDEO_GENERATION_MODE=h3_colab` while preserving its existing generation backends.
