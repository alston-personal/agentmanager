#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

helper = ROOT / "scripts/deploy_dashboard_blue_green_user.sh"
realm_workflow = ROOT / ".github/workflows/oracle-deploy-realm-gateway.yml"
wardrobe_workflow = ROOT / ".github/workflows/oracle-deploy-mio-wardrobe-dashboard.yml"
realm_entry = ROOT / "scripts/deploy_realm_gateway_user.sh"

for p in (helper, realm_workflow, wardrobe_workflow, realm_entry):
    if not p.is_file():
        raise SystemExit(f"dashboard_blue_green_invariant=FAIL missing={p.relative_to(ROOT)}")

h = helper.read_text(encoding="utf-8")
rw = realm_workflow.read_text(encoding="utf-8")
ww = wardrobe_workflow.read_text(encoding="utf-8")
re_entry = realm_entry.read_text(encoding="utf-8")

required_helper = [
    "3040",
    "3041",
    "dashboard_bg_candidate_ready=PASS",
    "dashboard_bg_candidate_identity=PASS",
    "dashboard_bg_nginx_switch=PASS",
    "dashboard_bg_public_verify=PASS",
    "dashboard_bg_old_slot_stopped=PASS",
    "dashboard_bg_post_retire_public_verify=PASS",
    "dashboard_bg_cutover=PASS",
    'systemctl --user stop "$OLD_UNIT"',
    'systemctl --user restart "$OLD_UNIT"',
    'sudo -n systemctl reload nginx',
]
missing = [x for x in required_helper if x not in h]
if missing:
    raise SystemExit(f"dashboard_blue_green_invariant=FAIL helper_missing={missing}")

def pos(token: str) -> int:
    i = h.find(token)
    if i < 0:
        raise SystemExit(f"dashboard_blue_green_invariant=FAIL missing_order_token={token}")
    return i

# Deployment ordering is the core availability invariant.
ordered = [
    "dashboard_bg_candidate_ready=PASS",
    "dashboard_bg_candidate_identity=PASS",
    "dashboard_bg_nginx_switch=PASS",
    "dashboard_bg_public_verify=PASS",
    'systemctl --user stop "$OLD_UNIT"',
    "dashboard_bg_old_slot_stopped=PASS",
    "dashboard_bg_post_retire_public_verify=PASS",
    "dashboard_bg_cutover=PASS",
]
positions = [pos(x) for x in ordered]
if positions != sorted(positions):
    raise SystemExit(f"dashboard_blue_green_invariant=FAIL invalid_cutover_order={list(zip(ordered, positions))}")

# A failed post-retire verification must restore both old process and nginx.
post = h[pos("# Prove the public surface remains healthy with only the new slot serving."):]
for token in [
    'systemctl --user restart "$OLD_UNIT"',
    'cp "$NGINX_SITE.pre-bg-$RUN_ID-$RUN_ATTEMPT" "$NGINX_SITE"',
    'systemctl reload nginx',
]:
    if token not in post:
        raise SystemExit(f"dashboard_blue_green_invariant=FAIL rollback_missing={token}")

# Realm scheduler entry must delegate to the canonical blue/green implementation
# before its legacy migration fallback.
delegate = 'BG_SCRIPT_REL="scripts/deploy_realm_gateway_blue_green_user.sh"'
legacy = 'DASH="$REPO/dashboard"'
if delegate not in re_entry or legacy not in re_entry or re_entry.find(delegate) > re_entry.find(legacy):
    raise SystemExit("dashboard_blue_green_invariant=FAIL realm_entry_not_blue_green_first")

# Production workflows must require the lifecycle proof markers.
for marker in [
    "dashboard_bg_cutover=PASS",
    "dashboard_bg_old_slot_stopped=PASS",
    "dashboard_bg_post_retire_public_verify=PASS",
]:
    if marker not in rw:
        raise SystemExit(f"dashboard_blue_green_invariant=FAIL realm_acceptance_missing={marker}")

if "deploy_dashboard_blue_green_user.sh" not in ww:
    raise SystemExit("dashboard_blue_green_invariant=FAIL wardrobe_not_using_shared_helper")

# Never reintroduce direct single-listener service mutation into production workflows.
bad = re.compile(r"systemctl\s+--user\s+(?:stop|restart)\s+agentos-dashboard\.service")
for workflow in ROOT.glob(".github/workflows/oracle-deploy-*.yml"):
    text = workflow.read_text(encoding="utf-8")
    if bad.search(text):
        raise SystemExit(f"dashboard_blue_green_invariant=FAIL direct_dashboard_service_mutation={workflow.relative_to(ROOT)}")

# GitHub only preserves one pending run per concurrency group. Realm and Wardrobe
# therefore need distinct workflow queues; host-level flock remains the single writer.
def concurrency_group(text: str) -> str:
    m = re.search(r"(?m)^\s*group:\s*([^\n#]+)", text)
    if not m:
        raise SystemExit("dashboard_blue_green_invariant=FAIL missing_concurrency_group")
    return m.group(1).strip()

rg = concurrency_group(rw)
wg = concurrency_group(ww)
if rg == wg:
    raise SystemExit(f"dashboard_blue_green_invariant=FAIL shared_pending_queue={rg}")

print("dashboard_blue_green_invariant=PASS")
print("dashboard_blue_green_candidate_before_switch=PASS")
print("dashboard_blue_green_public_before_retire=PASS")
print("dashboard_blue_green_post_retire_verify=PASS")
print("dashboard_blue_green_rollback_contract=PASS")
print(f"dashboard_blue_green_workflow_queues=PASS realm={rg} wardrobe={wg}")
