from pathlib import Path

LEGACY = Path(".agentos/governance/legacy-direct-oracle-workflows.txt")
WORKFLOWS = Path(".github/workflows")
GATEWAY_WORKFLOW = Path(".github/workflows/oracle-deploy-realm-gateway.yml")
GATEWAY_SCRIPT = Path("scripts/deploy_realm_gateway_user.sh")
DISPATCH_CLIENT = Path("scripts/agentos_dispatch.sh")


def main() -> int:
    legacy = {
        line.strip()
        for line in LEGACY.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    violations = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        rel = str(path)
        if rel in legacy:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "submit_agentos_scheduler_request_https.sh" in text:
            violations.append((rel, "internal_scheduler_client"))
        if "agentos-oracle-hosted-ingress" in text:
            violations.append((rel, "legacy_oracle_ingress_concurrency"))
    dispatch_client = DISPATCH_CLIENT.read_text(encoding="utf-8", errors="replace")
    inspect_retry_required = {
        "inspect_retry_scope": 'if [ "$CAPABILITY" = "agentos.executor" ] && [ "$OPERATION" = "job.inspect" ]' in dispatch_client,
        "inspect_retry_bound": "submit_attempts=4" in dispatch_client,
        "transient_codes": "429|502|503|504" in dispatch_client,
        "generic_submit_default_single_shot": "submit_attempts=1" in dispatch_client,
    }
    for name, ok in inspect_retry_required.items():
        if not ok:
            violations.append((str(DISPATCH_CLIENT), name))

    gateway_workflow = GATEWAY_WORKFLOW.read_text(encoding="utf-8", errors="replace")
    gateway_script = GATEWAY_SCRIPT.read_text(encoding="utf-8", errors="replace")
    gateway_required = {
        "workflow_dispatch_route": "/dashboard/api/agentos/v1/dispatch" in gateway_workflow,
        "workflow_public_dispatch": "public_dispatch_routing=PASS" in gateway_workflow,
        "script_local_dispatch": "realm_gateway_dispatch_local=PASS" in gateway_script,
        "script_public_dispatch": "realm_gateway_dispatch_public=PASS" in gateway_script,
        "script_route_guard": "'/v1/dispatch'" in gateway_script,
    }
    for name, ok in gateway_required.items():
        if not ok:
            violations.append((str(GATEWAY_WORKFLOW if name.startswith("workflow") else GATEWAY_SCRIPT), name))

    if violations:
        print("runner_window_boundary=FAIL")
        for path, reason in violations:
            print(f"violation={path}:{reason}")
        return 2
    print("runner_window_boundary=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
