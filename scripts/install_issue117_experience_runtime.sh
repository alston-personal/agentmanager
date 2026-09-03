#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

RUNTIME_ROOT="${AGENTOS_ACTION_RUNTIME_ROOT:-$HOME/.local/share/agentos/action-runtime}"
DATA_ROOT="${AGENT_DATA_ROOT:-$HOME/agent-data}"
EXPECTED_COMMIT="${AGENTOS_ACTION_SOURCE_COMMIT:-}"

printf '%s' "$EXPECTED_COMMIT" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "ERROR: AGENTOS_ACTION_SOURCE_COMMIT must be exact" >&2
  exit 3
}

test -d "$RUNTIME_ROOT/.git" || { echo "ERROR: exact Action runtime worktree missing: $RUNTIME_ROOT" >&2; exit 4; }
OBSERVED=$(git -C "$RUNTIME_ROOT" rev-parse HEAD)
test "$OBSERVED" = "$EXPECTED_COMMIT" || {
  echo "ERROR: Experience runtime generation mismatch: expected=$EXPECTED_COMMIT observed=$OBSERVED" >&2
  exit 5
}

for path in \
  agent_core/experience.py \
  agent_core/experience_store.py \
  agentos_node/experience_mcp_stdio.py \
  experience/agentos-core-oracle.seed.json \
  scripts/seed_one_experience.py \
  scripts/install_codex_experience_mcp_oracle.py; do
  test -f "$RUNTIME_ROOT/$path" || { echo "ERROR: Experience runtime input missing: $path" >&2; exit 6; }
done

cd "$RUNTIME_ROOT"
PYTHONPATH="$RUNTIME_ROOT" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 scripts/seed_one_experience.py --seed experience/agentos-core-oracle.seed.json

PYTHONPATH="$RUNTIME_ROOT" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 scripts/install_codex_experience_mcp_oracle.py

PYTHONPATH="$RUNTIME_ROOT" AGENT_DATA_ROOT="$DATA_ROOT" python3 - <<'PY'
from agent_core.experience import ExperienceQuery
from agent_core.experience_store import discover_from_one
items = discover_from_one(
    ExperienceQuery(
        project_id='agentos-core',
        realm='oracle',
        capabilities=('agentos.core.develop','repository.merge','agentos.one.resolve','agentos.capability.discover','executor.liveness'),
        executor='codex',
        limit=20,
    )
)
assert items, 'accepted Experience projection is empty'
print('one_experience_store=PASS')
print('one_experience_items=' + str(len(items)))
PY

grep -q '# AGENTOS_EXPERIENCE_MCP_START' "$HOME/.codex/config.toml"
grep -q 'agentos-experience' "$HOME/.codex/config.toml"
grep -q "$RUNTIME_ROOT" "$HOME/.codex/config.toml"
echo "codex_experience_mcp=PASS"
echo "experience_runtime_source_commit=$EXPECTED_COMMIT"
