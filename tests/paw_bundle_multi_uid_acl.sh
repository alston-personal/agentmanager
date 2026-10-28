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
# Production publication grants read-only access to the exact completed bundle.
# Do not rely on the creator umask or inherited default ACL to authorize the publisher.
setfacl -m "u:$p:r--" "$root/worker/paw-470-bundles/test.bundle"
if ! runuser -u "$p" -- test -r "$root/worker/paw-470-bundles/test.bundle"; then
  echo "paw_publisher_bundle_read_denied" >&2
  namei -l "$root/worker/paw-470-bundles/test.bundle" >&2
  getfacl -p "$root" "$root/worker" "$root/worker/paw-470-bundles" "$root/worker/paw-470-bundles/test.bundle" >&2
  exit 1
fi
runuser -u "$p" -- test ! -w "$root/worker/paw-470-bundles/test.bundle"
runuser -u "$p" -- test ! -w "$root/worker/paw-470-bundles"
runuser -u "$p" -- test ! -r "$root/worker/private-key"
echo 'paw_bundle_multi_uid_acl=PASS'
