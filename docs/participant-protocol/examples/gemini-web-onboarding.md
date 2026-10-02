# Example: Gemini Web self-onboarding experiment

Purpose: use Gemini Web as the first non-Node Participant to test whether a new participant can read the public contract, build only its adapter, and join without product-specific ONE Core changes.

## Important boundary

Gemini Web itself cannot be treated as READY merely because a browser can send prompts to it.

The experiment must prove:

```text
Gemini Web logical identity
 -> adapter
 -> Participant Protocol negotiation
 -> enrollment
 -> conformance
 -> verified capability
 -> ONE receipt
```

A GUI Worker/browser session may be used as transport/host, but transport is not the Participant capability itself.

## Suggested identity

```text
participant://agent/gemini-web
```

Recommended roles:

- agent
- model-provider
- browser-surface-client

Likely initial provided capabilities:

- llm.reason
- agent.review
- multimodal.analyze (only if the surface/adapter can actually pass supported inputs and it is verified)

Likely consumed capabilities:

- artifact.read
- artifact.write
- browser.interact

## Example invocation

Start from the canonical self-onboarding entrypoint:

`docs/participant-protocol/onboarding/SELF_ONBOARD.md`

The following notes are Gemini-specific examples only and are not normative protocol requirements.

1. docs/participant-protocol/README.md
2. docs/participant-protocol/v1.0/CONTRACT.md
3. docs/participant-protocol/v1.0/participant.schema.json
4. docs/participant-protocol/CONFORMANCE.md

Your task is to join AgentOS ONE as a new Participant named `participant://agent/gemini-web`.

Rules:

- Do not modify AgentOS ONE Core merely to accommodate Gemini.
- Implement the thinnest adapter between the Gemini Web surface and the existing AgentOS Participant Protocol.
- Do not invent a new Gemini-specific protocol.
- Keep transport, capability, feature and adapter version separate.
- Advertise only methods/capabilities/features that are actually implemented.
- Never mark your own claimed capability as verified; ONE-side conformance owns verification.
- Resolve locally resolvable requirements.
- Report login, credentials, approval, permissions or physical actions as HUMAN_REQUIRED rather than hanging.
- Preserve a stable Participant identity across reconnects.
- Produce receipts/evidence for each onboarding stage.
- If the current ONE runtime does not yet expose an endpoint needed by the published contract, report that as a protocol/runtime gap. Do not silently bypass ONE.

Expected workflow:

```text
inspect native Gemini Web surface
 -> inspect available AgentOS transport/bridge
 -> implement adapter
 -> produce manifest
 -> validate manifest against v1.0 schema
 -> request enrollment
 -> negotiate protocol
 -> run Core Conformance
 -> request verification of claimed capabilities
 -> register verified capabilities
 -> return final receipt
```

Minimum v1.0 methods:

- describe
- probe
- invoke
- status
- receipt
- shutdown

Return the following at completion:

1. adapter file/path and implementation summary
2. final Participant Manifest
3. supported and negotiated protocol version
4. claimed capabilities
5. verified capabilities
6. available/verified methods
7. requirements and blockers
8. host/dependency relationships
9. conformance results
10. enrollment/verification receipt IDs
11. any ONE-side protocol/runtime gaps discovered

Do not report JOINED/READY unless live ONE evidence proves enrollment, negotiation and conformance.

## Experiment success criteria

PASS requires live evidence for all of:

- stable Gemini Web Participant identity
- adapter exists
- manifest validates
- ONE accepts enrollment
- protocol 1.0 negotiation succeeds
- required methods pass
- at least one capability becomes ONE-verified
- ONE can invoke that capability
- response returns through ONE
- correlated receipt exists

Recommended first capability test:

```text
ONE
 -> invoke llm.reason on participant://agent/gemini-web
 -> Gemini Web returns a deterministic short response
 -> adapter returns result
 -> receipt correlates request and execution
```

Only after this passes should browser/desktop/artifact delegation be tested.
