# strategic-interaction

Reusable AgentOS library for representing and replaying multi-participant strategic interactions.

The library is intentionally domain-neutral. Financial markets, real-estate negotiation, procurement, auctions, pricing, and other domains should adapt their observations into this core rather than embedding domain semantics here.

## Core model

```
Participants
+ Environment state
+ Beliefs
+ Incentives / payoffs
+ Action history
+ Strategy reference
= InteractionState
```

The result is evaluated separately:

```
InteractionState
-> Prediction / Action proposal
-> Outcome
-> Evaluation
-> reusable Strategy Delta candidate
```

## Public boundary

```python
from strategic_interaction import (
    Participant,
    Belief,
    Incentive,
    ActionEvent,
    InteractionState,
    StrategySpec,
    StrategyDelta,
    resolve_strategy,
)
```

## Important boundary

Game theory is a toolbox, not an assumption.

Nash equilibrium, Bayesian games, repeated games, signaling games, prisoner's dilemma, and evolutionary dynamics can be implemented as evaluators over the same InteractionState. The library does not assume that real participants are perfectly rational or that observed behavior is at equilibrium.
