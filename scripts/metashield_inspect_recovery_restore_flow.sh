#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
BG="$ROOT/extension/background.js"
SP="$ROOT/extension/sidepanel.js"
HTML="$ROOT/extension/sidepanel.html"

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo '===== recovery functions ====='
for needle in 'async function recoverWithShares' 'recoverWithShares(' 'recovery/passkey/authenticate' 'decodeRecoveryCode' 'passwordRecoveryUnlock' 'recoveryCode'; do
  echo "--- $needle"
  grep -nF "$needle" "$BG" "$SP" "$HTML" 2>/dev/null | sed -n '1,120p' || true
done

echo '===== recoverWithShares context ====='
python3 - <<'PY'
from pathlib import Path
for path in [Path('/home/ubuntu/metashield-protocol/extension/background.js'),Path('/home/ubuntu/metashield-protocol/extension/sidepanel.js')]:
    if not path.exists(): continue
    lines=path.read_text(errors='replace').splitlines()
    hits=[i for i,l in enumerate(lines) if 'recoverWithShares' in l or 'authenticate/verify' in l or 'decodeRecoveryCode' in l]
    print('FILE',path)
    shown=[]
    for i in hits:
        a=max(0,i-35); b=min(len(lines),i+100)
        if any(a>=x and a<=y for x,y in shown): continue
        shown.append((a,b))
        print(f'--- lines {a+1}-{b}')
        for n in range(a,b): print(f'{n+1}: {lines[n]}')
PY

echo '===== writes to owner key storage ====='
grep -nE 'nativeWalletPrivateKey|customWalletPrivateKey|sharingPrivateKey|chrome\.storage\.local\.set' "$BG" | sed -n '1,260p'
