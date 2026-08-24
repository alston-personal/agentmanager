# Distributed AgentOS Cloud-Core Deployment

This runbook activates the Distributed AgentOS Control Plane on the existing Linux Cloud-Core host. The repository already treats the Oracle VM as the primary listener; this procedure adds the new Control Plane without requiring every IDE/device to install the full AgentOS Host.

## Deployment model

```text
Internet / private overlay
        ↓ HTTPS
reverse proxy / tunnel
        ↓ loopback
127.0.0.1:8765  Distributed Control Plane
        ↓
SQLite in Agent Data Layer
        ↓
Runtime Dispatcher
   ├─ GitHub Actions
   ├─ lightweight pull nodes
   └─ optional Provider Bridge :8775

Control Plane
   └─ best-effort mirror → private my-agent-data/projects/<project>/continuity/latest.json
```

Keep ports 8765/8775 bound to loopback unless there is a deliberate authenticated network design in front of them.

## 1. Update the Core checkout

Use the feature branch during deployment validation:

```bash
cd ~/agentmanager
git fetch origin
git switch feature/distributed-agentos-runtime
git pull --ff-only
python3 -m pip install -e .
```

Do not merge PR #2 merely to test deployment. The GitHub Actions worker itself must eventually exist on the branch/ref used for `workflow_dispatch`; production GitHub routing should use a workflow present on the chosen deploy ref.

## 2. Configure non-secret Core settings

In `~/agentmanager/.env`:

```bash
AGENT_MODE=CORE
AGENTOS_DISTRIBUTED_SERVICES_ENABLED=1
AGENTOS_PROVIDER_BRIDGE_ENABLED=0

AGENTOS_CONTROL_PLANE_HOST=127.0.0.1
AGENTOS_CONTROL_PLANE_PORT=8765
AGENTOS_CONTROL_PLANE_PUBLIC_URL=https://<real-agentos-hostname>

AGENTOS_CONTINUITY_MIRROR_REPOSITORY=alston-personal/my-agent-data
AGENTOS_CONTINUITY_MIRROR_BRANCH=main
AGENTOS_CONTINUITY_MIRROR_ROOT=projects
```

Do not leave `https://agentos.example.com` as the production URL.

If GitHub Actions dispatch is enabled, also configure the repository/workflow/ref/capability values from `.env.example`.

## 3. Put secrets outside the repository

Recommended file:

```text
~/.agentos.secrets
```

Set permissions:

```bash
touch ~/.agentos.secrets
chmod 600 ~/.agentos.secrets
```

Required for the first Control Plane deployment:

```bash
AGENTOS_CONTROL_PLANE_TOKEN=<strong-random-bearer-token>
AGENTOS_CONTINUITY_MIRROR_TOKEN=<private-my-agent-data-contents-write-token>
```

Optional routing secrets:

```bash
AGENTOS_GITHUB_TOKEN=<actions-workflow-write-token>
```

Provider API keys are not required while `AGENTOS_PROVIDER_BRIDGE_ENABLED=0`.

The generated Distributed AgentOS systemd units load both `.env` and optional `%h/.agentos.secrets`.

## 4. Expose HTTPS safely

The Control Plane process should normally stay on `127.0.0.1:8765`. Put an existing reverse proxy, authenticated tunnel, VPN/overlay, or equivalent ingress in front of it.

Required properties:

- HTTPS for non-loopback IDE/runtime clients
- preserve `Authorization: Bearer ...`
- proxy request bodies of at least 1 MiB
- do not expose SQLite/data files
- do not log bearer tokens
- rate-limit or network-restrict the endpoint where practical

The public URL must resolve to the same endpoint configured as `AGENTOS_CONTROL_PLANE_PUBLIC_URL`.

## 5. Install/restart through the existing AgentOS service installer

```bash
cd ~/agentmanager
python3 scripts/install_services.py
```

The Linux platform driver calls `scripts/install_systemd_user.sh`. With the enable flags above it will install/start:

```text
agentos-control-plane.service
```

Provider Bridge remains installed but stopped/disabled until explicitly enabled.

Inspect:

```bash
systemctl --user status agentos-control-plane.service
journalctl --user -u agentos-control-plane.service -n 100 --no-pager
```

File log:

```text
$AGENT_DATA_ROOT/logs/distributed_control_plane.log
```

## 6. Local health verification

On the Core:

```bash
curl -fsS http://127.0.0.1:8765/health
```

Expected service:

```json
{"service":"distributed-agentos-control-plane","status":"ok"}
```

Then test an authenticated project read through the public HTTPS route:

```bash
curl -fsS \
  -H "Authorization: Bearer $AGENTOS_CONTROL_PLANE_TOKEN" \
  "$AGENTOS_CONTROL_PLANE_PUBLIC_URL/v1/projects/agentmanager/state"
```

A project with no runtime task yet may legitimately return `recommendedAction: start`.

## 7. IDE smoke test

On another development machine/IDE terminal:

```bash
python -m pip install -e /path/to/agentmanager
export AGENTOS_CONTROL_PLANE_URL=https://<real-agentos-hostname>
export AGENTOS_CONTROL_PLANE_TOKEN=<authorized-token>

cd /path/to/agentmanager
agentos status
```

The committed `.agentos/project.json` should resolve the project as `agentmanager` regardless of the local clone folder name.

For a harmless first task, use a capability that has an available runtime/provider before submitting. `agentos continue` will not duplicate a task already in progress.

## 8. Verify private connector mailbox

After the first successful `submit` or `complete`, confirm the Core replaced the bootstrap checkpoint in:

```text
alston-personal/my-agent-data
projects/agentmanager/continuity/latest.json
```

The mirror response must not be used as an execution fence. If GitHub is temporarily unavailable, task operations continue and report mirror state as degraded.

## 9. Enable Provider Bridge later

Only after provider routes and credentials are ready:

```bash
AGENTOS_PROVIDER_BRIDGE_ENABLED=1
```

Configure at least:

```bash
AGENTOS_PROVIDER_BRIDGE_TOKEN=<strong-token>
AGENTOS_PROVIDER_ROUTES_FILE=config/provider-routes.example.json
```

and the environment variables referenced by the routes you actually intend to use (for example `OPENAI_API_KEY`, `GEMINI_API_KEY`, or a relay token).

Re-run:

```bash
python3 scripts/install_services.py
systemctl --user status agentos-provider-bridge.service
```

## 10. Rollback

Fast service rollback without deleting state:

```bash
AGENTOS_DISTRIBUTED_SERVICES_ENABLED=0
python3 scripts/install_services.py
```

This stops/disables the Distributed Control Plane and Provider Bridge units. It does not delete the SQLite Control Plane database or private continuity mirror.

After deployment validation is satisfactory, review Draft PR #2 and explicitly decide whether to merge it to `main`.
