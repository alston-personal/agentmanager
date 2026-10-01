from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.desktop_plan import execute_plan
from agentos_node.thin_client_transport import ClientConfig


class LowLatencyGuiAgentTests(unittest.TestCase):
    def test_client_defaults_to_long_poll_transport(self):
        cfg = ClientConfig(
            one_url='https://example.invalid',
            realm_id='realm-test',
            node_id='node-test',
            node_token='secret',
        )
        self.assertLessEqual(cfg.poll_seconds, 0.25)
        self.assertGreaterEqual(cfg.task_wait_seconds, 10.0)

    def test_desktop_plan_executes_locally_in_order(self):
        calls: list[tuple[str, object]] = []

        with tempfile.TemporaryDirectory() as td,              patch('agentos_node.desktop_plan.interactive_desktop.open_url', side_effect=lambda url: calls.append(('open', url)) or {'url': url}),              patch('agentos_node.desktop_plan.interactive_desktop.keyboard', side_effect=lambda step: calls.append(('keyboard', step['text'])) or {'characters': len(step['text'])}),              patch('agentos_node.desktop_plan.interactive_desktop.inspect_windows', side_effect=lambda: calls.append(('inspect', None)) or {'window_count': 1}):
            result = execute_plan(
                {
                    'plan': {
                        'schema': 'agentos.desktop-plan/v0.1',
                        'steps': [
                            {'action': 'desktop.open_url', 'url': 'https://example.com'},
                            {'action': 'desktop.keyboard', 'operation': 'paste', 'text': '中文測試'},
                            {'action': 'desktop.windows.inspect'},
                        ],
                    }
                },
                workspace=Path(td),
            )

        self.assertTrue(result['plan_ok'])
        self.assertEqual(result['steps_completed'], 3)
        self.assertEqual(
            calls,
            [('open', 'https://example.com'), ('keyboard', '中文測試'), ('inspect', None)],
        )

    def test_desktop_plan_stops_on_first_error(self):
        with tempfile.TemporaryDirectory() as td,              patch('agentos_node.desktop_plan.interactive_desktop.open_url', side_effect=RuntimeError('boom')):
            result = execute_plan(
                {
                    'plan': {
                        'schema': 'agentos.desktop-plan/v0.1',
                        'steps': [
                            {'action': 'desktop.open_url', 'url': 'https://example.com'},
                            {'action': 'desktop.wait', 'seconds': 0.01},
                        ],
                    }
                },
                workspace=Path(td),
            )

        self.assertFalse(result['plan_ok'])
        self.assertEqual(result['failed_step'], 0)
        self.assertEqual(result['steps_completed'], 0)


if __name__ == '__main__':
    unittest.main()
