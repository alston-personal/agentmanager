#!/usr/bin/env bash
# Submit registered slash command through existing ONE Runner Window transport.
# This wrapper does not execute local command definitions or select a node.
set -euo pipefail
COMMAND="${1:?usage: submit_agentos_command.sh /status-diff <40-character-source-sha>}"
SOURCE_COMMIT="${2:?exact source commit SHA is required}"
[ "$#" -eq 2 ] || { echo "agentos_command=INVALID_ARGUMENTS" >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTENT="$(python3 "$SCRIPT_DIR/resolve_agentos_command.py" "$COMMAND")"
PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["dispatch"]["payload"],separators=(",",":"),ensure_ascii=False))' <<<"$INTENT")"
# Existing transport handles OIDC credentials, capability policy and Receipt.
exec bash "$SCRIPT_DIR/agentos_dispatch.sh" agentos.command invoke "$SOURCE_COMMIT" --payload-json "$PAYLOAD"
