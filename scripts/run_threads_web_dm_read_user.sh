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

STAGE="$(mktemp -d /tmp/agentos-threads-dm-read.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
echo "threads_web_dm_stage=START"
git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$STAGE"
test -f "$STAGE/scripts/threads_web_dm_bridge_user.py"
echo "threads_web_dm_stage=PASS"

set +e
(
cd "$STAGE"
AGENTOS_DM_STAGE="$STAGE" PYTHONPATH="$STAGE" python3 - <<'PY'
import os
from pathlib import Path
stage=Path(os.environ["AGENTOS_DM_STAGE"]).resolve()
try:
    import agentos_node.social.web_dm as web_dm
    import agentos_node.social.persona_dm as persona_dm
    print("threads_web_dm_import_web_dm=PASS")
    origins=[Path(web_dm.__file__).resolve(),Path(persona_dm.__file__).resolve()]
    if all(stage in p.parents for p in origins):
        print("threads_web_dm_import_origin=PASS")
    else:
        print("threads_web_dm_import_origin=FAIL")
        raise SystemExit(12)
except ModuleNotFoundError:
    print("threads_web_dm_import_web_dm=MISSING")
    raise SystemExit(12)
try:
    import playwright
    print("threads_web_dm_import_playwright=PASS")
except ModuleNotFoundError:
    print("threads_web_dm_import_playwright=MISSING")
    raise SystemExit(13)
PY
)
OUT="$(cd "$STAGE" && PYTHONPATH="$STAGE" python3 - "$STAGE/scripts/threads_web_dm_bridge_user.py" <<'PY' 2>&1
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
except SystemExit:
    raise
except Exception as exc:
    kind=type(exc).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}",kind):
        kind="UnknownError"
    print("threads_web_dm_bridge=ERROR")
    print("threads_web_dm_error_type="+kind)
    raise SystemExit(8)
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
  AUTO_OUT="$(cd "$STAGE" && PYTHONPATH="$STAGE" python3 "$STAGE/scripts/mio_threads_dm_autonomous_user.py" 2>&1)"
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
  if [ "$PERSONA" = "oursong" ]; then
    echo "threads_web_dm_stage=SESSION_RESUME"
    set +e
    RESUME_OUT="$(AGENTOS_DM_PERSONA="$PERSONA" bash "$STAGE/scripts/resume_threads_persona_login_user.sh" 2>&1)"
    RESUME_RC=$?
    set -e
    printf '%s\n' "$RESUME_OUT" | grep -E '^threads_persona_login_resume' || true
    if [ "$RESUME_RC" -eq 0 ] && printf '%s\n' "$RESUME_OUT" | grep -Fq 'threads_persona_login_resume=PASS'; then
      set +e
      OUT="$(cd "$STAGE" && PYTHONPATH="$STAGE" python3 - "$STAGE/scripts/threads_web_dm_bridge_user.py" <<'PY' 2>&1
import os, runpy, sys
path=sys.argv[1]
sys.argv=[path,"--persona",os.environ.get("AGENTOS_DM_PERSONA","mio")]
runpy.run_path(path,run_name="__main__")
PY
)"
      RC=$?
      set -e
      printf '%s\n' "$OUT" | grep -E '^threads_web_dm_' || true
      echo "threads_web_dm_python_rc=$RC"
      if printf '%s\n' "$OUT" | grep -Fq 'threads_web_dm_bridge=PASS'; then
        echo "threads_web_dm_autonomous=DISABLED_FOR_PERSONA"
        echo "threads_web_dm_read=PASS"
        exit 0
      fi
    fi
  fi
  echo "threads_web_dm_read=LOGIN_REQUIRED"
  exit 0
fi
if printf '%s\n' "$OUT" | grep -Fq 'threads_web_dm_bridge=PLAYWRIGHT_UNAVAILABLE'; then
  echo "threads_web_dm_read=PLAYWRIGHT_UNAVAILABLE"
  exit 5
fi

echo "threads_web_dm_read=FAIL"
exit "${RC:-1}"
