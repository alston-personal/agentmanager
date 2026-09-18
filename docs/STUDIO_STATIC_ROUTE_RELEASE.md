# Studio Static Route Release Capability

This capability is the canonical AgentOS carrier for releasing one static route from a pinned `alston-personal/studio-web` commit into the current Studio production runtime.

## Canonical reusable workflow

- `.github/workflows/reusable-studio-static-route-release.yml`
- Trigger surface: `workflow_call`
- First production consumer: `.github/workflows/oracle-release-milkcat-world-mvp.yml`
- Governance provider: `service://studio.static-route.release`
- Capability URI: `capability://studio.static-route.release`

The human-maintained capability contract remains `.agent/governance/studio_release_capabilities.yaml`. `agent_core/studio_capability_adapter.py` mirrors that contract into the runtime Governance Directory for generic Reuse Before Build resolution; the runtime directory is a query index, not a second source of truth.

## Contract

A consumer supplies only product-specific release facts:

- pinned 40-character `studio-web` source SHA
- one static route directory such as `world`
- backup namespace
- receipt schema
- newline-delimited literal acceptance anchors
- optionally, a funded Milkcat Platform credit account and positive integer credit cost

The shared carrier owns the repeated release mechanics:

1. validate the release contract;
2. when metering is explicitly enabled, resolve `capability://studio.static-route.release` through the Reuse Before Build gate and reserve credits;
3. connect through the Oracle deployment lane;
4. clone and detach the exact canonical source SHA;
5. build in an isolated temporary directory;
6. verify `dist/<route>/index.html` and all acceptance anchors;
7. preserve the previous live route under `agent-data/releases/studio-web/...`;
8. atomically replace only the requested route;
9. roll back on any post-deploy failure;
10. verify the route through local Nginx;
11. emit the route release receipt;
12. verify the public route;
13. when metering is enabled, commit the reserved credits only after successful end-to-end acceptance, or release the reservation after failure/rollback.

## Reuse Before Build and Credits boundary

Metering is **opt-in** in this slice. `credit_account: ''` and `credit_cost: 0` preserve the pre-existing unmetered production behavior. A consumer must not invent, grant, or self-fund credits inside its release wrapper. Enabling metering requires a separately funded account.

When enabled, `.github/workflows/reusable-studio-static-route-release.yml` invokes `scripts/milkcat_platform_execution.py`, which binds one execution ID to:

- the capability resolution decision (`reuse / compose / build / deny`);
- the selected governed provider(s);
- one credit reservation;
- final credit settlement (`commit` on success, `release` on failure);
- a durable `milkcat.platform-execution/v0.1` receipt under the AgentOS data layer.

The product consumer remains a thin parameter-only wrapper. It must not own deployment mechanics or credit-ledger mutations directly.

## Safety boundary

The first version intentionally supports a **single top-level static route only**. Route names are restricted to lowercase letters, digits, and hyphens. This prevents a consumer from widening scope through path traversal or by passing arbitrary filesystem paths.

This workflow does not prove or perform the full `studio-web` production cutover. It only releases the requested route into the existing runtime.

Credits v0.1 are internal off-chain integer accounting units. This contract does not define fiat value, payment processing, transferability, token settlement, or dynamic pricing.

## Assetization status

This capability is considered extracted because the common implementation now has a canonical source and Milkcat World consumes it through a parameter-only wrapper. It becomes broadly proven after at least one additional production route is migrated to the same carrier without adding product-specific deployment logic to the reusable workflow.

The Reuse Before Build + Credits integration is a candidate contract until CI passes and at least one explicitly metered, funded execution produces a live platform execution receipt. Existing unmetered production verification must not be relabeled as metered acceptance.
