from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentos_node.antigravity_one_hook import build_injection, _safe_failure_code
from agentos_node.one_mcp import OneGatewayError


class FakeGateway:
    def __init__(self, *, index_id="idx-7", ir_id="ir-core-152"):
        self.resolved = []
        self.index_id = index_id
        self.ir_id = ir_id

    def status(self):
        return {
            "schema": "agentos.one-mcp-status/v0.1",
            "connected": True,
            "realm_id": "realm-test",
            "node_id": "oracle-core-node",
        }

    def resolve(self, project):
        self.resolved.append(project)
        return {
            "schema": "agentos.resolve/v1",
            "project": {"id": "agentos-core", "name": "AgentOS Core"},
            "mutation_allowed": False,
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": self.index_id,
                "active_goal": "Complete #152 Antigravity IR hydration",
                "execution_head": {"status": "in_progress"},
            },
            "continuation": {
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": self.index_id,
                    "ir_id": self.ir_id,
                    "parent_ir_id": "ir-core-151",
                    "goal": "Complete #152 Antigravity IR hydration",
                    "constraints": ["Workspace is not continuation authority"],
                    "decisions": ["Canonical IR is the durable continuation state"],
                    "pending_tasks": ["Run fresh Codex regression"],
                    "continuation": {"recommended_action": "Run fresh Codex regression"},
                    "capability": "agentos.one.resolve",
                }
            },
            "next_action": "Run fresh Codex regression",
            "provenance": {"continuation": "project/continuity/latest.json"},
        }


def selector(index_id="idx-7", ir_id="ir-core-152"):
    return {
        "schema": "agentos.active-continuation/v1",
        "project_id": "agentos-core",
        "index_id": index_id,
        "ir_id": ir_id,
    }


def envelope_from(output):
    message = output["injectSteps"][0]["ephemeralMessage"]
    return json.loads(message.split("\n", 1)[1])


class AntigravityOneHookTests(unittest.TestCase):
    def test_malformed_usage_does_not_break_existing_hydration(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "EPHEMERAL_MESSAGE", "content": "ONE_PREINVOCATION_IR"}),
                json.dumps({"type": "PLANNER_RESPONSE", "input_tokens": "unknown"}),
            ]))
            gateway = FakeGateway()
            self.assertEqual(build_injection({"invocationNum": 0, "transcriptPath": str(transcript)},
                                             gateway, selector=selector()), {})
            self.assertEqual(gateway.resolved, [])

    def test_first_invocation_hydrates_active_canonical_ir(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": [
                    "/home/ubuntu/zeus-writer",
                    "/home/ubuntu/agentmanager",
                    "/home/ubuntu/privacy-guard",
                ],
                "modelName": "gemini-test",
            },
            gateway,
            selector=selector(),
        )
        self.assertIn("injectSteps", output)
        message = output["injectSteps"][0]["ephemeralMessage"]
        self.assertIn("ONE_PREINVOCATION_IR", message)
        self.assertIn("ONE_ACTIVE_CONTINUATION", message)
        self.assertIn("ir-core-152", message)
        self.assertIn("idx-7", message)
        self.assertNotIn("zeus-writer", message)
        self.assertNotIn("privacy-guard", message)
        self.assertNotIn("token", message.casefold())
        self.assertEqual(gateway.resolved, ["agentos-core"])
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-gemini")
        self.assertTrue(envelope["executor_identity_bound"])
        self.assertEqual(envelope["selection_source"], "ONE_ACTIVE_CONTINUATION")

    def test_acas_workspace_cannot_override_active_core_ir(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/acas"],
                "modelName": "gpt-5-codex",
            },
            gateway,
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["canonical_ir"]["project_id"], "agentos-core")
        self.assertEqual(envelope["executor_class"], "antigravity-codex")
        self.assertEqual(gateway.resolved, ["agentos-core"])
        self.assertNotIn("/home/ubuntu/acas", json.dumps(envelope))

    def test_nested_workspace_cannot_override_active_core_ir(self):
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/agentmanager/workspace/if-tv-station"],
                "modelName": "gpt-5-codex",
            },
            FakeGateway(),
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["canonical_ir"]["project_id"], "agentos-core")
        self.assertNotIn("if-tv-station", json.dumps(envelope))

    def test_empty_workspace_still_hydrates_active_ir(self):
        output = build_injection(
            {"invocationNum": 0, "workspacePaths": [], "modelName": "gpt-5-codex"},
            FakeGateway(),
            selector=selector(),
        )
        self.assertEqual(envelope_from(output)["canonical_ir"]["project_id"], "agentos-core")

    def test_codex_model_binds_codex_executor(self):
        output = build_injection(
            {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"], "modelName": "gpt-5-codex"},
            FakeGateway(),
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-codex")
        self.assertTrue(envelope["executor_identity_bound"])
        self.assertEqual(envelope["model_name"], "gpt-5-codex")

    def test_unknown_model_does_not_guess_executor_identity(self):
        output = build_injection(
            {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"], "modelName": "mystery-model"},
            FakeGateway(),
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-unknown")
        self.assertFalse(envelope["executor_identity_bound"])

    def test_later_invocation_is_silent(self):
        gateway = FakeGateway()
        output = build_injection(
            {"invocationNum": 1, "workspacePaths": ["/home/ubuntu/acas"]},
            gateway,
            selector=selector(),
        )
        self.assertEqual(output, {})
        self.assertEqual(gateway.resolved, [])

    def test_stale_active_selector_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "active continuation selector is stale"):
            build_injection(
                {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"]},
                FakeGateway(),
                selector=selector(index_id="idx-stale"),
            )

    def test_index_generation_mismatch_fails_closed(self):
        class MismatchGateway(FakeGateway):
            def resolve(self, project):
                result = super().resolve(project)
                result["continuation"]["canonical_ir"]["index_id"] = "idx-other"
                return result

        with self.assertRaisesRegex(ValueError, "index generation mismatch"):
            build_injection(
                {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"]},
                MismatchGateway(),
                selector=selector(),
            )

    def test_failure_codes_do_not_echo_exception_details(self):
        secret_error = RuntimeError("Bearer TOPSECRET /home/private/session")
        code = _safe_failure_code(secret_error)
        self.assertEqual(code, "one_hydration_runtime_failed")
        self.assertNotIn("TOPSECRET", code)
        self.assertNotIn("/home/private", code)

        one_error = OneGatewayError("one_http_503")
        self.assertEqual(_safe_failure_code(one_error), "one_http_503")

    def test_already_hydrated_transcript_does_not_reinject_on_next_user_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "USER_INPUT", "content": "hi"}),
                        json.dumps(
                            {
                                "type": "EPHEMERAL_MESSAGE",
                                "content": "AgentOS ONE canonical IR hydration... ONE_PREINVOCATION_IR",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "PLANNER_RESPONSE",
                                "input_tokens": 2000,
                                "cache_read_tokens": 12000,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            gateway = FakeGateway()
            output = build_injection(
                {
                    "invocationNum": 0,
                    "initialNumSteps": 5,
                    "transcriptPath": str(transcript),
                    "modelName": "gemini-test",
                },
                gateway,
                selector=selector(),
            )
            self.assertEqual(output, {})
            self.assertEqual(gateway.resolved, [])

    def test_checkpoint_after_hydration_rehydrates_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "EPHEMERAL_MESSAGE",
                                "content": "AgentOS ONE canonical IR hydration... ONE_PREINVOCATION_IR",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "PLANNER_RESPONSE",
                                "input_tokens": 5000,
                                "cache_read_tokens": 85000,
                            }
                        ),
                        json.dumps({"type": "CHECKPOINT", "content": "compacted"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            gateway = FakeGateway()
            output = build_injection(
                {
                    "invocationNum": 0,
                    "initialNumSteps": 12,
                    "transcriptPath": str(transcript),
                    "modelName": "gemini-test",
                },
                gateway,
                selector=selector(),
            )
            self.assertIn("injectSteps", output)
            self.assertEqual(len(output["injectSteps"]), 1)
            self.assertIn("ONE_PREINVOCATION_IR", output["injectSteps"][0]["ephemeralMessage"])
            self.assertEqual(gateway.resolved, ["agentos-core"])

    def test_context_budget_gatekeeper_yellow_and_red_zones(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "EPHEMERAL_MESSAGE",
                                "content": "AgentOS ONE canonical IR hydration... ONE_PREINVOCATION_IR",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "PLANNER_RESPONSE",
                                "model_usage": {
                                    "input_tokens": 4500,
                                    "cache_read_tokens": 62000,
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            gateway = FakeGateway()
            yellow_out = build_injection(
                {
                    "invocationNum": 0,
                    "initialNumSteps": 10,
                    "transcriptPath": str(transcript),
                    "modelName": "gemini-test",
                },
                gateway,
                selector=selector(),
            )
            self.assertEqual(gateway.resolved, [])
            self.assertEqual(len(yellow_out["injectSteps"]), 1)
            sys_msg = yellow_out["injectSteps"][0]["systemMessage"]
            self.assertIn("CONTEXT_BUDGET_GUARD", sys_msg["systemMessage"])
            self.assertIn("66500", sys_msg["systemMessage"])
            self.assertIn("66,500 tokens", sys_msg["metadata"]["user_markdown"])
            self.assertIn("/compact", sys_msg["metadata"]["user_markdown"])

            # Red zone (>= 100,000 tokens)
            with transcript.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "type": "PLANNER_RESPONSE",
                            "input_tokens": 6000,
                            "cache_read_tokens": 105000,
                        }
                    )
                    + "\n"
                )
            red_out = build_injection(
                {
                    "invocationNum": 0,
                    "initialNumSteps": 14,
                    "transcriptPath": str(transcript),
                    "modelName": "gemini-test",
                },
                gateway,
                selector=selector(),
            )
            red_msg = red_out["injectSteps"][0]["systemMessage"]
            self.assertIn("CRITICAL", red_msg["systemMessage"])
            self.assertIn("111,000 tokens", red_msg["metadata"]["user_markdown"])

    def _seed_temp_data_root(self, root: Path) -> None:
        from agent_core.active_continuation import activate_continuation
        from agent_core.project_continuation_index import publish_project_continuation
        from unittest.mock import patch

        (root / "projects" / "agentos-core").mkdir(parents=True, exist_ok=True)
        (root / "runtime").mkdir(parents=True, exist_ok=True)
        project = {
            "id": "agentos-core",
            "identity_source": "governance-directory",
            "governance_entity_id": "project://agentos-core",
            "integrity": {"mutation_allowed": True},
        }
        initial_params = {
            "project_id": "agentos-core",
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": "idx-seed-1",
                "active_goal": "Cross-surface real-time canonical IR continuity",
                "execution_head": {"status": "in_progress"},
            },
            "continuation": {
                "protocol": "ANCP/1.0",
                "index_id": "idx-seed-1",
                "recommended_action": "Verify Stop hook auto-sync",
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": "idx-seed-1",
                    "ir_id": "ir-seed-1",
                    "parent_ir_id": None,
                    "goal": "Cross-surface real-time canonical IR continuity",
                    "constraints": ["Preserve Logic/Data separation"],
                    "decisions": ["Initial seed decision"],
                    "pending_tasks": ["Verify Stop hook and Codex projection"],
                    "evidence": [],
                    "continuation": {
                        "recommended_action": "Verify Stop hook auto-sync",
                        "next_action": "Verify Stop hook auto-sync",
                    },
                    "capability": "agentos.one.resolve",
                },
            },
        }
        with patch(
            "agent_core.project_continuation_index.resolve_project_identity",
            return_value=project,
        ), patch(
            "agent_core.resolve_facade.resolve_project_identity",
            return_value=project,
        ):
            publish_project_continuation(initial_params, data_root=root)
            activate_continuation(
                "agentos-core",
                index_id="idx-seed-1",
                ir_id="ir-seed-1",
                reason="seed",
                data_root=root,
            )

    def test_checkpoint_completion_is_explicit_fenced_and_stays_empty(self):
        from unittest.mock import patch
        from agentos_node.ir_stop_sync import advance_active_ir_checkpoint
        from agentos_node.codex_one_mcp_stdio import _active_projection
        from agentos_node.one_mcp import OracleLocalGateway

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_temp_data_root(root)
            project = {"id": "agentos-core", "identity_source": "governance-directory",
                       "governance_entity_id": "project://agentos-core",
                       "integrity": {"mutation_allowed": True}}
            kwargs = dict(surface="test", model_name="test", user_intent="continue",
                          assistant_summary="done", data_root=root)
            fence = dict(expected_project_id="agentos-core", expected_index_id="idx-seed-1",
                         expected_ir_id="ir-seed-1")
            task = "Verify Stop hook and Codex projection"
            selector_path = root / "runtime" / "active-continuation.json"
            original = selector_path.read_bytes()
            with patch("agent_core.project_continuation_index.resolve_project_identity", return_value=project), \
                 patch("agent_core.resolve_facade.resolve_project_identity", return_value=project):
                for bad in ({"completed_tasks": [task]},
                            {**fence, "completed_tasks": ["unknown"]},
                            {**fence, "expected_ir_id": "stale", "completed_tasks": [task]},
                            {**fence, "expected_project_id": "other", "completed_tasks": [task]}):
                    with self.assertRaises(ValueError):
                        advance_active_ir_checkpoint(**kwargs, **bad)
                    self.assertEqual(selector_path.read_bytes(), original)
                result = advance_active_ir_checkpoint(**kwargs, **fence, completed_tasks=[task])
                self.assertEqual(result["completed_tasks"], [task])
                def pending():
                    return _active_projection(OracleLocalGateway(data_root=root))["resolution"]["continuation"]["canonical_ir"]["pending_tasks"]
                self.assertEqual(pending(), [])
                after_completion = selector_path.read_bytes()
                with self.assertRaises(ValueError):
                    advance_active_ir_checkpoint(**kwargs, **fence, completed_tasks=[task])
                self.assertEqual(selector_path.read_bytes(), after_completion)
                advance_active_ir_checkpoint(**kwargs)
                self.assertEqual(pending(), [])

    def test_stop_hook_advances_canonical_ir_and_codex_projection_resolves_it(self):
        from unittest.mock import patch
        from agentos_node.codex_one_mcp_stdio import _active_projection
        from agentos_node.ir_stop_sync import handle_stop_payload
        from agentos_node.one_mcp import OracleLocalGateway

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "agent-data"
            self._seed_temp_data_root(root)
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "USER_INPUT",
                                "content": "<USER_REQUEST>實作 Stop hook 自動同步 IR</USER_REQUEST>",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "PLANNER_RESPONSE",
                                "content": "已完成 Stop hook 與 Codex/Claude 即時 IR 寫回機制。",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            project = {
                "id": "agentos-core",
                "identity_source": "governance-directory",
                "governance_entity_id": "project://agentos-core",
                "integrity": {"mutation_allowed": True},
            }
            with patch(
                "agent_core.project_continuation_index.resolve_project_identity",
                return_value=project,
            ), patch(
                "agent_core.resolve_facade.resolve_project_identity",
                return_value=project,
            ):
                out = handle_stop_payload(
                    {
                        "executionNum": 1,
                        "terminationReason": "NO_TOOL_CALL",
                        "conversationId": "conv-stop-test",
                        "transcriptPath": str(transcript),
                        "modelName": "claude-opus-4-6-thinking",
                        "lastUserInput": "<USER_REQUEST>實作 Stop hook 自動同步 IR</USER_REQUEST>",
                    },
                    data_root=root,
                )
                self.assertEqual(out, {"decision": "allow"})

                selector = json.loads(
                    (root / "runtime" / "active-continuation.json").read_text(encoding="utf-8")
                )
                self.assertNotEqual(selector["index_id"], "idx-seed-1")
                self.assertNotEqual(selector["ir_id"], "ir-seed-1")

                gateway = OracleLocalGateway(data_root=root)
                projection = _active_projection(gateway)
                self.assertEqual(projection["selector"]["index_id"], selector["index_id"])
                self.assertEqual(projection["selector"]["ir_id"], selector["ir_id"])
                ir = projection["resolution"]["continuation"]["canonical_ir"]
                self.assertEqual(ir["parent_ir_id"], "ir-seed-1")
                self.assertEqual(ir["pending_tasks"], ["Verify Stop hook and Codex projection"])
                self.assertIn("實作 Stop hook 自動同步 IR", ir["continuation"]["next_action"])
                self.assertIn("已完成 Stop hook", ir["continuation"]["next_action"])

    def test_25_consecutive_stop_hook_turns_keep_canonical_ir_bounded(self):
        from unittest.mock import patch
        from agentos_node.ir_stop_sync import handle_stop_payload

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "agent-data"
            self._seed_temp_data_root(root)
            transcript = Path(tmp) / "transcript.jsonl"
            project = {
                "id": "agentos-core",
                "identity_source": "governance-directory",
                "governance_entity_id": "project://agentos-core",
                "integrity": {"mutation_allowed": True},
            }
            with patch(
                "agent_core.project_continuation_index.resolve_project_identity",
                return_value=project,
            ), patch(
                "agent_core.resolve_facade.resolve_project_identity",
                return_value=project,
            ):
                for i in range(1, 26):
                    transcript.write_text(
                        "\n".join(
                            [
                                json.dumps(
                                    {
                                        "type": "USER_INPUT",
                                        "content": f"Turn {i}: update module and verify step {i}",
                                    }
                                ),
                                json.dumps(
                                    {
                                        "type": "PLANNER_RESPONSE",
                                        "content": f"Completed step {i} verification with all checks passing.",
                                    }
                                ),
                            ]
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    res = handle_stop_payload(
                        {
                            "executionNum": i,
                            "terminationReason": "NO_TOOL_CALL",
                            "conversationId": "conv-25-turns",
                            "transcriptPath": str(transcript),
                            "modelName": "gemini-2.5-pro",
                            "lastUserInput": f"Turn {i}: update module and verify step {i}",
                        },
                        data_root=root,
                    )
                    self.assertEqual(res, {"decision": "allow"})

                latest_path = root / "projects" / "agentos-core" / "continuity" / "latest.json"
                latest = json.loads(latest_path.read_text(encoding="utf-8"))
                ir = latest["canonical_ir"]
                self.assertLessEqual(len(ir["decisions"]), 20)
                self.assertEqual(len(ir["evidence"]), 12)
                self.assertIn("Turn 25", ir["decisions"][-1])
                self.assertLess(latest_path.stat().st_size, 12_000)


if __name__ == "__main__":
    unittest.main()
