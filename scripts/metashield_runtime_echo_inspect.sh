#!/usr/bin/env bash
set -u
ROOT=/home/ubuntu/metashield-protocol
PID=$(ss -ltnp 2>/dev/null | sed -n 's/.*127\.0\.0\.1:3011.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)
echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "api_pid=${PID:-}"
if test -n "${PID:-}"; then
  echo '===== api process ====='
  ps -o pid,ppid,user,lstart,args -p "$PID" || true
  PPIDV=$(ps -o ppid= -p "$PID" | tr -d ' ')
  echo "api_ppid=$PPIDV"
  test -n "$PPIDV" && ps -o pid,ppid,user,lstart,args -p "$PPIDV" || true
  echo '===== proc cmdline ====='
  tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true; echo
  echo '===== proc cwd ====='
  readlink -f "/proc/$PID/cwd" 2>/dev/null || true
  echo '===== proc executable ====='
  readlink -f "/proc/$PID/exe" 2>/dev/null || true
  echo '===== selected environment ====='
  tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | grep -E '^(PATH|HOME|PM2_HOME|NODE|NVM|PWD)=' || true
fi

echo '===== pm2 candidates ====='
for p in \
  /usr/bin/pm2 /usr/local/bin/pm2 \
  /home/ubuntu/.local/bin/pm2 \
  /home/ubuntu/.npm-global/bin/pm2 \
  /home/ubuntu/.nvm/versions/node/*/bin/pm2 \
  /home/agentos-node/.nvm/versions/node/*/bin/pm2 \
  /home/agentos-node/.local/bin/pm2; do
  for x in $p; do test -x "$x" && echo "$x"; done
done
find /home/ubuntu /home/agentos-node -maxdepth 6 -type f -name pm2 -perm -111 2>/dev/null | sed -n '1,80p' || true

echo '===== PM2 homes ====='
ls -la /home/ubuntu/.pm2 2>/dev/null | sed -n '1,120p' || true
ls -la /home/agentos-node/.pm2 2>/dev/null | sed -n '1,120p' || true

echo '===== likely launch artifacts ====='
find "$ROOT" /home/ubuntu -maxdepth 4 -type f \( -name 'ecosystem*.js' -o -name 'ecosystem*.cjs' -o -name 'ecosystem*.json' -o -name '*.service' -o -name '*start*.sh' -o -name '*run*.sh' \) 2>/dev/null | grep -Ei 'chamber|metashield|echo|ecosystem|pm2' | sed -n '1,160p' || true

echo '===== Echo source files ====='
find "$ROOT/web-feed/app" -maxdepth 5 -type f \( -name '*.tsx' -o -name '*.ts' \) | sort | sed -n '1,200p'
echo '===== suspicious empty-route construction ====='
grep -RniE 'wallet_address|walletAddress|identityAlias|alias|/echo/\$\{|href=.*echo|Chamber Portal|studio\.milkcat\.org/reborn|chamber-extension-v0\.6\.0' "$ROOT/web-feed/app" 2>/dev/null | sed -n '1,360p' || true

echo '===== dynamic page snippets ====='
for f in "$ROOT"/web-feed/app/'[wallet_address]'/'[platform]'/*.tsx "$ROOT"/web-feed/app/'[wallet_address]'/'[platform]'/*.ts; do
  test -f "$f" || continue
  echo "--- $f"
  nl -ba "$f" | sed -n '1,320p'
done
