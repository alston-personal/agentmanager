import unittest
from pathlib import Path

from agent_core.roles import (
    BaseRoleWorker,
    CheckVerdict,
    DoOutput,
    GovernanceRoleBase,
    PlanSpec,
    ProductCreatorBase,
    RoleContext,
    SectorExecutorBase,
    SystemInfraRoleBase,
)


class _SampleAtlasLeaf(GovernanceRoleBase):
    ROLE_ID = "test.governance.sample_atlas"
    ALIASES = ("sample-atlas",)

    def plan(self, cycle: int) -> PlanSpec:
        return PlanSpec(task="Audit closure queue", source="test_scheduler")

    def do(self, plan_spec: PlanSpec, work_id: str) -> DoOutput:
        q = self.load_refinement_queue()
        return DoOutput(
            action="audit_closure",
            status="completed",
            findings=[f"queue_unqualified={q.get('total_unqualified', 0)}"],
        )

    def check(self, plan_spec: PlanSpec, do_output: DoOutput) -> CheckVerdict:
        return CheckVerdict(
            verifier_role="governance.keeper",
            verdict="PASS",
            findings=do_output.findings,
        )


class RoleAbstractHierarchyTests(unittest.TestCase):
    def test_abstract_layers_cannot_be_instantiated(self) -> None:
        for abstract_cls in (
            BaseRoleWorker,
            GovernanceRoleBase,
            SystemInfraRoleBase,
            SectorExecutorBase,
            ProductCreatorBase,
        ):
            with self.assertRaises(TypeError):
                abstract_cls()  # type: ignore[abstract]

    def test_concrete_leaf_auto_registers_and_resolves_normalized(self) -> None:
        resolved = BaseRoleWorker.resolve_leaf("test.governance.sample_atlas")
        self.assertIs(resolved, _SampleAtlasLeaf)
        self.assertIs(BaseRoleWorker.resolve_leaf("test-governance-sample-atlas"), _SampleAtlasLeaf)
        self.assertIs(BaseRoleWorker.resolve_leaf("sample_atlas"), _SampleAtlasLeaf)

    def test_unregistered_role_fails_closed(self) -> None:
        with self.assertRaises(KeyError):
            BaseRoleWorker.resolve_leaf("nonexistent.abstract.shell")

    def test_leaf_executes_template_method_with_di_context(self) -> None:
        ctx = RoleContext(
            data_root=Path("/tmp/nonexistent-agent-data"),
            project_root=Path("/tmp/nonexistent-project"),
            clock=lambda: "2026-11-20T00:00:00Z",
        )
        worker = _SampleAtlasLeaf(context=ctx)
        res = worker.run_cycle(cycle=7)
        self.assertEqual(res["verdict"], "PASS")
        self.assertEqual(res["timestamp"], "2026-11-20T00:00:00Z")
        self.assertEqual(res["work_id"], "test-governance-sample-atlas-work-0007")


if __name__ == "__main__":
    unittest.main()
