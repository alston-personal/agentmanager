from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cutover_command_is_exact_and_rollback_required() -> None:
    data = json.loads(
        (ROOT / ".agentos" / "commands" / "oracle-employee-worker-system-boundary-cutover.json")
        .read_text(encoding="utf-8")
    )
    assert data["operation"] == "cutover_employee_worker_to_system_resource_boundary"
    assert data["source_support_commit"] == "3b4705bc05bebebbbb69a3819668ce1d4a4640c0"
    assert data["rollback_on_failure"] is True
    assert data["required_kernel_contract"]["cpu.max"] == "50000 100000"


def test_cutover_proves_kernel_resources_before_marker() -> None:
    text = (
        ROOT
        / ".github"
        / "workflows"
        / "oracle-employee-worker-system-boundary-cutover.yml"
    ).read_text(encoding="utf-8")

    cpu_check = text.index('test "$(cat "$root/cpu.max")" = "50000 100000"')
    marker_write = text.index("support_commit=%s")
    assert cpu_check < marker_write
    assert 'grep -Eq '^default[[:space:]]+20$'' in text
    assert "employee_worker_system_cutover_rollback=START" in text
    assert 'systemctl --user restart "$USER_UNIT"' in text
    assert 'case "$cg" in' in text
    assert "/system.slice/*" in text
    assert "worker_system_cpu_percent_10s=" in text
    assert "employee_worker_system_cutover=PASS" in text
