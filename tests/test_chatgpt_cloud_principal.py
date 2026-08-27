import json
import subprocess
import sys

from agent_core.client_auth import ClientTokenStore
from agent_core.distributed_control_plane import DistributedControlPlane


def test_provisioned_chatgpt_principal_is_read_only_and_project_scoped(tmp_path):
    db = tmp_path / "one.sqlite3"
    command = [
        sys.executable,
        "scripts/provision_chatgpt_cloud_principal.py",
        "--db",
        str(db),
        "--principal-id",
        "acct-test",
        "--project",
        "layout-3d",
        "--ttl-days",
        "30",
    ]
    output = subprocess.check_output(command, text=True)
    issued = json.loads(output)

    assert issued["subject"] == "chatgpt:acct-test"
    assert issued["permissions"] == ["project.read", "task.read"]
    assert issued["projects"] == ["layout-3d"]

    principal = ClientTokenStore(DistributedControlPlane(db)).principal(issued["token"])
    assert principal is not None
    assert principal.allows_permission("project.read")
    assert principal.allows_permission("task.read")
    assert not principal.allows_permission("task.submit")
    assert principal.allows_project("layout-3d")
    assert not principal.allows_project("other-project")
