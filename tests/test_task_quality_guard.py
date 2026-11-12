from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agent_core.task_quality import TaskQualityError, parse_task_contract, validate_task_text


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"test_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class TaskQualityGuardTests(unittest.TestCase):
    def test_placeholders_and_missing_contract_are_rejected(self):
        for text in (
            "Define objectives",
            "Break work into milestones",
            "Execute and report progress",
            "[P0] Define objectives | workspace=/repo | acceptance=write a detailed objective record",
            "Implement the endpoint",
            "Implement endpoint | workspace=/repo",
        ):
            with self.subTest(text=text), self.assertRaises(TaskQualityError):
                validate_task_text(text)

    def test_specific_task_is_accepted(self):
        text = (
            "Implement authenticated approval endpoint | workspace=/srv/vendor "
            "| prerequisite=provider resolved | acceptance=pytest -q tests/test_approve.py"
        )
        contract = parse_task_contract(text)
        self.assertEqual(contract.workspace, "/srv/vendor")
        self.assertIn("pytest", contract.acceptance)

    def test_register_project_creates_no_placeholder_tasks(self):
        module = load_script("register_project")
        with tempfile.TemporaryDirectory() as tmp:
            module.DATA_PROJECTS_DIR = Path(tmp) / "projects"
            status = module.ensure_status_file("demo", "Demo", "new", None)
            content = status.read_text(encoding="utf-8")
        self.assertNotIn("Define objectives", content)
        self.assertNotRegex(content, r"(?m)^- \[ \]")

    def test_board_projection_drops_invalid_pending_but_keeps_valid(self):
        module = load_script("sync_task_board")
        valid = "Implement signed receipt | workspace=/repo | acceptance=pytest -q tests/test_receipt.py"
        with tempfile.TemporaryDirectory() as tmp:
            status = Path(tmp) / "STATUS.md"
            status.write_text(
                "## 📅 Todo List\n- [ ] Define objectives\n- [ ] " + valid + "\n",
                encoding="utf-8",
            )
            todos = module.parse_todos(status)
        self.assertEqual(todos, [(" ", valid)])

    def test_lobster_never_selects_invalid_historical_task(self):
        lobster = load_script("lobster")
        valid = "Implement signed receipt | workspace=/repo | acceptance=pytest -q tests/test_receipt.py"
        task = lobster.pick_next_task([
            {"status": "todo", "text": "Define objectives"},
            {"status": "todo", "text": valid},
        ])
        self.assertEqual(task["text"], valid)
        success, reason = lobster.run_with_inspector(Path("/repo"), "Define objectives")
        self.assertFalse(success)
        self.assertIn("task_quality", reason)
        direct_success, direct_reason = lobster.run_claude_task(
            "demo", {"text": "Define objectives"}, dry_run=True
        )
        self.assertFalse(direct_success)
        self.assertIn("task_quality", direct_reason)

    def test_lobster_quota_exhaustion_opens_circuit_without_retrying(self):
        lobster = load_script("lobster")
        task = "Resolve governed provider | workspace=/repo | acceptance=governance receipt names one provider"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            lobster,
            "run_claude_task_wrapper",
            return_value=(False, "EXIT_3: Your AI credits balance is too low; RESOURCE_EXHAUSTED"),
        ) as executor:
            ok, reason = lobster.run_with_inspector(Path(tmp), task)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("QUOTA_EXHAUSTED:"))
        self.assertEqual(executor.call_count, 1)
        self.assertGreater(lobster.QUOTA_COOLDOWN_UNTIL, lobster.time.monotonic() + 1790)

    def test_add_todo_rejects_before_mutating_status(self):
        module = load_script("add_todo")
        with tempfile.TemporaryDirectory() as tmp:
            module.DATA_ROOT = tmp
            status = Path(tmp) / "projects" / "demo" / "STATUS.md"
            status.parent.mkdir(parents=True)
            status.write_text("## 📅 Todo List\n", encoding="utf-8")
            self.assertFalse(module.add_todo("demo", "Define objectives"))
            self.assertEqual(status.read_text(encoding="utf-8"), "## 📅 Todo List\n")

    def test_architect_rejects_entire_invalid_batch(self):
        module = load_script("architect")
        with tempfile.TemporaryDirectory() as tmp:
            module.TASK_BOARD = Path(tmp) / "TASK_BOARD.md"
            original = "### 📦 demo\n"
            module.TASK_BOARD.write_text(original, encoding="utf-8")
            ok = module.append_tasks_to_board("demo", "wish", {"tasks": ["Define objectives"]})
            self.assertFalse(ok)
            self.assertEqual(module.TASK_BOARD.read_text(encoding="utf-8"), original)

    def test_command_center_template_contains_no_placeholder_task(self):
        source = (ROOT / ".agent/skills/command_center_reporter/reporter_client.py").read_text(encoding="utf-8")
        self.assertNotIn("- [ ] Define objectives", source)
        self.assertIn("workspace=<path-or-repo>", source)


if __name__ == "__main__":
    unittest.main()
