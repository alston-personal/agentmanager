from datetime import datetime, timezone
import json
from pathlib import Path

from agent_core.context_compiler import compile_execution_context


def test_executor_working_set_preserves_semantics_without_heavy_runtime_state(tmp_path: Path, monkeypatch):
    context_doc = tmp_path / "development-context.json"
    context_doc.write_text(
        json.dumps(
            {
                "updated_at": "2026-08-27T11:20:00+08:00",
                "integration_branch": "feature/distributed-agentos-runtime",
                "write_policy": {
                    "experimental_writes_to_main": "deny",
                    "branch_required_for_writes": True,
                },
                "active_work": {
                    "goal": "Keep the Master Experience Floor system-owned.",
                    "current_findings": ["Native execution is proven.", "Weak executors need bounded context."],
                    "next_actions": ["Run the weak-executor proof."],
                },
            }
        ),
        encoding="utf-8",
    )
    registry = tmp_path / "contexts.json"
    registry.write_text(json.dumps({"demo": str(context_doc)}), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_CONTEXTS_FILE", str(registry))

    state = {
        "recommendedAction": "continue",
        "latestTask": {"taskId": "task_heavy", "result": {"blob": "x" * 10000}},
        "currentIR": {"goal": "runtime fallback", "payload": {"blob": "y" * 10000}},
        "continuation": {"blob": "z" * 10000},
    }
    context = compile_execution_context(
        "demo",
        state,
        now=datetime(2026, 8, 27, 3, 30, tzinfo=timezone.utc),
    )
    working = context["working_set"]

    assert working["schema"] == "agentos.executor-working-set/v0.1"
    assert working["active_goal"] == context["active_goal"]
    assert working["next_action"] == context["next_action"]
    assert working["current_findings"] == context["current_findings"]
    assert working["next_actions"] == context["next_actions"]
    assert working["write_policy"] == context["write_policy"]
    assert working["integration_branch"] == context["integration_branch"]
    assert working["context_freshness"] == context["context_freshness"]
    assert "latest_task" not in working
    assert "current_ir" not in working
    assert "continuation" not in working
    assert len(json.dumps(working)) < len(json.dumps(context)) / 5
