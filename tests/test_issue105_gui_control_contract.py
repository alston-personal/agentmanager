import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from agent_core.control_inbox_bridge import BridgeConfig, ControlInboxBridge
from agent_core.controller_api import ControllerService, CONTROLLER_ACTION_CAPABILITY


class Issue105GuiContractTests(unittest.TestCase):
    def test_input_capabilities_are_explicit(self):
        self.assertEqual(CONTROLLER_ACTION_CAPABILITY['desktop.mouse'], 'desktop.mouse')
        self.assertEqual(CONTROLLER_ACTION_CAPABILITY['desktop.keyboard'], 'desktop.keyboard')

    def test_mouse_validation(self):
        task = ControllerService._desktop_input_task(
            'desktop.mouse', 't1',
            {'operation': 'click', 'x': 12, 'y': -4, 'button': 'left'},
        )
        self.assertEqual(task['action'], 'desktop.mouse')
        self.assertEqual(task['button'], 'left')
        with self.assertRaises(ValueError):
            ControllerService._desktop_input_task(
                'desktop.mouse', 't2',
                {'operation': 'click', 'x': '12', 'y': 4},
            )
        with self.assertRaises(ValueError):
            ControllerService._desktop_input_task(
                'desktop.mouse', 't3', {'operation': 'drag'},
            )

    def test_keyboard_validation(self):
        task = ControllerService._desktop_input_task(
            'desktop.keyboard', 't1',
            {'operation': 'type', 'text': 'PASS'},
        )
        self.assertEqual(task['text'], 'PASS')
        with self.assertRaises(ValueError):
            ControllerService._desktop_input_task(
                'desktop.keyboard', 't2',
                {'operation': 'type', 'text': ''},
            )
        with self.assertRaises(ValueError):
            ControllerService._desktop_input_task(
                'desktop.keyboard', 't3',
                {'operation': 'press', 'text': 'x'},
            )

    def _bridge(self, root):
        cfg = BridgeConfig(
            'o/r', 50, 'u', 'g', 'c', 'http://one',
            Path(root) / 'state.json', 1, 1,
        )
        return ControlInboxBridge(cfg, github=object(), one=object())

    def test_screenshot_is_compacted_to_artifact_ref(self):
        with tempfile.TemporaryDirectory() as td:
            raw = b'fake-jpeg-bytes'
            sha = hashlib.sha256(raw).hexdigest()
            compact = self._bridge(td)._compact_receipt({
                'schema': 'agentos.node-receipt/v0.1',
                'node_id': 'n',
                'task_id': 't',
                'action': 'desktop.screenshot',
                'ok': True,
                'image_base64': base64.b64encode(raw).decode(),
                'sha256': sha,
                'bytes': len(raw),
                'width': 10,
                'height': 20,
                'mime_type': 'image/jpeg',
                'path': 'C:/private/path.jpg',
                'session': {'username': 'private'},
            })
            self.assertNotIn('image_base64', compact)
            self.assertNotIn('path', compact)
            self.assertNotIn('session', compact)
            self.assertEqual(
                compact['artifact_ref'],
                f'agentos://control-inbox/artifacts/{sha}.jpg',
            )
            self.assertTrue((Path(td) / 'artifacts' / f'{sha}.jpg').is_file())

    def test_window_titles_are_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            compact = self._bridge(td)._compact_receipt({
                'action': 'desktop.windows.inspect',
                'ok': True,
                'windows': [
                    {'title': 'PRIVATE TITLE', 'process_name': 'notepad.exe'},
                    {'title': 'ANOTHER PRIVATE TITLE', 'process_name': 'notepad.exe'},
                ],
                'window_count': 2,
            })
            self.assertEqual(compact['process_names'], ['notepad.exe'])
            self.assertTrue(compact['window_titles_redacted'])
            self.assertNotIn('windows', compact)
            self.assertNotIn('PRIVATE TITLE', repr(compact))


if __name__ == '__main__':
    unittest.main()
