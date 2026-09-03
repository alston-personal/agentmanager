#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: #117 Codex Experience regression must run as ubuntu on Oracle" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-117-experience-memory"
RUNTIME_ROOT="${AGENTOS_EXPERIENCE_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/experience-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
OUTPUT="${AGENTOS_EXPERIENCE_REGRESSION_OUTPUT:-$DATA_ROOT/runtime/issue-117-codex-experience-regression.json}"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"

if [ ! -f "$TARGET/scripts/oracle_codex_experience_regression_entry_v2.py" ]; then
  TMP="$RUNTIME_ROOT/.issue117-$SOURCE_COMMIT-$$"
  rm -rf "$TMP"
  mkdir -p "$TMP" "$RUNTIME_ROOT"
  git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$TMP"
  mv "$TMP" "$TARGET"
fi

cd "$TARGET"
echo "agentos_issue117_source_commit=$SOURCE_COMMIT"
echo "agentos_issue117_runtime_source=$TARGET"
echo "agentos_issue117_execution_cwd=$PWD"

echo "agentos_issue117_contract_tests=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 -m pytest \
    tests/test_experience_memory.py \
    tests/test_experience_store.py \
    tests/test_experience_mcp_stdio.py \
    tests/test_install_codex_experience_mcp_oracle.py \
    -q
echo "agentos_issue117_contract_tests=PASS"

echo "agentos_issue117_one_experience_seed=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/seed_one_experience.py" \
  --seed "$TARGET/experience/agentos-core-oracle.seed.json"
echo "agentos_issue117_one_experience_seed=PASS"

echo "agentos_issue117_codex_experience_mcp_install=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/install_codex_experience_mcp_oracle.py"
echo "agentos_issue117_codex_experience_mcp_install=PASS"

mkdir -p "$(dirname "$OUTPUT")"
set +e
PYTHONPATH="$TARGET" \
AGENT_DATA_ROOT="$DATA_ROOT" \
AGENTOS_RUNTIME_SOURCE_COMMIT="$SOURCE_COMMIT" \
  python3 "$TARGET/scripts/oracle_codex_experience_regression_entry_v2.py" \
    --output "$OUTPUT"
RC=$?
set -e

echo "agentos_issue117_regression_output=$OUTPUT"
if [ -f "$OUTPUT" ]; then
  cat "$OUTPUT"
fi

if [ "$RC" -eq 0 ]; then
  echo "agentos_issue117_codex_experience_regression=PASS"
else
  echo "agentos_issue117_codex_experience_regression=FAIL"
fi
exit "$RC"
