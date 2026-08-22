import subprocess
import sys

from runtime_core.onboarding_v1 import JoinReference


def test_issue_join_reference_cli_emits_decodable_https_link(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/issue_node_join_reference.py",
            "--db",
            str(tmp_path / "enrollment.db"),
            "--realm-id",
            "realm-personal",
            "--core-url",
            "https://core.example.test",
            "--ttl-minutes",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    link = result.stdout.strip()
    reference = JoinReference.decode(link)
    assert reference.core_url == "https://core.example.test"
    assert reference.enrollment_id.startswith("enr_")
