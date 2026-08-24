# LCCB Experiment 2A — Evidence Selection Audit

**Status:** completed deterministic mechanism analysis  
**Model calls:** 0  
**Source provider experiment:** run `32615130545`  
**Audit workflow run:** `32618376056`  
**Audit SHA:** `96ce428b32fad9067a1cf8ca26d4c51c27ead283`  
**Audit artifact ID:** `9487630043`  
**Audit artifact digest:** `sha256:0e87b9aeb2d19d81b0764a0166998860976bd930c57260ee99329c7546729f6c`

## 1. Question

Experiment 2 showed a clear behavioral contrast: B1 and B3 remained fact-perfect, while B2 degraded from `7/13` correct facts at age 100 to `4/13` at age 1000 and produced `3/13` stale task errors.

The provider outputs alone do not prove whether this pattern came from the representation supplied to the model or from an unrelated reasoning failure. This audit therefore examines the **selected public evidence before model inference**.

For each task and condition, the evaluator asks:

- Is the canonical current source present in the selected public evidence?
- Is an older same-key source present?
- Is the condition exposing current only, current plus stale, stale only, or no same-key evidence?
- For the multi-source continuity task, what fraction of the canonical current proof sources is present?

Private labels are used only after public evidence selection, evaluator-side, to identify the canonical source. No label is exposed to any model because this audit makes no model calls.

## 2. Frozen-pack identity

The audit rebuilt the same deterministic Meridian pack used by Experiment 2:

- seed: `73129`
- events: `1000`
- experience manifest hash: `3d76a3b0a24fec821c27fba7c33c34aecfd64cdecc8329c50bccca56e01498d5`
- evaluator manifest hash: `41872f0c465c43dff86b81403f3b26707854f86b3ac0a6a26aac549b6cafaead`

Those hashes match the immutable Experiment 2 artifact. The audit therefore analyzes the same benchmark world rather than a regenerated approximation.

## 3. Aggregate evidence states

There are 12 single-source tasks plus one multi-source continuity task per stage.

### Age 100

| Condition | Selected events | Current-source coverage, 12 single-source tasks | Current only | Current + stale | Stale only | No same-key evidence | Continuity current-source coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| B1 | 100 | 12/12 | 12 | 0 | 0 | 0 | 100% |
| B2 | 16 | 7/12 | 7 | 0 | 0 | 5 | 0% |
| B3 | 58 | 12/12 | 12 | 0 | 0 | 0 | 100% |

### Age 1000

| Condition | Selected events | Current-source coverage, 12 single-source tasks | Current only | Current + stale | Stale only | No same-key evidence | Continuity current-source coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| B1 | 1000 | 12/12 | 5 | 7 | 0 | 0 | 100% |
| B2 | 16 | 4/12 | 4 | 0 | 3 | 5 | 0% |
| B3 | 58 | 12/12 | 12 | 0 | 0 | 0 | 100% |

The representations separate cleanly:

- **B1** always contains the current source, but as history grows it co-exposes superseded same-key evidence. At age 1000, 7/12 single-source tasks contain both current and stale same-key events.
- **B2** remains fixed at 16 selected events. Its current-source coverage drops from 7/12 to 4/12; three tasks become stale-only while five remain missing. It never contains the continuity task's current proof sources.
- **B3** remains fixed at 58 current semantic events and supplies current-only evidence for all 12 single-source tasks at both stages, plus complete continuity-source coverage.

## 4. Exact B2 stale-only tasks at age 1000

The audit identifies exactly three stale-only B2 selections:

| Task | Canonical current source | B2-selected stale source |
|---|---|---|
| `governance:meridian.deploy` | `lccb:meridian:event:0300` | `lccb:meridian:event:0070` |
| `state:service-01.owner` | `lccb:meridian:event:0120` | `lccb:meridian:event:0001` |
| `state:service-02.owner` | `lccb:meridian:event:0250` | `lccb:meridian:event:0002` |

These are the same three tasks that the provider model answered with stale values in the completed Experiment 2 responses.

## 5. Cross-layer alignment

The strongest result of the audit is the exact alignment between representation state and observed provider behavior.

### B2 at age 100

The selected evidence contains the current source for 7 of the 12 single-source tasks and 0% of the continuity proof set. The completed provider experiment reports exactly `7/13` fact accuracy.

### B2 at age 1000

The selected evidence contains:

- 4 current-only task states;
- 3 stale-only task states;
- 5 tasks with no same-key evidence;
- 0% continuity current-source coverage.

The completed provider experiment reports exactly:

- `4/13` fact accuracy;
- `3/13` stale-error rate.

### B3

B3 supplies current-only evidence for every single-source task and complete current continuity evidence at both stages. The provider experiment reports exactly `13/13` fact accuracy and `0/13` stale tasks at both stages.

### B1

B1 supplies current evidence for every task. At age 1000 it also exposes stale same-key history for 7 of 12 single-source tasks, yet the fixed model remains `13/13` fact-correct. This shows that raw full history is still sufficient for the current benchmark when the provider can process it, while B3 removes the supersession-resolution burden from the model-facing representation.

## 6. Causal interpretation

The audit substantially strengthens the **within-system mechanism explanation** of Experiment 2.

For the tested B2 lexical selector, the provider is not merely making arbitrary errors after receiving adequate evidence. The selector itself fails to supply the current authoritative evidence for exactly the tasks that are subsequently missed, and supplies only stale same-key evidence for exactly the tasks that become stale model answers.

Conversely, B3's structured projector deterministically replaces superseded same-key evidence with the current public semantic state. The provider then preserves all measured facts.

The evidence chain is therefore:

> public longitudinal history → condition-specific evidence selection → current/stale evidence state → observed model answer

For the frozen Meridian pack, the middle two links are now directly audited rather than inferred from aggregate accuracy alone.

This supports a narrower and stronger statement than “B3 is better because it is structured”:

> **The tested B3 current-state projector preserves canonical current evidence under revision, whereas the tested B2 lexical selector loses or retains stale evidence; the provider outputs track those representation differences exactly in the completed series.**

## 7. What this still does not prove

This analysis is not a third cognitive-provider experiment. It makes zero model calls and must not be counted as independent evidence that B3 has greater reasoning capability than B1.

It also does not establish that retrieval architectures in general are revision-blind. A stronger retrieval system could explicitly model time, supersession, authority, revision graphs, or current-state reconciliation. Such a system should become a new baseline rather than being rhetorically included in B2.

The analysis also uses evaluator labels to identify canonical source refs after evidence selection. That is appropriate for an evaluator-side audit but would be leakage if used in condition construction or model prompting. The implementation keeps those roles separate.

## 8. Scientific implication

Experiment 2 now has three mutually consistent layers of evidence:

1. **representation cost:** B3 uses 93.49% fewer prompt characters than B1 at age 1000;
2. **representation semantics:** B3 keeps current-only evidence while B2 develops stale-only/missing evidence under revision;
3. **provider behavior:** B3 and B1 remain fact-perfect, while B2's fact and stale scores exactly follow its selected evidence state.

This does not close the B1-versus-B3 capability question because B1 still resolves its mixed current/stale history correctly. It does, however, make the supersession mechanism substantially less ambiguous.

The direct remaining test is the frozen dense-revision stress series, where B1 must resolve thousands of authoritative supersessions while B3 carries only current state. That series is currently `PROTOCOL_READY_PROVIDER_BLOCKED`; provider HTTP 429 is recorded separately and cannot be interpreted as a cognitive outcome.

## 9. Reproducibility

- Analysis script: `scripts/analyze_lccb_evidence_selection.py`
- Workflow: `.github/workflows/lccb-evidence-selection-audit.yml`
- Successful workflow run: `32618376056`
- Audit SHA: `96ce428b32fad9067a1cf8ca26d4c51c27ead283`
- Artifact ID: `9487630043`
- Artifact digest: `sha256:0e87b9aeb2d19d81b0764a0166998860976bd930c57260ee99329c7546729f6c`
- Machine-readable summary: `research/results/lccb-evidence-selection-audit-73129-20260823.json`
- First failed audit run: `32618347026` — missing repo-root import bootstrap; pack construction had succeeded, analysis execution did not. The repair added the same repository import bootstrap used by the existing research runners and did not change the audit method.
