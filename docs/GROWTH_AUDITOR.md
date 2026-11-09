# AgentOS Growth Auditor Contract

## Overview

The **Growth Auditor** is a fixed responsibility in AgentOS. While executors perform work and Atlast advances the open loops (execution -> acceptance -> close -> next work), the Growth Auditor independently evaluates whether accumulated validated experience caused later execution to improve.

## Growth Proof Ledger

Mutable evidence of growth belongs in the data repository:
`$AGENT_DATA_ROOT/growth-proof/ledger.json`

Live evidence must never be committed into the logic repository.

## Five-Tier Growth Classification (G1 - G5)

The Growth Auditor evaluates claims conservatively:

1. **G1 (Persistence / Source Experience)**:
   - Historical interactions, transcripts, or session logs are recorded.
   - Persistence alone is not self-growth.
2. **G2 (Independent Later Reuse)**:
   - A subsequent session or executor retrieves and successfully applies previously stored validated patterns.
3. **G3 (Causal Before-vs-After Uplift)**:
   - Measured latency reduction, token reduction, or test pass-rate improvement directly attributable to validated experience.
4. **G4 (Cross-Boundary Measured Transfer)**:
   - Experience gained in one project, model, or executor transfers to an independent project or executor with measurable performance gain.
5. **G5 (Longitudinal Autonomous Evolution)**:
   - Sustained multi-cycle capability expansion without human prompting or regression. Longitudinal proofs must not be inferred from a single event.
