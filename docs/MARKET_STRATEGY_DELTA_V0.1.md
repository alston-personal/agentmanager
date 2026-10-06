# Market Strategy Delta IR v0.1

Parent: #1200 / #1251

## Principle

A Market Master is not a prompt persona.

It is:

```
Base Strategy IR
+ Strategy Delta IR
+ Pattern Set
+ Learning Memory
= reproducible Market Master instance
```

Persona/publication style is deliberately outside the prediction strategy.

## Determinism

The same base and delta must resolve to the same fingerprint. This enables:

- lineage
- replay comparison
- rollback
- promotion gates
- cross-model reuse

## Seed masters

v0.1 includes four deliberately different strategy deltas:

- Flow
- Momentum
- Reversal
- Neutral

These are seeds for Replay Tournament, not claims that the strategies have market edge.

## Cognitive Growth compatibility

A future strategy delta is only a candidate until evidence proves reusable uplift. Promotion follows the existing AgentOS Cognitive Growth Protocol:

Experience -> candidate delta -> validation -> holdout -> promotion -> later reuse -> measured uplift.

No single win/loss can directly mutate the active strategy.
