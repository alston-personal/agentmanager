from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.governance_directory import GovernanceEntity, get, register, resolve, seed_core


def test_port_manager_is_exclusive_owner(tmp_path: Path):
    path = tmp_path / "directory.json"
    seed_core(path)
    owners = resolve("capability://network.port.allocate", path)
    assert owners
    assert owners[0]["id"] == "manager://port"
    assert owners[0]["authority"]["exclusive"] is True


def test_exclusive_duplicate_owner_is_rejected(tmp_path: Path):
    path = tmp_path / "directory.json"
    seed_core(path)
    duplicate = GovernanceEntity(
        id="manager://rogue-port-manager",
        kind="manager",
        name="Rogue Port Manager",
        owns=["capability://network.port.allocate"],
        provides=["capability://network.port.allocate"],
        implementation={},
        authority={"exclusive": True},
        state="implemented",
    )
    with pytest.raises(ValueError, match="exclusive ownership conflict"):
        register(duplicate, path=path)


def test_roles_are_mirrored_from_versioned_role_registry(tmp_path: Path):
    path = tmp_path / "directory.json"
    seed_core(path)
    steward = get("role://governance.spec_steward", path)
    assert steward is not None
    assert steward["authority"]["canonical_role_contract"] is True
    assert steward["metadata"]["role_set_version"]
    assert steward["implementation"]["canonical_registry"] == ".agent/roles/registry.yaml"


def test_stale_legacy_role_is_not_resolved(tmp_path: Path):
    path = tmp_path / "directory.json"
    seed_core(path)
    stale = get("role://instance.agentmanager_paw", path)
    assert stale is not None
    assert stale["state"] == "stale"
