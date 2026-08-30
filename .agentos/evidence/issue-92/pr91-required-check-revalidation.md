# Issue #92 — PR #91 required-check revalidation

This marker intentionally changes no Vendor runtime or deployment behavior.

Reason: PR #91's last governance checks were created before PR #78 introduced the canonical `guard` producer on the protected target branch. This commit forces a fresh `pull_request synchronize` event after that producer became available, so the repository ruleset can be validated against the actual current workflow set.

Expected required context: `guard`.
