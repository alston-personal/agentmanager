#!/usr/bin/env bash
# Fixed #2346 independent suite repository provision. Not the #2297 two-repo action.
set -euo pipefail
test "$(id -un)" = "ubuntu" || { echo "error=executor_owner_mismatch" >&2; exit 2; }
command -v gh >/dev/null
unset GH_TOKEN GITHUB_TOKEN
gh auth status >/dev/null 2>&1 || { echo "error=github_auth_unavailable" >&2; exit 3; }
repo="alston-personal/wow-companion-suite"
if gh repo view "$repo" --json id,nameWithOwner,isPrivate >/dev/null 2>&1; then
  classification="ALREADY_EXISTS_PRIVATE"
else
  # Bootstrap only the named user-approved private repository, with its main branch.
  gh repo create "$repo" --private --add-readme --description "AgentOS governed WoW Companion Suite (#2346)" >/dev/null
  classification="CREATED_PRIVATE"
fi
metadata="$(gh api "repos/$repo" --jq '[.id,.full_name,.private,.default_branch] | @tsv')"
IFS=$'\t' read -r repo_id actual_name is_private default_branch <<< "$metadata"
test "$actual_name" = "$repo" || { echo "error=repo_identity_mismatch" >&2; exit 4; }
test "$is_private" = "true" || { echo "error=repo_not_private" >&2; exit 4; }
test "$default_branch" = "main" || { echo "error=repo_default_branch_not_main" >&2; exit 4; }
[[ "$repo_id" =~ ^[0-9]+$ ]] || { echo "error=repo_id_invalid" >&2; exit 4; }
echo "repo=$repo"
echo "repository_id=$repo_id"
echo "classification=$classification"
echo "private=true"
echo "default_branch=main"
echo "wow_2346_repository_provision=PASS"
