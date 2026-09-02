from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_core.employee_memory import (
    MEMORY_DECISION_SCHEMA,
    EmployeeMemoryPolicy,
    EmployeeMemoryService,
)
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry


REPO_ROOT = Path(__file__).resolve().parents[1]


class EmployeeMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.roles = RoleRegistry(REPO_ROOT / ".agent" / "roles" / "registry.yaml")
        self.policy = EmployeeMemoryPolicy(
            REPO_ROOT / "governance" / "employee-memory-policy.json"
        )
        self.memory = EmployeeMemoryService(self.runtime, self.roles, self.policy)

    def tearDown(self):
        self.tmp.cleanup()

    def test_spec_steward_can_use_governance_evidence_memory(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
        )
        decision = self.memory.write(
            "spec-steward",
            "governance_evidence",
            "closure-gap",
            {"issue": 151, "state": "open"},
        )
        self.assertEqual(decision.schema, MEMORY_DECISION_SCHEMA)
        self.assertTrue(decision.allowed)
        self.assertEqual(
            decision.authorizing_roles, ("governance.spec_steward",)
        )
        self.assertEqual(
            self.memory.read(
                "spec-steward", "governance_evidence", "closure-gap"
            ),
            {"issue": 151, "state": "open"},
        )

    def test_weaver_can_use_working_memory_but_not_governance_evidence(self):
        self.runtime.create_employee(
            "weaver",
            "Weaver",
            role_ids=["sector.weaver"],
        )
        self.memory.write("weaver", "working", "draft", {"spec": "bounded"})
        self.assertEqual(
            self.memory.read("weaver", "working", "draft"),
            {"spec": "bounded"},
        )
        denied = self.memory.authorize(
            "weaver", "weaver", "governance_evidence", "write"
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "no_explicit_role_grant")
        with self.assertRaisesRegex(PermissionError, "no_explicit_role_grant"):
            self.memory.write(
                "weaver", "governance_evidence", "fake-audit", {"ok": True}
            )

    def test_cartographer_world_model_grant_is_explicit(self):
        self.runtime.create_employee(
            "cartographer",
            "Cartographer",
            role_ids=["system.cartographer"],
        )
        decision = self.memory.write(
            "cartographer",
            "world_model",
            "node-freshness",
            {"fresh": False},
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(
            decision.authorizing_roles, ("system.cartographer",)
        )

    def test_cross_employee_private_memory_is_denied(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
        )
        self.runtime.create_employee(
            "keeper",
            "Keeper",
            role_ids=["governance.keeper"],
        )
        self.memory.write(
            "keeper",
            "governance_evidence",
            "private-finding",
            {"risk": "bounded"},
        )
        decision = self.memory.authorize(
            "spec-steward",
            "keeper",
            "governance_evidence",
            "read",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.reason, "cross_employee_private_memory_denied"
        )
        with self.assertRaisesRegex(
            PermissionError, "cross_employee_private_memory_denied"
        ):
            self.memory.read_other(
                "spec-steward",
                "keeper",
                "governance_evidence",
                "private-finding",
            )

    def test_proposed_role_cannot_coexist_with_active_role_to_gain_memory(self):
        self.runtime.create_employee(
            "unsafe-mixed-role",
            "Unsafe",
            role_ids=["sector.weaver", "governance.arbiter"],
        )
        with self.assertRaisesRegex(ValueError, "role is not active"):
            self.memory.authorize(
                "unsafe-mixed-role",
                "unsafe-mixed-role",
                "working",
                "read",
            )

    def test_employee_without_active_role_is_denied(self):
        self.runtime.create_employee("unroled", "Unroled")
        decision = self.memory.authorize(
            "unroled", "unroled", "working", "read"
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "active_role_required")

    def test_unknown_memory_class_is_denied(self):
        self.runtime.create_employee(
            "weaver",
            "Weaver",
            role_ids=["sector.weaver"],
        )
        decision = self.memory.authorize(
            "weaver", "weaver", "secret_everything", "read"
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "unknown_memory_class")

    def test_active_but_unlisted_role_does_not_inherit_another_roles_grant(self):
        policy_path = self.root / "policy.json"
        policy_path.write_text(
            json.dumps(
                {
                    "schema": "agentos.employee-memory-policy/v1",
                    "default_effect": "deny",
                    "cross_employee_access": "deny",
                    "memory_classes": ["working"],
                    "role_rules": {
                        "governance.spec_steward": {
                            "read": ["working"],
                            "write": ["working"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        service = EmployeeMemoryService(
            self.runtime,
            self.roles,
            EmployeeMemoryPolicy(policy_path),
        )
        self.runtime.create_employee(
            "weaver",
            "Weaver",
            role_ids=["sector.weaver"],
        )
        decision = service.authorize(
            "weaver", "weaver", "working", "write"
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "no_explicit_role_grant")

    def test_executor_rebinding_never_changes_memory_authority_or_leaks_session(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
        )
        before = self.memory.authorize(
            "spec-steward", "spec-steward", "governance_evidence", "read"
        )
        self.runtime.bind_executor(
            "spec-steward",
            provider="openai-codex-local",
            model="codex",
            session_id="private-session-id",
        )
        after = self.memory.authorize(
            "spec-steward", "spec-steward", "governance_evidence", "read"
        )
        self.assertEqual(before.allowed, after.allowed)
        serialized = json.dumps(after.as_dict(), ensure_ascii=False)
        self.assertNotIn("private-session-id", serialized)
        self.assertNotIn("openai-codex-local", serialized)

    def test_policy_rejects_default_allow_and_wildcards(self):
        for payload in (
            {
                "schema": "agentos.employee-memory-policy/v1",
                "default_effect": "allow",
                "cross_employee_access": "deny",
                "memory_classes": ["working"],
                "role_rules": {},
            },
            {
                "schema": "agentos.employee-memory-policy/v1",
                "default_effect": "deny",
                "cross_employee_access": "deny",
                "memory_classes": ["working"],
                "role_rules": {"*": {"read": ["working"], "write": []}},
            },
            {
                "schema": "agentos.employee-memory-policy/v1",
                "default_effect": "deny",
                "cross_employee_access": "deny",
                "memory_classes": ["working"],
                "role_rules": {
                    "sector.weaver": {"read": ["*"], "write": []}
                },
            },
        ):
            path = self.root / "invalid-policy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                EmployeeMemoryPolicy(path)

    def test_memory_classes_are_storage_isolated(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
        )
        self.memory.write("spec-steward", "working", "same-key", "work")
        self.memory.write(
            "spec-steward", "governance_evidence", "same-key", "evidence"
        )
        self.assertEqual(
            self.memory.read("spec-steward", "working", "same-key"),
            "work",
        )
        self.assertEqual(
            self.memory.read(
                "spec-steward", "governance_evidence", "same-key"
            ),
            "evidence",
        )


if __name__ == "__main__":
    unittest.main()
