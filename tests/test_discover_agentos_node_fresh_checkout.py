from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_discover_agentos_node_runs_without_editable_install_or_pythonpath(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "discover_agentos_node.py"
    output = tmp_path / "capabilities.json"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--node-id",
            "fresh-checkout-node",
            "--realm-id",
            "test-realm",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["identity"]["node_id"] == "fresh-checkout-node"
    assert payload["metadata"]["authorization_inferred"] is False
    assert payload["manifest_id"].startswith("ncap_")
