# Oracle #117 ONE-dispatched Experience regression

Status: **A/B PASS; Master Experience Floor promotion still pending attribution gate**

## Provenance

- GitHub Actions workflow: `Oracle Exact Generation Executor Job Rollout`
- workflow run: `34439962572` (#29)
- accepted source generation: `core/integration@6fc41c10adce2c07c93f42344b62e25d5d67e4fd`
- Oracle runner: `instance-20260129-0852`
- ONE Node: `oracle-core-node`
- bounded job: `experience.regression`
- executor class: `openai-codex-local`
- job id: `action-228042af501a4cbbafa451dc7e05d047`
- uploaded artifact id: `10137567309`
- uploaded artifact zip digest: `sha256:2583e7cb736b9a5e5e751f41174b295af854680a769f6e1c872854a7f734e149`
- source artifact name: `oracle-exact-generation-executor-job-34439962572`

## Accepted observations

- exact-generation transport repair: PASS
- ONE controller dispatch entered: PASS
- bounded executor transport receipt: PASS
- executor available / routable / authorized / successful: all true
- credential exposed: false
- hydration receipt: PASS
- baseline score: `0.8571428571428571` (6/7)
- hydrated score: `1.0` (7/7)
- observed uplift: `0.1428571428571429` (+1/7)
- regression classification: `EXPERIENCE_REGRESSION_PASS`

This run is the first accepted evidence in this lane that the same exact Oracle generation completed the path:

`ONE controller -> bounded executor job -> openai-codex-local -> ONE Experience hydration -> sanitized terminal receipt`.

It therefore closes the previously observed runtime/transport blockers for this experiment. It also proves aggregate A/B improvement and a perfect hydrated floor for this seven-dimension benchmark.

## What this evidence does NOT prove

The revised #117 promotion gate explicitly forbids promoting Master Experience Floor from aggregate score alone. This receipt does not by itself attribute the single improved dimension to a specific Experience item, nor does it provide the requested `experience_id x behavior_dimension` contribution matrix.

Remaining #117 work is therefore bounded to observable Experience attribution evidence:

1. persist the exact hydration manifest / projection digest and Experience IDs for this accepted A/B generation;
2. persist per-dimension baseline vs hydrated values and deltas;
3. map candidate contributing Experience IDs and provenance to each material delta;
4. run bounded B-minus-Ei or grouped ablation for the material improvement(s), repeating only where stochasticity requires it;
5. record attribution confidence and explicit ambiguity;
6. only then evaluate `MASTER_EXPERIENCE_FLOOR=VERIFIED` and #117 closure.

Do not reopen already-closed Realm Fabric, Action Relay group-context, capability publication, Experience digest convergence, or ONE-dispatch blockers without contradictory new evidence.
