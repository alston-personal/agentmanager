import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService


def _run_cli(args: list[str], *, env: dict[str, str], cwd: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "agentos_node.ide_cli", *args],
        cwd=str(cwd),
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_ide_cli_submit_status_and_continue_share_control_plane_state(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "ide-cli.sqlite3")
    server = DistributedGatewayServer(
        ("127.0.0.1", 0),
        DistributedGatewayService(store),
        token="test-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        host, port = server.server_address
        gateway = f"http://{host}:{port}"
        env = dict(os.environ)
        env["AGENTOS_CONTROL_PLANE_TOKEN"] = "test-token"

        submitted = _run_cli(
            [
                "--gateway",
                gateway,
                "ask",
                "continue this project from any IDE",
                "--project",
                "shared-project",
                "--workspace",
                str(workspace),
                "--capability",
                "agent.reason",
            ],
            env=env,
            cwd=workspace,
        )
        task_id = submitted["task"]["taskId"]

        status = _run_cli(
            ["--gateway", gateway, "status", "--project", "shared-project", "--workspace", str(workspace)],
            env=env,
            cwd=workspace,
        )
        assert status["project"]["latestTask"]["taskId"] == task_id
        assert status["project"]["recommendedAction"] == "wait"

        continued = _run_cli(
            ["--gateway", gateway, "continue", "--project", "shared-project", "--workspace", str(workspace)],
            env=env,
            cwd=workspace,
        )
        assert continued["status"] == "already_in_progress"
        assert continued["task"]["taskId"] == task_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_ide_cli_init_needs_no_gateway(tmp_path: Path):
    workspace = tmp_path / "renamed-clone"
    workspace.mkdir()
    env = dict(os.environ)
    env.pop("AGENTOS_CONTROL_PLANE_URL", None)
    env.pop("AGENTOS_CONTROL_PLANE_TOKEN", None)

    initialized = _run_cli(
        ["init", "agentmanager", "--workspace", str(workspace)],
        env=env,
        cwd=workspace,
    )
    assert initialized["projectId"] == "agentmanager"
    marker = json.loads((workspace / ".agentos" / "project.json").read_text(encoding="utf-8"))
    assert marker["project_id"] == "agentmanager"
