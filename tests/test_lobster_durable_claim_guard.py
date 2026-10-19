"""Keep durable Lobster work fenced before executor invocation."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "lobster.py"


def test_durable_work_execution_is_claim_gated():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    begin = ast.unparse(functions["completion_begin"])
    main = ast.unparse(functions["main"])
    assert "work_item_not_owned_by_lobster" in begin
    assert "work_item_already_in_progress" in begin
    assert "work_item_not_runnable" in begin
    assert "work_item_not_found" in begin
    claim = main.index("work_id = completion_begin(task['text'])")
    guard = main.index("if durable_id and work_id != durable_id:")
    executor = main.index("run_with_inspector(")
    assert claim < guard < executor
    assert "if '[WI:' in task['text']" in main


def test_completion_begin_behavioral_claim_fencing():
    """Execute the real extracted function against deterministic Ledger doubles."""
    from unittest.mock import Mock
    from typing import Optional
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "completion_begin")
    code = compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec")
    item = {"owner": "role://lobster", "status": "accepted", "next_action": "safe inspect"}
    api = Mock()
    api.item_id_from_task.return_value = "a"
    api.load.return_value = {"items": {"a": item}}
    api.transition.return_value = {"status": "in_progress"}
    ns = {"WorkCompletion": api, "COMPLETION_STATE": Path("/tmp/test-only-work-items.json"),
          "logger": Mock(), "Optional": Optional}
    exec(code, ns)
    begin = ns["completion_begin"]

    assert begin("[WI:a] safe inspect") == "a"
    assert api.transition.call_count == 1

    for status, owner in [
        ("in_progress", "role://lobster"),
        ("blocked", "role://lobster"),
        ("accepted", "role://foreign"),
    ]:
        api.transition.reset_mock()
        item.update(status=status, owner=owner)
        assert begin("[WI:a] safe inspect") is None
        api.transition.assert_not_called()

    api.load.return_value = {"items": {}}
    assert begin("[WI:a] missing") is None
    api.transition.assert_not_called()


def test_real_ledger_claim_is_single_winner_and_owner_fenced():
    """Two competing claim attempts must not both transition accepted -> running."""
    import importlib.util
    import sys
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    spec = importlib.util.spec_from_file_location("work_completion_guard_test", ROOT / "scripts" / "work_completion.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "items.json"
        module.register(ledger, work_id="race", project_id="test", title="Claim race",
                        owner="role://lobster", next_action="read-only probe",
                        acceptance=["one winner"])
        start = Barrier(2)
        def attempt():
            start.wait()
            try:
                module.transition(ledger, work_id="race", target="in_progress",
                                  actor="role://lobster", expected_owner="role://lobster")
                return "won"
            except ValueError:
                return "lost"
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            results = [f.result(timeout=10) for f in futures]
        assert sorted(results) == ["lost", "won"]
        assert module.load(ledger)["items"]["race"]["status"] == "in_progress"

        # Simulate an existing owner handoff before an attempted stale claim.
        ledger2 = Path(td) / "foreign.json"
        module.register(ledger2, work_id="foreign", project_id="test", title="Foreign",
                        owner="role://another", next_action="read-only probe",
                        acceptance=["fenced"])
        import pytest
        with pytest.raises(PermissionError, match="work_item_owner_changed"):
            module.transition(ledger2, work_id="foreign", target="in_progress",
                              actor="role://lobster", expected_owner="role://lobster")
        assert module.load(ledger2)["items"]["foreign"]["status"] == "accepted"


def test_separate_processes_only_one_claims_work_item():
    """fcntl must fence across OS processes, not only threads."""
    import subprocess
    import sys
    import tempfile
    import json
    from pathlib import Path

    script = ROOT / "scripts" / "work_completion.py"
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "items.json"
        import importlib.util
        spec = importlib.util.spec_from_file_location("work_completion_process_test", script)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.register(ledger, work_id="multiproc", project_id="test", title="Race",
                        owner="role://lobster", next_action="read-only probe",
                        acceptance=["exactly one winner"])
        start = Path(td) / "start"
        worker = """
import importlib.util, pathlib, sys, time
spec = importlib.util.spec_from_file_location('wc_child', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
while not pathlib.Path(sys.argv[3]).exists():
    time.sleep(.005)
try:
    mod.transition(pathlib.Path(sys.argv[2]), work_id='multiproc',
                   target='in_progress', actor='role://lobster',
                   expected_owner='role://lobster')
    print('WON')
except ValueError:
    print('LOST')
"""
        processes = [
            subprocess.Popen([sys.executable, "-c", worker, str(script), str(ledger), str(start)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        try:
            start.touch()
            results = [p.communicate(timeout=10) for p in processes]
            assert sorted(s.strip() for s, _ in results) == ["LOST", "WON"], results
            assert all(p.returncode == 0 for p in processes), results
            assert module.load(ledger)["items"]["multiproc"]["status"] == "in_progress"
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.wait()


def test_expired_lease_reclaim_persists_and_fences_old_executor():
    """A crashed owner is reclaimed durably; stale owner cannot claim again."""
    import importlib.util
    import sys
    import tempfile
    import pytest
    spec = importlib.util.spec_from_file_location("wc_recovery_test", ROOT / "scripts" / "work_completion.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "items.json"
        module.register(path, work_id="recover", project_id="test", title="Recovery",
                        owner="role://lobster", next_action="safe inspect", acceptance=["reclaimed"])
        module.transition(path, work_id="recover", target="in_progress", actor="role://lobster",
                          expected_owner="role://lobster")
        with module.locked(path):
            state = module.load(path)
            state["items"]["recover"]["lease_expires_at"] = "2020-01-01T00:00:00+00:00"
            module.save(path, state)
        assert module.reclaim_stale(path) == ["recover"]
        item = module.load(path)["items"]["recover"]
        assert item["owner"] == "role://completion.controller"
        assert item["owner_generation"] == 2
        assert item["status"] == "in_progress"
        assert item["history"][-1]["event"] == "stale_reclaim"
        with pytest.raises(PermissionError, match="work_item_owner_changed"):
            module.transition(path, work_id="recover", target="in_progress",
                              actor="role://lobster", expected_owner="role://lobster")
        assert module.reclaim_stale(path) == []


def test_fallback_status_file_path_also_claim_gated():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    fallback = ast.unparse(functions["process_project"])
    assert "if '[WI:' in task['text']" in fallback
    claim = fallback.index("work_id = completion_begin(task['text'])")
    guard = fallback.index("if durable_id and work_id != durable_id:")
    execute = fallback.index("run_with_inspector(")
    assert claim < guard < execute


def test_uncertain_reclaimed_work_never_becomes_auto_runnable():
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("wc_disposition_test", ROOT / "scripts" / "work_completion.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    item = {"status": "in_progress", "history": [
        {"event": "registered"}, {"event": "stale_reclaim"}]}
    assert module.recovery_disposition(item) == "needs_receipt_reconciliation"
    item["status"] = "verifying"
    assert module.recovery_disposition(item) == "needs_receipt_reconciliation"
    item["status"] = "accepted"
    assert module.recovery_disposition(item) == "eligible_for_governed_dispatch"
    item["status"] = "blocked"
    assert module.recovery_disposition(item) == "blocked"


def test_next_item_skips_uncertain_reclaimed_work_without_starving_safe_candidate():
    import importlib.util
    import sys
    import tempfile
    spec = importlib.util.spec_from_file_location("wc_select_recovery_test", ROOT / "scripts" / "work_completion.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.json"
        for wid in ("uncertain", "safe"):
            module.register(path, work_id=wid, project_id="test", title=wid,
                            owner="role://completion.controller", next_action="inspect",
                            acceptance=["no duplicate side effect"])
        with module.locked(path):
            state = module.load(path)
            item = state["items"]["uncertain"]
            item["status"] = "in_progress"
            item["history"].append({"event": "stale_reclaim"})
            module.save(path, state)
        assert module.next_item(path)["work_id"] == "safe"
        with module.locked(path):
            state = module.load(path)
            state["items"]["safe"]["status"] = "done"
            state["items"]["safe"]["evidence"] = ["verified"]
            state["items"]["safe"]["verification"] = {"status": "passed"}
            module.save(path, state)
        assert module.next_item(path) is None
