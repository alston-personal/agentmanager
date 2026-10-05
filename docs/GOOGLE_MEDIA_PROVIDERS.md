# Google media providers

AgentOS models Google Flow and Google Vids as governed web providers rather than assuming a public automation API.

## Capabilities

- `capability://media.video.generate.google-flow`
  - provider: `service://media.google-flow.web`
  - service: `https://flow.google.com/`
  - role: generative filmmaking / shot creation
- `capability://media.video.compose.google-vids`
  - provider: `service://media.google-vids.web`
  - service: `https://vids.google.com/`
  - role: video composition, editing, avatar/voice and export workflows when available to the authenticated account

Both start as `declared`. They must not become `verified` merely because the public site exists.

## Live probe

The existing governed desktop-inspection lane can run a read-only provider probe on the interactive Windows node.

The probe:

1. opens only the allowlisted Flow and Vids URLs;
2. waits for each page to settle;
3. records visible window titles and process names;
4. captures a low-quality screenshot only to obtain non-secret dimensions/hash evidence;
5. removes screenshot image bytes before committing evidence;
6. does not click generation controls, enter credentials, purchase credits, or bypass challenges.

Evidence is written to:

`.agentos/evidence/google-media-provider-probe-current.json`

Provider classification is intentionally conservative:

- `READY`: a provider-specific window title is visible;
- `AUTH_REQUIRED`: a Google sign-in/login title is visible;
- `UNKNOWN`: browser navigation happened but the title is not enough to establish readiness.

A later provider-specific adapter may add deeper semantic inspection, quota discovery and effect execution after the read-only probe succeeds.

## Routing

These providers should be selected by capability and policy rather than hard-coded by callers. A future video director may route shots among Colab/MiniMax H3, Google Flow, Google Vids, and other providers according to quality, credits, session health, format and task type.

No provider credential belongs in prompts, manifests, receipts or repository evidence.
