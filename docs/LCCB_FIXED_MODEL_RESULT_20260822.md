# LCCB Fixed-Model Result — 2026-08-22

## Empirical receipt

The controlled Project Meridian fixed-model series was actually executed on Oracle and completed successfully.

- series: `meridian-fixed-model-73129`
- workflow run: `32581330887`
- artifact: `9477877435`
- artifact digest: `sha256:96ca40f58c8f743dc53bd4eb7fe0ae9345d3d8b9306d3a675d235e4dbd942b8a`
- experiment git commit: `11a910eeefd09f2a33a994c2bbef04c3831bdbe0`
- provider: OpenAI-compatible
- model: `gemini-3.1-flash-lite`
- seed/events: `73129 / 1000`
- stages: `0 / 100 / 1000`
- temperature: `0`
- repeats: `3`
- execution environment: Oracle Linux AArch64, Python 3.10.12
- execution transport: GitHub-hosted Actions -> governed SSH -> isolated Oracle `/tmp` workspace

Evaluator-only labels were chmod-inaccessible during model execution and restored only for the scoring phase. The raw response artifact, deterministic score artifact, environment fingerprint, capability manifest and immutable series manifest were preserved before the isolated workspace was removed.

## Results

| Stage | Fact recall | Source recall | Stale error | Unauthorized action | Completion |
|---|---:|---:|---:|---:|---:|
| age 0 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| age 100 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| age 1000 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |

All three repeats produced the same answer for every task. The primary controlled metrics therefore have zero observed repeat variance in this run.

Age 0 is not evidence of pre-existing knowledge: the frozen benchmark explicitly defines `unknown` as the correct answer before any Meridian experience is supplied. Consequently, raw fact-recall accuracy is an accuracy metric, not by itself a cognitive-growth metric.

## Source-recall interpretation

The age-100 and age-1000 source-recall value of zero must not be interpreted as provenance forgetting. The public task prompts ask for the current value, procedure, authority mode, or next work item; they do not request literal `lccb:meridian:event:NNNN` evidence references. The evaluator nevertheless counts those literal references for `source_recall_accuracy`.

This is a benchmark contract limitation discovered by the real run. Provenance retrieval needs either a separate source-citation task or a revised public response contract before source recall can support a cognitive claim.

## Hypothesis verdict

**This condition does not establish longitudinal cognitive improvement.**

The fixed model supplied with all public history visible at each age already reaches the controlled-task ceiling by age 100 and remains at the same ceiling at age 1000 for fact recall, stale-fact avoidance, governance safety, and completion. The measured age-100 -> age-1000 gain on those primary metrics is therefore zero.

That is still an important result: the experiment establishes a strong full-public-history / long-context baseline. A future AgentOS persistent-cognition condition cannot claim improvement merely by matching these numbers. It must demonstrate value on non-ceiling dimensions such as transfer to unseen tasks, revival after forgetting, reconciliation under contradictory state, provenance retrieval, context-constrained continuity, or equivalent tasks where structured accumulated cognition can outperform direct-history prompting.

Accordingly the current verdict is:

> **Fixed-model full-history baseline: validated and at ceiling. AgentOS cognitive-accumulation hypothesis: not supported or refuted by this condition; a discriminating AgentOS-vs-baseline condition is still required for an efficacy claim.**

## Evidence integrity

The downloaded Actions artifact was independently inspected after the run. The included pack manifest, capability manifest, environment, raw responses and scored-results hashes match the immutable series manifest. The series manifest also preserves hashes for the public experience, public tasks and evaluator-only labels, which are intentionally not included in the uploaded evidence bundle.

Full sanitized machine-readable result metadata is preserved at `research/results/lccb-meridian-fixed-model-73129-20260822.json`.

## Failure knowledge produced by the run

Two execution failures were converted into reusable negative knowledge rather than discarded:

1. The OpenAI-compatible upstream returned HTTP 403 when the research runner omitted the canonical `Accept` and AgentOS `User-Agent` headers. Aligning the runner with `agent_core.ai_client` fixed all age-0/100/1000 and repeat-3 model diagnostics.
2. Fresh isolated checkout execution exposed an implicit editable-install/PYTHONPATH dependency in `scripts/discover_agentos_node.py`. Adding explicit repo-root import bootstrap and a fresh-cwd regression test fixed the formal experiment.

Structured records are preserved at `research/results/lccb-execution-failure-knowledge-20260822.json`.
