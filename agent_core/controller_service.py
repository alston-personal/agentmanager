from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agent_core.executor_job_contract import validate_executor_job
from agent_core.realm_fabric import RealmFabricStore
from agent_core.runtime_converge_contract import SCHEMA as RUNTIME_CONVERGE_SCHEMA, validate_runtime_converge_request


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class ControllerService:
    """Governed ONE control-plane dispatcher for Node actions.

    Typed privileged actions use fixed semantic adapters. Ordinary Node actions
    still follow the accepted #64 queue contract. No privileged branch expands
    into generic shell/argv authority.
    """

    REQUEST_SCHEMA = 'agentos.controller-dispatch/v0.1'
    RECEIPT_SCHEMA = 'agentos.controller-dispatch-receipt/v0.1'
    EXECUTOR_JOB_ACTION = 'agentos.executor.job'
    EXECUTOR_JOB_NODE = 'oracle-core-node'
    RUNTIME_CONVERGE_ACTION = 'node.runtime.converge'
    RUNTIME_CONVERGE_NODE = 'oracle-core-node'

    def __init__(self, fabric: RealmFabricStore, executor_job_dispatcher: Any | None = None,
                 runtime_converge_dispatcher: Any | None = None):
        self.fabric = fabric
        self._executor_job_dispatcher = executor_job_dispatcher
        self._runtime_converge_dispatcher = runtime_converge_dispatcher

    def _executor_dispatcher(self):
        if self._executor_job_dispatcher is None:
            from agentos_node.executor_job_action_relay import ActionRelayExecutorJobDispatcher
            self._executor_job_dispatcher = ActionRelayExecutorJobDispatcher()
        return self._executor_job_dispatcher

    def _runtime_dispatcher(self):
        if self._runtime_converge_dispatcher is None:
            from agentos_node.runtime_converge_action_relay import ActionRelayRuntimeConvergeDispatcher
            self._runtime_converge_dispatcher = ActionRelayRuntimeConvergeDispatcher()
        return self._runtime_converge_dispatcher

    TYPED_DESKTOP_CAPABILITY = {
        'desktop.window.stage': 'desktop.windows.tile',
        'desktop.pointer.click': 'desktop.mouse',
        'desktop.text.insert': 'desktop.keyboard',
    }

    @classmethod
    def _typed_desktop_task(cls, *, task_id: str, action: str, request: dict[str, Any]) -> dict[str, Any]:
        base = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'controller_action': action,
            'cognition_ids_used': list(request.get('cognition_ids_used') or []),
        }
        if action == 'desktop.window.stage':
            title = str(request.get('title_contains') or '').strip()
            zone = str(request.get('zone') or '').strip().lower()
            if not title or len(title) > 120:
                raise ValueError('desktop.window.stage requires title_contains 1..120 chars')
            if zone not in {'left', 'right', 'full'}:
                raise ValueError('desktop.window.stage zone must be left|right|full')
            reserve_top = int(request.get('reserve_top_px') if request.get('reserve_top_px') is not None else 8)
            margin = int(request.get('margin_px') if request.get('margin_px') is not None else 4)
            if not 0 <= reserve_top <= 160:
                raise ValueError('desktop.window.stage reserve_top_px must be 0..160')
            if not 0 <= margin <= 40:
                raise ValueError('desktop.window.stage margin_px must be 0..40')
            return {
                **base,
                'action': 'desktop.windows.tile',
                'windows': [{'title_contains': title, 'zone': zone}],
                'reserve_top_px': reserve_top,
                'margin_px': margin,
            }
        if action == 'desktop.pointer.click':
            if 'x' not in request or 'y' not in request:
                raise ValueError('desktop.pointer.click requires x and y')
            x, y = int(request['x']), int(request['y'])
            if not 0 <= x <= 16383 or not 0 <= y <= 16383:
                raise ValueError('desktop.pointer.click coordinates out of bounds')
            button = str(request.get('button') or 'left').strip().lower()
            if button not in {'left', 'right'}:
                raise ValueError('desktop.pointer.click button must be left|right')
            return {
                **base, 'action': 'desktop.mouse', 'operation': 'click',
                'x': x, 'y': y, 'button': button,
            }
        if action == 'desktop.text.insert':
            text = str(request.get('text') or '')
            if not text or len(text) > 1000:
                raise ValueError('desktop.text.insert text must contain 1..1000 characters')
            return {**base, 'action': 'desktop.keyboard', 'operation': 'paste', 'text': text}
        raise ValueError(f'unsupported typed desktop action: {action}')

    def _node_for_dispatch(self, node_id: str) -> dict[str, Any]:
        node_map = self.fabric.node_registry.node_map()
        matches = [node for node in node_map.get('nodes', []) if node.get('node_id') == node_id]
        if not matches:
            raise KeyError(node_id)
        node = matches[0]
        if node.get('status') != 'online':
            raise ValueError(f'target node is not online: {node_id}')
        return node

    def _dispatch_executor_job(self, *, node_id: str, payload: Any, passthrough: dict[str, Any]) -> dict[str, Any]:
        if passthrough:
            raise ValueError(f'unexpected executor-job controller fields: {sorted(passthrough)}')
        if not isinstance(payload, dict):
            raise ValueError('executor-job payload must be an object')
        validate_executor_job(payload)
        if node_id != self.EXECUTOR_JOB_NODE:
            raise ValueError(f'executor job is not routable to target node: {node_id}')
        submission = dict(self._executor_dispatcher().submit(node_id=node_id, request=payload))
        job_id = str(submission.get('job_id') or '')
        if not job_id:
            raise RuntimeError('executor-job dispatcher returned no job_id')
        submission['task_id'] = job_id
        return submission

    def _dispatch_runtime_converge(self, *, node_id: str, task_hint: str,
                                   payload: dict[str, Any], passthrough: dict[str, Any]) -> dict[str, Any]:
        if payload:
            raise ValueError('runtime converge does not accept generic payload')
        allowed = {'repository', 'source_ref', 'source_commit'}
        unexpected = set(passthrough) - allowed
        if unexpected:
            raise ValueError(f'unexpected runtime-converge controller fields: {sorted(unexpected)}')
        if set(passthrough) != allowed:
            raise ValueError('runtime converge requires repository, source_ref, and source_commit')
        if node_id != self.RUNTIME_CONVERGE_NODE:
            raise ValueError(f'runtime converge is not routable to target node: {node_id}')
        request_id = task_hint or ('ctl-' + uuid.uuid4().hex)
        canonical = {
            'schema': RUNTIME_CONVERGE_SCHEMA,
            'request_id': request_id,
            'node_id': node_id,
            'repository': passthrough['repository'],
            'source_ref': passthrough['source_ref'],
            'source_commit': passthrough['source_commit'],
        }
        validate_runtime_converge_request(canonical)
        return dict(self._runtime_dispatcher().submit(request=canonical))

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError('controller request must be an object')
        schema = request.get('schema')
        if schema not in (None, self.REQUEST_SCHEMA):
            raise ValueError('invalid controller dispatch schema')

        node_id = str(request.get('node_id') or request.get('target_node') or '').strip()
        action = str(request.get('action') or request.get('capability') or '').strip()
        if not node_id:
            raise ValueError('node_id is required')
        if not action:
            raise ValueError('action is required')

        node = self._node_for_dispatch(node_id)
        payload = request.get('payload')
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError('payload must be an object')

        reserved = {'schema', 'task_id', 'action', 'node_id', 'target_node', 'capability', 'payload'}
        passthrough = {key: value for key, value in request.items() if key not in reserved}

        if action == self.EXECUTOR_JOB_ACTION:
            return self._dispatch_executor_job(node_id=node_id, payload=payload, passthrough=passthrough)

        advertised = {str(x) for x in (node.get('capabilities') or []) if str(x)}
        required_capability = self.TYPED_DESKTOP_CAPABILITY.get(action, action)
        if required_capability not in advertised:
            raise ValueError(f'target node does not advertise capability: {required_capability}')

        if action == self.RUNTIME_CONVERGE_ACTION:
            return self._dispatch_runtime_converge(
                node_id=node_id,
                task_hint=str(request.get('task_id') or '').strip(),
                payload=payload,
                passthrough=passthrough,
            )

        task_id = str(request.get('task_id') or ('task-' + uuid.uuid4().hex))
        if action in self.TYPED_DESKTOP_CAPABILITY:
            if payload:
                raise ValueError(f'{action} does not accept generic payload')
            task = self._typed_desktop_task(task_id=task_id, action=action, request=passthrough)
        else:
            task = {
                'schema': 'agentos.node-task/v0.1',
                'task_id': task_id,
                'action': action,
                **payload,
                **passthrough,
            }
        queued = self.fabric.queue_task(node_id, task)
        return {
            'schema': self.RECEIPT_SCHEMA,
            'ok': True,
            'controller_entered': True,
            'dispatch_id': 'dispatch-' + uuid.uuid4().hex,
            'node_id': node_id,
            'action': action,
            'task_id': task_id,
            'queued_at': queued.get('queued_at') or _utc_now(),
            'queue_schema': queued.get('schema'),
            'node_status': node.get('status'),
            'advertised_capability': True,
        }
