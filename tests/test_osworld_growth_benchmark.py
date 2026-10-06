import json
import tempfile
import unittest
from pathlib import Path

from agent_core.osworld_growth_benchmark import (
    build_run_record,
    compare_growth,
    load_release,
    parse_osworld_results,
)


class OSWorldGrowthBenchmarkTests(unittest.TestCase):
    def _release(self):
        return {
            "schema": "agentos.external-benchmark-release/v1",
            "benchmark": "OSWorld-V2",
            "release": "osworld-v2.1",
        }

    def _results(self, scores):
        return {
            "task_count": len(scores),
            "score_sum": sum(scores),
            "mean_score": sum(scores) / len(scores),
            "error_count": 0,
            "rows": [
                {"application": "chrome", "task_id": f"t{i}", "status": "success", "score": s}
                for i, s in enumerate(scores)
            ],
        }

    def _model(self):
        return {"provider": "openai", "name": "gpt-x", "version": "fixed"}

    def _runtime(self):
        return {
            "provider": "docker",
            "image": "pinned",
            "action_space": "pyautogui",
            "observation_type": "screenshot",
            "max_steps": 200,
        }

    def test_parse_official_summary_results_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "results.json"
            p.write_text(json.dumps([
                {"application": "chrome", "task_id": "a", "status": "success", "score": 1.0},
                {"application": "writer", "task_id": "b", "status": "success", "score": 0.0},
            ]))
            result = parse_osworld_results(p)
        self.assertEqual(result["task_count"], 2)
        self.assertEqual(result["mean_score"], 0.5)

    def test_experienced_requires_snapshot_and_no_heldout_leakage(self):
        with self.assertRaises(ValueError):
            build_run_record(
                release=self._release(),
                arm="experienced",
                results=self._results([1.0]),
                model=self._model(),
                runtime=self._runtime(),
                cognitive_snapshot={"experience_enabled": True, "snapshot_sha256": "abc"},
                contamination={"heldout_answers_seen": True},
            )

    def test_cold_rejects_enabled_experience(self):
        with self.assertRaises(ValueError):
            build_run_record(
                release=self._release(),
                arm="cold",
                results=self._results([0.0]),
                model=self._model(),
                runtime=self._runtime(),
                cognitive_snapshot={"experience_enabled": True},
            )

    def test_compare_detects_growth_uplift(self):
        cold = build_run_record(
            release=self._release(),
            arm="cold",
            results=self._results([0.0, 1.0]),
            model=self._model(),
            runtime=self._runtime(),
            cognitive_snapshot={"experience_enabled": False, "snapshot_sha256": "cold"},
        )
        experienced = build_run_record(
            release=self._release(),
            arm="experienced",
            results=self._results([1.0, 1.0]),
            model=self._model(),
            runtime=self._runtime(),
            cognitive_snapshot={"experience_enabled": True, "snapshot_sha256": "age100"},
            contamination={"heldout_answers_seen": False},
        )
        comparison = compare_growth(cold=cold, experienced=experienced)
        self.assertEqual(comparison["verdict"], "G3_CANDIDATE")
        self.assertEqual(comparison["metrics"]["growth_uplift_absolute"], 0.5)
        self.assertEqual(comparison["metrics"]["improved_tasks"], 1)
        self.assertEqual(comparison["metrics"]["regressed_tasks"], 0)

    def test_compare_rejects_model_change(self):
        cold = build_run_record(
            release=self._release(),
            arm="cold",
            results=self._results([0.0]),
            model=self._model(),
            runtime=self._runtime(),
            cognitive_snapshot={"experience_enabled": False},
        )
        model2 = self._model()
        model2["version"] = "stronger"
        experienced = build_run_record(
            release=self._release(),
            arm="experienced",
            results=self._results([1.0]),
            model=model2,
            runtime=self._runtime(),
            cognitive_snapshot={"experience_enabled": True, "snapshot_sha256": "age100"},
            contamination={"heldout_answers_seen": False},
        )
        with self.assertRaisesRegex(ValueError, "model.version"):
            compare_growth(cold=cold, experienced=experienced)


if __name__ == "__main__":
    unittest.main()
