#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
cd "$ROOT"
echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "head=$(git rev-parse HEAD)"
echo '===== current owner-key storage references ====='
grep -RniE 'nativeWalletPrivateKey|customWalletPrivateKey|walletPrivateKey|ownerSecret|recovery.*private|privateKey' extension web-feed api scripts 2>/dev/null | sed -n '1,420p' || true

echo '===== git history key-name introduction ====='
for needle in nativeWalletPrivateKey customWalletPrivateKey walletPrivateKey chamber-owner-envelope-v1 post-key-v2; do
  echo "--- $needle"
  git log --all --date=iso --pretty=format:'%h %ad %s' -S"$needle" -- extension/background.js extension/*.js web-feed 2>/dev/null | sed -n '1,80p' || true
  echo
done

echo '===== commits around Aug 16-20 touching crypto/identity/recovery ====='
git log --all --since='2026-08-15' --until='2026-08-21 23:59:59' --date=iso --pretty=format:'%h %ad %s' -- extension/background.js extension/content.js web-feed api scripts | sed -n '1,220p'

echo '===== likely migration/recovery snippets from current tree ====='
grep -RniE 'migrat|legacy|recover|restore|rotate|wallet.*key|owner.*key' extension/background.js extension/sidepanel.js extension/content.js web-feed/app 2>/dev/null | sed -n '1,480p' || true
