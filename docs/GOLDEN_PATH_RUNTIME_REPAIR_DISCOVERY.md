# Golden Path runtime repair capability — canonical resolution

**Capability:** `agentos.runtime / repair` (Runner Window)
**Owner:** existing ONE Scheduler → Oracle Bootstrap; not the general `node.runtime/converge` installer.
**Source:** `agent_core/runner_window.py` maps to `ACTION_REPAIR_TRANSPORT`; `agentos_node/bootstrap_control.py` executes `scripts/repair_antigravity_relay_user.sh`, which calls `scripts/install_action_relay_user.sh`.
**Hosted carrier:** `.github/workflows/core-integration-runtime-self-converge-20261007.yml` uses GitHub Actions OIDC audience `agentos-scheduler`. Note: this workflow is triggered only by changes to its own path on `core/integration`; **do not touch that path merely to induce a deployment**. Determine and use a currently authorized carrier.
**Pinned generation:** explicit `AGENTOS_REF=core/integration` and exact accepted source SHA, with `AGENTOS_ACTION_SOURCE_REF` and `AGENTOS_ACTION_SOURCE_COMMIT` propagated to the installer. The installer defaults to `main`; never trust that default for an integration candidate.
**Verification:** node-authoritative receipt with `action_relay_install=PASS`, exact `agentos_source_commit`, systemd runtime generation, capability marker, and stable service liveness. A GitHub job ID, source CI green, or generic `node.runtime/converge` does not prove relay installation.
**Next tests:** authorized `node.realm/inspect` terminal receipt; cross-node Oracle→vopc5750 A→B→C and replay recovery.
**Promotion:** this remains feature-development on `core/integration`; only after runtime acceptance should #1682 prepare a scoped protected-main PR, separately authorized.

## Required discovery / fail-closed rule

Before claiming a deployment capability is missing, inspect the Runner Window intent table, its mapped Bootstrap action, the exact fixed script it calls, downstream installers, and registered hosted workflow trigger/authority. Record both the *capability* and the *authorized carrier*. A present capability is not proof it is currently authorized or deployed. If no carrier can be invoked, report **carrier unavailable**, not **installer absent**, and do not fabricate a new control plane or use direct Oracle self-hosted runner.

## GitHub Actions run discovery and automatic deployment receipts (#2198)

A GitHub Actions `push` deployment **must not** be declared missing because `fetch_commit_workflow_runs` returned an empty collection: that connector method filters PR-triggered runs.

**Known working connected-source route** (verified against production Run 42965407789):

1. From the WorkItem's source SHA, perform an authorized GitHub repository GET:
   `https://api.github.com/repos/alston-personal/agentmanager/actions/runs?head_sha=<40-hex-sha>&per_page=100`.
   Filter returned runs by exact `workflow_id` / workflow name, branch and SHA; paginate if required. Do not guess Run IDs.
2. Read each candidate run's status, conclusion and exact head SHA; fetch the selected run's job IDs and sanitized logs. Check `accepted_release` / `agentos_control_plane_login_release=PASS` before calling a deployment accepted.
3. Reuse the original WorkItem as durable evidence. For #2198, the existing immutable release workflow has a separate `report-release-receipt` job that posts or updates an idempotent Run-ID-keyed comment on #2198, including failures, without deployment SSH secrets. It does not prove signed-in admin or tenant browser acceptance.
4. If the connected source returns an authorization error or no results, distinguish missing permission, unsupported endpoint and empty results; only then request the minimum user action. The GitHub connector supports repository `/actions/runs` with SHA filtering, even though its workflow-specific runs endpoint may reject the URL.

**Keep this distinction:** GitHub source CI success ≠ Oracle deployment accepted ≠ authenticated admin authorization ≠ first tenant Node/ONE runtime task receipt. Continue the original WorkItem until each claimed stage has its own evidence.
