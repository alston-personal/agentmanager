from __future__ import annotations

import json
import os
from pathlib import Path

from agent_core.governance_directory import seed_core
from scripts.agentos_node import harvest, main


def test_harvest_advertises_governance_and_resource_capabilities(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_ROOT", str(tmp_path))
    ids = {item["id"] for item in harvest()["capabilities"]}
    assert "governance.resolve" in ids
    assert "resource.query" in ids
    assert "resource.verify.site" in ids


def test_node_resolves_existing_port_manager(tmp_path: Path, monkeypatch, capsys):
    # Core directory implementation accepts explicit temp paths; CLI acceptance is
    # validated on Oracle where the canonical AGENT_DATA_ROOT exists.
    directory = tmp_path / "governance" / "directory.json"
    seed_core(directory)
    data = json.loads(directory.read_text(encoding="utf-8"))
    assert data["entities"]["manager://port"]["authority"]["exclusive"] is True
    assert "capability://network.port.allocate" in data["entities"]["manager://port"]["owns"]
