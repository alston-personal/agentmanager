import json
import tempfile
import unittest
from pathlib import Path

from agent_core.engineering_authority import evaluate_branch_write, load_engineering_state


class TestEngineeringAuthority(unittest.TestCase):
    def setUp(self):
        self.state = {
            'schema': 'agentos.engineering-state/v0.1',
            'authority': {
                'owner_role': 'agentos-engineering',
                'active_branch': 'feature/realm-node-fabric-readiness',
                'merge_target': 'main',
            },
        }

    def test_owner_can_write_only_active_branch(self):
        allowed = evaluate_branch_write(
            role='agentos-engineering',
            branch='feature/realm-node-fabric-readiness',
            state=self.state,
        )
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.permission, 'write')

        denied = evaluate_branch_write(
            role='agentos-engineering',
            branch='feature/something-else',
            state=self.state,
        )
        self.assertFalse(denied.allowed)

    def test_main_is_never_directly_writable(self):
        decision = evaluate_branch_write(
            role='agentos-engineering',
            branch='main',
            state=self.state,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.permission, 'proposal-only')

    def test_other_agents_are_proposal_only(self):
        for role in ('agentos-research', 'project-agent', 'unknown'):
            decision = evaluate_branch_write(
                role=role,
                branch='feature/realm-node-fabric-readiness',
                state=self.state,
            )
            self.assertFalse(decision.allowed, role)
            self.assertEqual(decision.permission, 'proposal-only')

    def test_experiment_agent_isolated_branch_only(self):
        allowed = evaluate_branch_write(
            role='experiment-agent',
            branch='experiment/layoutlib-threshold',
            state=self.state,
        )
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.permission, 'isolated-experiment-write')

        denied = evaluate_branch_write(
            role='experiment-agent',
            branch='feature/realm-node-fabric-readiness',
            state=self.state,
        )
        self.assertFalse(denied.allowed)

    def test_state_loader_validates_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text(json.dumps(self.state), encoding='utf-8')
            loaded = load_engineering_state(path)
            self.assertEqual(loaded['authority']['merge_target'], 'main')


if __name__ == '__main__':
    unittest.main()
