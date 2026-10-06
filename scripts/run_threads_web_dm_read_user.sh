#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_read=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
PERSONA="${AGENTOS_DM_PERSONA:-mio}"
case "$PERSONA" in mio|oursong) ;; *) echo "threads_web_dm_read=INVALID_PERSONA" >&2; exit 2 ;; esac
if ! printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "threads_web_dm_read=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
fi

for rel in   agentos_node/social/web_dm.py   agentos_node/social/persona_dm.py   scripts/threads_web_dm_bridge_user.py   scripts/mio_threads_dm_autonomous_user.py   scripts/mio_persona_dm_decision_user.py   scripts/mio_persona_social_loop_user.py   scripts/send_mio_threads_dm_from_decision.py; do
  tmp="$(mktemp)"
  git -C "$REPO" show "$SOURCE_COMMIT:$rel" > "$tmp"
  install -D -m 0644 "$tmp" "$REPO/$rel"
  rm -f "$tmp"
done

set +e
PYTHONPATH="$REPO" python3 - <<'PY'
try:
    import agentos_node.social.web_dm
    print("threads_web_dm_import_web_dm=PASS")
except ModuleNotFoundError:
    print("threads_web_dm_import_web_dm=MISSING")
try:
    import playwright
    print("threads_web_dm_import_playwright=PASS")
except ModuleNotFoundError:
    print("threads_web_dm_import_playwright=MISSING")
PY
OUT="$(PYTHONPATH="$REPO" python3 - "$REPO/scripts/threads_web_dm_bridge_user.py" <<'PY' 2>&1
import os, re, runpy, sys
path=sys.argv[1]
sys.argv=[path,"--persona",os.environ.get("AGENTOS_DM_PERSONA","mio")]
try:
    runpy.run_path(path,run_name="__main__")
except ModuleNotFoundError as exc:
    name=str(getattr(exc,"name","") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}",name):
        name="unknown"
    print("threads_web_dm_bridge=ERROR")
    print("threads_web_dm_error_type=ModuleNotFoundError")
    print("threads_web_dm_missing_module="+name)
    raise SystemExit(7)
PY
)"
RC=$?
set -e
printf '%s\n' "$OUT" | grep -E '^threads_web_dm_' || true
echo "threads_web_dm_python_rc=$RC"

if printf '%s\n' "$OUT" | grep -Fq 'threads_web_dm_bridge=PASS'; then
  if [ "$PERSONA" != "mio" ]; then
    echo "threads_web_dm_autonomous=DISABLED_FOR_PERSONA"
    echo "threads_web_dm_read=PASS"
    exit 0
  fi
  set +e
  AUTO_OUT="$(PYTHONPATH="$REPO" python3 "$REPO/scripts/mio_threads_dm_autonomous_user.py" 2>&1)"
  AUTO_RC=$?
  set -e
  printf '%s\n' "$AUTO_OUT" | grep -E '^mio_dm_(autonomous|send)' || true
  if [ "$AUTO_RC" -ne 0 ]; then
    echo "threads_web_dm_autonomous=FAIL"
    exit "$AUTO_RC"
  fi
  echo "threads_web_dm_autonomous=PASS"
  echo "threads_web_dm_read=PASS"
  exit 0
fi
if printf '%s\n' "$OUT" | grep -Fq 'threads_web_dm_bridge=LOGIN_REQUIRED'; then
  echo "threads_web_dm_read=LOGIN_REQUIRED"
  exit 0
fi
if printf '%s\n' "$OUT" | grep -Fq 'threads_web_dm_bridge=PLAYWRIGHT_UNAVAILABLE'; then
  echo "threads_web_dm_read=PLAYWRIGHT_UNAVAILABLE"
  exit 5
fi

echo "threads_web_dm_read=FAIL"
exit "${RC:-1}"
