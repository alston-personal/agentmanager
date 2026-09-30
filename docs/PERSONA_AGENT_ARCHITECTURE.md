# Persona Agent Architecture

AgentOS treats a persona as a first-class agent, not as a social-media bot.

## Core rule

A Persona Agent owns continuity: identity, versioned Persona IR, memory/event ledger,
relationships, PDCA state, energy/state dynamics and governance boundaries.

Capabilities are detachable adapters. Removing Threads, a wardrobe renderer, image
generation or a commerce connector must not erase or redefine the persona.

## Contract

- Agent manifest: `personas/<persona>/agent.yaml`
- Generic schema: `schemas/persona-agent.schema.json`
- Attachment schema: `schemas/persona-capability-attachment.schema.json`
- Discovery: `scripts/persona_agent_registry.py`
- Observer projection: persona-specific projector until promoted to a generic projector.

## Capability lifecycle

`planned -> attached -> degraded -> attached` or `detached`

External writes require receipts. A degraded capability becomes an incident/health
signal; it must not be interpreted as the Persona Agent itself being dead.

## Observability

Each Persona Agent should expose two projections:

1. Public life projection: public-safe current activity, recent meaningful events,
   interests and coarse health.
2. Owner projection: PDCA cycle, energy, capability health, pending external actions,
   incidents, uncertainty and IR revisions.

Neither projection exposes private model chain-of-thought.

## Mio

`persona.mio` is the first registered implementation. Her Threads, DM, Galaxy
relationship memory, wardrobe and visual-generation functions are attachments.
