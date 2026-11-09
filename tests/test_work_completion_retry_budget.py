import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("work_completion_retry_budget", ROOT / "scripts/work_completion.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_exhausted_verification_remains_blocked_and_idempotent():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "work-items.json"
        mod.register(path, work_id="wi-470", project_id="agentmanager",
                     title="finish runtime", owner="role://completion.controller",
                     next_action="verify receipt", acceptance=["terminal receipt"])
        mod.transition(path, work_id="wi-470", target="blocked",
                       actor="role://lobster", blocker="verification failed")
        state = mod.load(path)
        state["items"]["wi-470"]["machine_retry_count"] = 359
        mod.save(path, state)
        assert mod.defer_machine_blockers(path) == []
        first = mod.load(path)["items"]["wi-470"]
        assert first["status"] == "blocked"
        assert first["machine_retry_count"] == 359
        markers = [h for h in first["history"] if h.get("event") == "machine_retry_budget_exhausted"]
        assert len(markers) == 1
        assert mod.defer_machine_blockers(path) == []
        second = mod.load(path)["items"]["wi-470"]
        assert sum(h.get("event") == "machine_retry_budget_exhausted" for h in second["history"]) == 1
        assert second["owner_generation"] == first["owner_generation"]
