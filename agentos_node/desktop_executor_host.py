from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agentos_node import interactive_desktop
from agentos_node.executor_bridge import FileExecutorHost
from agentos_node.executor_registry import DESKTOP_CAPABILITIES, ExecutorRegistry
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


_RECEIPT_FIELDS = {
    'schema', 'realm_id', 'node_id', 'task_id', 'action', 'started_at',
    'completed_at', 'ok', 'cognition_ids_used', 'error',
}


class DesktopExecutorHost:
    """User-session host for the desktop executor.

    It intentionally owns no ONE transport and no Realm credential. Existing
    ThinClient desktop dispatch is reused with an empty local policy, and the host
    rejects every non-desktop task before execution.
    """

    def __init__(self, *, bridge_root: str | Path, poll_seconds: float = 0.2):
        registry = ExecutorRegistry()
        self.client = ThinClient(
            NodeIdentity('local-executor', 'desktop-executor-host'),
            ThinClientPolicy(),
            executor_registry=registry,
        )
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.host = FileExecutorHost(
            'desktop',
            bridge_root,
            capabilities=DESKTOP_CAPABILITIES,
            details_provider=interactive_desktop.session_info,
        )

    def _handle(self, task: dict[str, Any]) -> dict[str, Any]:
        action = str(task.get('action') or '')
        if not action.startswith('desktop.') or action not in DESKTOP_CAPABILITIES:
            raise PermissionError(f'desktop executor rejects action: {action}')
        receipt = self.client.execute(task)
        if not receipt.get('ok'):
            raise RuntimeError(str(receipt.get('error') or 'desktop execution failed'))
        return {key: value for key, value in receipt.items() if key not in _RECEIPT_FIELDS}

    def serve_once(self) -> int:
        info = interactive_desktop.session_info()
        if not info.get('interactive'):
            self.host.publish_descriptor(ready=False)
            return 0
        return self.host.serve_once(self._handle)

    def _publish_unavailable(self, exc: Exception) -> None:
        original = self.host.details_provider
        try:
            self.host.details_provider = lambda: {'error': f'{type(exc).__name__}: {exc}'}
            self.host.publish_descriptor(ready=False)
        except Exception:
            pass
        finally:
            self.host.details_provider = original

    def run_forever(self) -> None:
        while True:
            try:
                self.serve_once()
            except Exception as exc:
                self._publish_unavailable(exc)
            time.sleep(self.poll_seconds)
