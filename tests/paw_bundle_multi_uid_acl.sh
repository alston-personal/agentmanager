#!/usr/bin/env bash
set -euo pipefail
# CI-only multi-UID integration; no Oracle, credentials, remote push or deployment.
test "$(id -u)" -eq 0
w=ci-paw-worker
p=ci-paw-publisher
useradd --system --no-create-home "$w"
useradd --system --no-create-home "$p"
root="$(mktemp -d)"
trap 'rm -rf "$root"; userdel "$w" || :; userdel "$p" || :' EXIT
install -d -m 0700 -o "$w" -g "$w" "$root/worker"
install -d -m 0700 -o "$w" -g "$w" "$root/worker/paw-470-bundles"
setfacl -m "u:$w:--x,u:$p:--x" "$root"
setfacl -m "u:$p:--x" "$root/worker"
setfacl -m "u:$p:r-x" "$root/worker/paw-470-bundles"
setfacl -d -m "u:$p:r-x" "$root/worker/paw-470-bundles"
runuser -u "$w" -- sh -c 'printf "test-bundle" > "$1"' -- "$root/worker/paw-470-bundles/test.bundle"
runuser -u "$p" -- test -r "$root/worker/paw-470-bundles/test.bundle"
runuser -u "$p" -- test ! -w "$root/worker/paw-470-bundles/test.bundle"
runuser -u "$p" -- test ! -w "$root/worker/paw-470-bundles"
runuser -u "$p" -- test ! -r "$root/worker/private-key"
echo 'paw_bundle_multi_uid_acl=PASS'
