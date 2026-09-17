# Studio Static Route Release Capability

This capability is the canonical AgentOS carrier for releasing one static route from a pinned `alston-personal/studio-web` commit into the current Studio production runtime.

## Canonical reusable workflow

- `.github/workflows/reusable-studio-static-route-release.yml`
- Trigger surface: `workflow_call`
- First production consumer: `.github/workflows/oracle-release-milkcat-world-mvp.yml`

## Contract

A consumer supplies only product-specific release facts:

- pinned 40-character `studio-web` source SHA
- one static route directory such as `world`
- backup namespace
- receipt schema
- newline-delimited literal acceptance anchors

The shared carrier owns the repeated release mechanics:

1. validate the release contract;
2. connect through the Oracle deployment lane;
3. clone and detach the exact canonical source SHA;
4. build in an isolated temporary directory;
5. verify `dist/<route>/index.html` and all acceptance anchors;
6. preserve the previous live route under `agent-data/releases/studio-web/...`;
7. atomically replace only the requested route;
8. roll back on any post-deploy failure;
9. verify the route through local Nginx;
10. emit a release receipt;
11. verify the public route.

## Safety boundary

The first version intentionally supports a **single top-level static route only**. Route names are restricted to lowercase letters, digits, and hyphens. This prevents a consumer from widening scope through path traversal or by passing arbitrary filesystem paths.

This workflow does not prove or perform the full `studio-web` production cutover. It only releases the requested route into the existing runtime.

## Assetization status

This capability is considered extracted because the common implementation now has a canonical source and Milkcat World consumes it through a parameter-only wrapper. It becomes broadly proven after at least one additional production route is migrated to the same carrier without adding product-specific deployment logic to the reusable workflow.
