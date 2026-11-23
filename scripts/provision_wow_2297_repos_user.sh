#!/usr/bin/env bash
# Fixed, approved #2297 private repo provisioning via the existing ubuntu Bootstrap owner.
set -euo pipefail

test "$(id -un)" = "ubuntu" || { echo "error=executor_owner_mismatch" >&2; exit 2; }
command -v gh >/dev/null
# Do not let an Actions-scoped token override the existing ubuntu gh identity.
unset GH_TOKEN GITHUB_TOKEN
gh auth status >/dev/null 2>&1 || { echo "error=github_auth_unavailable" >&2; exit 3; }

# Names and owner are compile-time constants. Never take repository names from requests.
for name in wow-agentos-addon wow-nav-assist; do
  repo="alston-personal/$name"
  if gh repo view "$repo" --json id,nameWithOwner,isPrivate >/dev/null 2>&1; then
    classification="ALREADY_EXISTS_PRIVATE"
  else
    # A missing repo and a permission-denied repo can look identical.
    # Creation is bounded to the two named, user-approved private repositories.
    gh repo create "$repo" --private --description "AgentOS governed World of Warcraft addon project (#2297)" >/dev/null
    classification="CREATED_PRIVATE"
  fi

  # Independent remote readback, never infer success from gh repo create exit 0 alone.
  metadata="$(gh api "repos/$repo" --jq '[.id,.full_name,.private] | @tsv')"
  IFS=$'\t' read -r repo_id actual_name is_private <<< "$metadata"
  test "$actual_name" = "$repo" || { echo "error=repo_identity_mismatch" >&2; exit 4; }
  test "$is_private" = "true" || { echo "error=repo_not_private" >&2; exit 4; }
  [[ "$repo_id" =~ ^[0-9]+$ ]] || { echo "error=repo_id_invalid" >&2; exit 4; }
  echo "repo=$repo"
  echo "repository_id=$repo_id"
  echo "classification=$classification"
  echo "private=true"
done

echo "wow_2297_repository_provision=PASS"
