from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_skills import (
    SKILL_REQUEST_SCHEMA,
    EmployeeSkillRegistry,
    EmployeeSkillService,
)
from agent_core.role_runtime import RoleRegistry


REPO_ROOT = Path(__file__).resolve().parents[1]


class EmployeeSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.roles = RoleRegistry(REPO_ROOT / ".agent" / "roles" / "registry.yaml")
        self.registry = EmployeeSkillRegistry(
            REPO_ROOT / "governance" / "employee-skills.json"
        )
        self.skills = EmployeeSkillService(
            self.runtime,
            self.roles,
            self.registry,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_spec_steward_hydrates_spec_audit_from_role_capability(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        hydrated = self.skills.hydrate_employee_skills("spec-steward")
        self.assertEqual(len(hydrated), 1)
        self.assertEqual(hydrated[0].skill_id, "spec.audit")
        self.assertEqual(
            hydrated[0].required_capabilities,
            ("governance.spec.audit",),
        )
        self.assertFalse(hydrated[0].mutation_authority)

    def test_skill_id_does_not_grant_missing_role_capability(self):
        self.runtime.create_employee(
            "weaver",
            "Weaver",
            role_ids=["sector.weaver"],
            skill_ids=["spec.audit"],
        )
        with self.assertRaisesRegex(
            PermissionError,
            "employee_skill_missing_role_capability:spec.audit:governance.spec.audit",
        ):
            self.skills.hydrate_employee_skills("weaver")

    def test_build_request_is_intent_only_and_authority_unbound(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        request = self.skills.build_request(
            "spec-steward",
            "spec.audit",
            "audit",
            {
                "scope": "agentos-core",
                "target_refs": ["issue:151", "spec:employee-runtime"],
            },
        )
        self.assertEqual(request["schema"], SKILL_REQUEST_SCHEMA)
        self.assertEqual(request["capability_authorization"], "required_downstream")
        self.assertEqual(
            request["execution_authority"], "external_governed_dispatcher"
        )
        self.assertEqual(request["executor_selection"], "unbound")
        self.assertEqual(request["transport_selection"], "unbound")
        self.assertFalse(request["credential_exposed"])
        serialized = json.dumps(request, ensure_ascii=False).casefold()
        for forbidden in (
            '"argv"',
            '"executable"',
            '"command"',
            '"shell"',
            '"url"',
            '"endpoint"',
            '"credential"',
            '"token"',
            '"authorization"',
            '"node_id"',
            "github_actions",
            "workflow_dispatch",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_skill_must_be_assigned_even_if_role_has_capability(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=[],
        )
        with self.assertRaisesRegex(PermissionError, "employee_skill_not_assigned"):
            self.skills.build_request(
                "spec-steward",
                "spec.audit",
                "audit",
                {"scope": "agentos-core", "target_refs": []},
            )

    def test_unknown_or_unexpected_intent_and_input_fail_closed(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        with self.assertRaisesRegex(
            PermissionError, "employee_skill_intent_not_allowed"
        ):
            self.skills.build_request(
                "spec-steward",
                "spec.audit",
                "mutate",
                {"scope": "agentos-core", "target_refs": []},
            )
        with self.assertRaisesRegex(ValueError, "employee_skill_unexpected_input"):
            self.skills.build_request(
                "spec-steward",
                "spec.audit",
                "audit",
                {"scope": "agentos-core", "target_refs": [], "extra": True},
            )

    def test_request_rejects_arbitrary_execution_and_secret_surfaces(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        unsafe_values = (
            {"scope": {"argv": ["rm", "-rf"]}, "target_refs": []},
            {"scope": "https://example.invalid/private", "target_refs": []},
            {"scope": "Bearer TOPSECRET", "target_refs": []},
            {"scope": {"token": "TOPSECRET"}, "target_refs": []},
        )
        for args in unsafe_values:
            with self.assertRaises(ValueError):
                self.skills.build_request(
                    "spec-steward", "spec.audit", "audit", args
                )

    def test_executor_rebinding_does_not_change_skill_authority_or_leak_session(self):
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        first = self.skills.build_request(
            "spec-steward",
            "spec.audit",
            "audit",
            {"scope": "agentos-core", "target_refs": []},
        )
        self.runtime.bind_executor(
            "spec-steward",
            provider="claude-code-local",
            model="claude",
            session_id="private-session-id",
        )
        second = self.skills.build_request(
            "spec-steward",
            "spec.audit",
            "audit",
            {"scope": "agentos-core", "target_refs": []},
        )
        self.assertEqual(first, second)
        serialized = json.dumps(second, ensure_ascii=False)
        self.assertNotIn("private-session-id", serialized)
        self.assertNotIn("claude-code-local", serialized)

    def test_registry_rejects_execution_carrier_fields(self):
        invalid_contracts = (
            {"argv": ["tool"]},
            {"executable": "/bin/tool"},
            {"url": "https://example.invalid"},
            {"token": "secret"},
        )
        for extra in invalid_contracts:
            path = self.root / "invalid-skills.json"
            skill = {
                "status": "active",
                "version": "1",
                "purpose": "invalid",
                "required_capabilities": ["governance.spec.audit"],
                "allowed_intents": ["audit"],
                "input_fields": ["scope"],
                "output_types": ["closure_gap"],
                "mutation_authority": False,
                **extra,
            }
            path.write_text(
                json.dumps(
                    {
                        "schema": "agentos.employee-skills/v1",
                        "default_effect": "deny",
                        "skills": {"bad": skill},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                EmployeeSkillRegistry(path)

    def test_inactive_and_unknown_skill_fail_closed(self):
        path = self.root / "inactive-skills.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "agentos.employee-skills/v1",
                    "default_effect": "deny",
                    "skills": {
                        "inactive": {
                            "status": "proposed",
                            "version": "1",
                            "purpose": "not active",
                            "required_capabilities": [],
                            "allowed_intents": ["audit"],
                            "input_fields": [],
                            "output_types": [],
                            "mutation_authority": False,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        registry = EmployeeSkillRegistry(path)
        with self.assertRaisesRegex(ValueError, "employee_skill_not_active"):
            registry.resolve("inactive")
        with self.assertRaisesRegex(KeyError, "unknown_employee_skill"):
            registry.resolve("missing")


if __name__ == "__main__":
    unittest.main()
