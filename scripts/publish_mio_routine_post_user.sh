#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -un)" != 'ubuntu' ]; then
  echo 'mio_publish=WRONG_USER' >&2
  exit 2
fi
cd /home/ubuntu/agentmanager
exec python3 scripts/publish_mio_routine_post_user.py
