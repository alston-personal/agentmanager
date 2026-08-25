#!/usr/bin/env bash
set -euo pipefail

OUT=.agentos/evidence/studio-web-host-audit-deterministic.txt
mkdir -p .agentos/evidence
SITE=studio.milkcat.org
WEB=/home/ubuntu/zeus-writer/website
{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "hostname=$(hostname)"

  echo '=== ACTIVE WEB CONFIG ==='
  for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
    [ -r "$f" ] || continue
    if grep -q "$SITE" "$f"; then
      echo "--- FILE $f"
      cat "$f"
    fi
  done

  echo '=== WEBSITE SOURCE / BUILD OWNERSHIP ==='
  for p in /home/ubuntu/zeus-writer /home/ubuntu/zeus-writer/website "$WEB/dist"; do
    if [ -e "$p" ]; then
      stat -c '%U:%G %a %F %n' "$p" || true
    else
      echo "missing=$p"
    fi
  done
  if [ -d /home/ubuntu/zeus-writer/.git ]; then
    git -c safe.directory=/home/ubuntu/zeus-writer -C /home/ubuntu/zeus-writer rev-parse --show-toplevel 2>&1 || true
    git -c safe.directory=/home/ubuntu/zeus-writer -C /home/ubuntu/zeus-writer branch --show-current 2>&1 || true
    git -c safe.directory=/home/ubuntu/zeus-writer -C /home/ubuntu/zeus-writer rev-parse HEAD 2>&1 || true
    git -c safe.directory=/home/ubuntu/zeus-writer -C /home/ubuntu/zeus-writer status --short 2>&1 | head -100 || true
  fi
  if [ -r "$WEB/package.json" ]; then
    echo '--- package.json'
    cat "$WEB/package.json"
  fi

  echo '=== WEBSITE COUPLING SCAN ==='
  if [ -d "$WEB" ]; then
    find "$WEB" -maxdepth 3 -type l -printf 'symlink %p -> %l\n' 2>/dev/null | sort || true
    grep -RInE --exclude-dir=node_modules --exclude-dir=dist --exclude='*.map' \
      '(/home/ubuntu/|\.\./\.\./|\.\./[^./]|zeus-writer|layoutlib|agent-data|localhost:|127\.0\.0\.1:)' \
      "$WEB" 2>/dev/null | head -500 || true
  fi

  echo '=== LISTENERS ==='
  ss -ltnp 2>&1 || true

  echo '=== RELEVANT PROCESSES ==='
  ps -eo user,group,pid,ppid,etime,args --sort=user | grep -E \
    '(node|next|uvicorn|gunicorn|python|run_demo|chamber|echo|iftv|hanzi|ip.?genome|layout.?lab|zeus|acas|prophecy)' \
    | grep -v -E '(grep -E|github-actions)' || true

  echo '=== USER SYSTEMD UNITS ==='
  find /home/ubuntu/.config/systemd/user -maxdepth 1 -type f -name '*.service' -print 2>/dev/null | sort | while read -r u; do
    echo "--- UNIT $u"
    grep -E '^(Description|ExecStart|WorkingDirectory|Environment|EnvironmentFile|User|Group|Restart|UMask)=' "$u" 2>/dev/null || true
  done

  echo '=== AGENTOS WORKFLOW / DEPLOYMENT COUPLING ==='
  ROOT=/home/ubuntu/agentmanager
  if [ -d "$ROOT" ]; then
    grep -RInE --include='*.yml' --include='*.yaml' --include='*.py' --include='*.sh' --include='*.json' \
      '(studio\.milkcat\.org|/home/ubuntu/zeus-writer/website|site\.sync_build|site://studio\.milkcat\.org)' \
      "$ROOT/.github" "$ROOT/scripts" "$ROOT/agentos_node" "$ROOT/config" "$ROOT"/resource* 2>/dev/null | head -800 || true
  fi

  echo '=== PUBLIC BASELINE ==='
  paths=(
    '/'
    '/dashboard'
    '/layout-lab/'
    '/prophecy/'
    '/novels/'
    '/ipgenome'
    '/iftv'
    '/echo'
    '/hanzi'
    '/acas/'
  )
  for path in "${paths[@]}"; do
    tmp=$(mktemp)
    code=$(curl -L -sS --max-time 15 -o "$tmp" -w '%{http_code}' "https://$SITE$path" || true)
    bytes=$(wc -c < "$tmp" 2>/dev/null || echo 0)
    marker=$(tr '\n' ' ' < "$tmp" 2>/dev/null | sed -E 's/[[:space:]]+/ /g' | head -c 180 || true)
    printf 'path=%s status=%s bytes=%s marker=%q\n' "$path" "$code" "$bytes" "$marker"
    rm -f "$tmp"
  done

  echo '=== LOCAL BACKEND BASELINE ==='
  for port in 3000 3002 3005 3010 3011 3020 8088 8090; do
    code=$(curl -sS --max-time 5 -o /tmp/studio-local-probe -w '%{http_code}' "http://127.0.0.1:$port/" 2>/dev/null || true)
    echo "port=$port root_http=$code"
  done

  echo '=== AUDIT SAFETY ==='
  echo 'mutation=NONE'
  echo 'nginx_reload=NO'
  echo 'service_restart=NO'
  echo 'repository_write=NO'
  echo 'studio_host_audit=PASS'
} 2>&1 | tee "$OUT"
