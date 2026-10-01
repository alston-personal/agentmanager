#!/usr/bin/env bash
set -euo pipefail

GCLOUD_ROOT="${GCLOUD_ROOT:-/home/ubuntu/.local/opt/google-cloud-sdk}"
GCLOUD="${GCLOUD_ROOT}/bin/gcloud"
SCOPES="openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory"

if [[ ! -x "$GCLOUD" ]]; then
  echo "gcloud_missing=$GCLOUD" >&2
  exit 2
fi

mkdir -p /home/ubuntu/.config/gcloud
chmod 700 /home/ubuntu/.config/gcloud

echo "AgentOS Colab ADC bootstrap"
echo "This is a one-time interactive Google authorization for Oracle."
echo "Scopes: $SCOPES"
echo
exec "$GCLOUD" auth application-default login \
  --scopes="$SCOPES"
