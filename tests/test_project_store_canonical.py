from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_core import project_store
from agent_core.project_store import CanonicalProjectRegistration, ProjectSourceAuthority


class TestCanonicalProjectStore(unittest.TestCase):
    def test_project_identity_is_independent_from_repo_and_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            projects = root / 'projects'
            governance = root / 'governance' / 'directory.json'
            with patch.object(project_store.config, 'PROJECTS_DIR', projects), \
                 patch.object(project_store, 'upsert') as upsert:
                upsert.side_effect = lambda entity: entity
                result = project_store.register_canonical_project(
                    CanonicalProjectRegistration(
                        project_id='agentos-core',
                        display_name='AgentOS Core',
                        aliases=('AgentOS', 'AgentOS Core'),
                        source=ProjectSourceAuthority(
                            repo='alston-personal/agentmanager',
                            branch='main',
                            canonical_path='/home/ubuntu/agentmanager',
                            node='oracle-core-node',
                        ),
                        state_document='STATUS.md',
                        current_focus='Canonical continuation through ONE',
                        next_action='Run authenticated live resolve acceptance',
                    )
                )
                self.assertEqual(result['project_id'], 'agentos-core')
                self.assertEqual(result['source']['repo'], 'alston-personal/agentmanager')
                self.assertEqual(result['source']['canonical_path'], '/home/ubuntu/agentmanager')
                self.assertTrue(result['mutation_ready'])
                doc = project_store.load_project_document('agentos-core')
                self.assertEqual(doc['project_id'], 'agentos-core')
                self.assertEqual(doc['source']['repo'], 'alston-personal/agentmanager')
                self.assertEqual(doc['state']['document'], str(projects / 'agentos-core' / 'STATUS.md'))
                entity = upsert.call_args.args[0]
                self.assertEqual(entity.id, 'project://agentos-core')
                self.assertEqual(entity.implementation['source']['node'], 'oracle-core-node')
                self.assertEqual(entity.metadata['aliases'], ['AgentOS', 'AgentOS Core'])

    def test_missing_source_authority_is_rejected(self) -> None:
        registration = CanonicalProjectRegistration(
            project_id='agentos-core',
            display_name='AgentOS Core',
            source=ProjectSourceAuthority(
                repo='alston-personal/agentmanager',
                branch='main',
                canonical_path='/home/ubuntu/agentmanager',
                node='',
            ),
            state_document='STATUS.md',
        )
        with self.assertRaises(ValueError):
            registration.validate()


if __name__ == '__main__':
    unittest.main()
