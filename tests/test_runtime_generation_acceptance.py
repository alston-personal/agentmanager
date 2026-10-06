from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"accept_runtime_generation_user.py"

def test_runtime_generation_acceptance_requires_all_three(monkeypatch,tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location("runtime_accept",SCRIPT)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    sha="a"*40
    monkeypatch.setattr(m,"core_commit",lambda:sha)
    monkeypatch.setattr(m,"action_commit",lambda:sha)
    monkeypatch.setattr(m,"realm_commit",lambda:sha)
    monkeypatch.setattr(sys,"argv",["accept","--expected",sha])
    import pytest
    with pytest.raises(SystemExit) as e: m.main()
    assert e.value.code==0

def test_runtime_generation_acceptance_fails_on_split_generation(monkeypatch):
    import importlib.util, pytest
    spec=importlib.util.spec_from_file_location("runtime_accept",SCRIPT)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    sha="a"*40
    monkeypatch.setattr(m,"core_commit",lambda:sha)
    monkeypatch.setattr(m,"action_commit",lambda:"b"*40)
    monkeypatch.setattr(m,"realm_commit",lambda:sha)
    monkeypatch.setattr(sys,"argv",["accept","--expected",sha])
    with pytest.raises(SystemExit) as e: m.main()
    assert e.value.code==10
