from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_system_worker_unit_has_kernel_resource_boundary() -> None:
    text = (
        ROOT / ".agent" / "scripts" / "agentos-employee-worker-host-system.service"
    ).read_text(encoding="utf-8")

    required = (
        "User=ubuntu",
        "Group=ubuntu",
        "SupplementaryGroups=agentos",
        "WorkingDirectory=/home/ubuntu/agent-data/runtime/core/current",
        "ExecStart=/usr/bin/python3 -m agentos_node.employee_worker_host_daemon",
        "CPUQuota=50%",
        "CPUWeight=20",
        "IOWeight=20",
        "MemoryMax=1G",
        "NoNewPrivileges=true",
        "PrivateNetwork=true",
        "ProtectSystem=strict",
        "ProtectHome=read-only",
    )
    for item in required:
        assert item in text


def test_immutable_convergence_supports_single_system_owner() -> None:
    text = (
        ROOT
        / ".github"
        / "workflows"
        / "oracle-core-bundle-immutable-runtime-convergence.yml"
    ).read_text(encoding="utf-8")

    assert "employee-worker-host-system-boundary" in text
    assert "agentos-employee-worker-host-system.service" in text
    assert "core_bundle_worker_owner=system" in text
    assert "core_bundle_worker_kernel_resource_boundary=PASS" in text
    assert 'test "$(cat "$worker_root/cpu.max")" = "50000 100000"' in text
    assert 'case "$worker_cg" in /system.slice/*)' in text


def test_user_installer_never_starts_second_worker_under_system_marker() -> None:
    text = (ROOT / "scripts" / "install_systemd_user.sh").read_text(encoding="utf-8")
    assert "EMPLOYEE_WORKER_SYSTEM_BOUNDARY_MARKER" in text
    assert "Employee Worker Host owner: system boundary marker present" in text
