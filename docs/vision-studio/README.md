# AgentOS Vision Studio

## Purpose

Vision Studio turns a short creative intent into a finished, publishable video while keeping story, production state, cost, provenance, and quality gates explicit.

It is not a single video model. It is an orchestration layer over writing, storyboarding, casting, image/video generation, audio, editing, QC, and publishing capabilities.

## User contract

Minimum input:

```text
Make a short film about Mio walking out of a Taipei metro station on a rainy night.
Mood: lonely, but quietly hopeful.
```

Expected output:

- final video file
- production receipt
- total cost
- models/executors used
- attempts/rejections per shot
- QC result
- reusable project IR

## Production pipeline

```text
Vision
  -> Producer
  -> Writer
  -> Director
  -> Storyboard / Shot Planner
  -> Casting / Character Identity
  -> Art / Wardrobe / Props / Location
  -> Model Router
  -> Shot Generation
  -> Continuity Supervisor
  -> Editor
  -> Audio / Music / Dialogue
  -> QC
  -> Deliverable + Receipt
```

## Routing policy

Default priority:

1. existing paid entitlement / included credits
2. local or already-owned compute
3. paid external API
4. manual web/GUI executor only when API/native executor is unavailable

The router must optimize for:
- quality
- character consistency
- prompt adherence
- latency
- retry probability
- cost
- licensing/commercial constraints

## Required receipts

Every finished production should report:

- project_id
- deliverable_id
- duration
- aspect_ratio
- generators used
- cost by provider
- render time
- attempts
- accepted shots
- rejected shots
- QC scores
- final file location
- provenance / source assets

## MVP acceptance

First acceptance production: `rain-exit-v001`.

A pass requires:
- 10s vertical MP4
- four planned shots
- Mio identity continuity
- wardrobe continuity
- rainy Taipei metro environment
- no major anatomy glitches
- coherent camera language
- audio bed present
- production receipt emitted
- total generation cost recorded

This capability should absorb existing IFTV/video experiments rather than becoming another isolated project.
