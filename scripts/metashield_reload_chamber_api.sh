#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
API="$ROOT/api"
PM2_HOME=/home/ubuntu/.pm2
export PM2_HOME
before_pid=$(ss -ltnp 2>/dev/null | sed -n 's/.*127\.0\.0\.1:3011.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)
echo "before_pid=$before_pid"
test -n "$before_pid"
ps -o pid,ppid,user,lstart,args -p "$before_pid"

cd "$API"
npm ci --omit=dev >/tmp/chamber-api-npm-ci.log 2>&1
cat /tmp/chamber-api-npm-ci.log
node -e "Promise.all([import('@irys/upload'),import('@irys/upload-ethereum')]).then(()=>console.log('current_uploader_import=PASS')).catch(e=>{console.error(e);process.exit(1)})"
if grep -q '@irys/sdk' server.js; then
  echo 'legacy_sdk_source=FAIL'
  exit 10
fi
grep -q '@irys/upload' server.js
echo 'current_uploader_source=PASS'

PM2_CLI=""
while IFS= read -r p; do PM2_CLI="$p"; break; done < <(find /home/ubuntu/.npm/_npx -maxdepth 7 -type f -path '*/node_modules/pm2/lib/binaries/CLI.js' 2>/dev/null | sort)
test -n "$PM2_CLI"
echo "pm2_cli=$PM2_CLI"
pm2(){ node "$PM2_CLI" "$@"; }
pm2 ping
pm2 describe chamber-api | sed -n '1,140p'
pm2 restart chamber-api --update-env
sleep 4
pm2 describe chamber-api | sed -n '1,140p'

after_pid=$(ss -ltnp 2>/dev/null | sed -n 's/.*127\.0\.0\.1:3011.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)
echo "after_pid=$after_pid"
test -n "$after_pid"
if test "$before_pid" = "$after_pid"; then
  echo 'pid_rotated=FAIL'
  exit 11
fi
echo 'pid_rotated=PASS'
ps -o pid,ppid,user,lstart,args -p "$after_pid"

curl -fsS --max-time 20 http://127.0.0.1:3011/chamber-api/health
echo
echo 'api_health=PASS'
curl -fsS --max-time 20 https://studio.milkcat.org/chamber-api/health
echo
echo 'public_api_health=PASS'

echo '===== recent chamber-api PM2 log ====='
tail -n 60 /home/ubuntu/.pm2/logs/chamber-api-out.log 2>/dev/null || true
tail -n 60 /home/ubuntu/.pm2/logs/chamber-api-error.log 2>/dev/null || true
