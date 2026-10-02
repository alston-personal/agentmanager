from pathlib import Path

LEGACY = Path(".agentos/governance/legacy-direct-oracle-workflows.txt")
WORKFLOWS = Path(".github/workflows")


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
    if violations:
        print("runner_window_boundary=FAIL")
        for path, reason in violations:
            print(f"violation={path}:{reason}")
        return 2
    print("runner_window_boundary=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
