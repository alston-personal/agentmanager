from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from agentos_node import interactive_desktop

PLAN_SCHEMA = 'agentos.desktop-plan/v0.1'
_ALLOWED_STEP_ACTIONS = {
    'desktop.open_url',
    'desktop.mouse',
    'desktop.keyboard',
    'desktop.wait',
    'desktop.windows.inspect',
    'desktop.screenshot',
}


def execute_plan(task: dict[str, Any], *, workspace: Path, max_steps: int = 64) -> dict[str, Any]:
    plan = dict(task.get('plan') or {})
    if plan.get('schema') != PLAN_SCHEMA:
        raise ValueError('invalid desktop plan schema')
    steps = plan.get('steps') or []
    if not isinstance(steps, list) or not steps:
        raise ValueError('desktop plan requires at least one step')
    if len(steps) > max_steps:
        raise ValueError(f'desktop plan exceeds max_steps={max_steps}')

    started = time.monotonic()
    results: list[dict[str, Any]] = []
    stop_on_error = bool(plan.get('stop_on_error', True))

    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ValueError(f'plan step {index} must be an object')
        action = str(raw.get('action') or '')
        if action not in _ALLOWED_STEP_ACTIONS:
            raise ValueError(f'unsupported desktop plan action at step {index}: {action}')

        step_started = time.monotonic()
        try:
            if action == 'desktop.open_url':
                result = interactive_desktop.open_url(str(raw.get('url') or ''))
            elif action == 'desktop.mouse':
                result = interactive_desktop.mouse(raw)
            elif action == 'desktop.keyboard':
                result = interactive_desktop.keyboard(raw)
            elif action == 'desktop.wait':
                seconds = max(0.0, min(float(raw.get('seconds') or 0), 30.0))
                time.sleep(seconds)
                result = {'seconds': seconds}
            elif action == 'desktop.windows.inspect':
                result = interactive_desktop.inspect_windows()
            elif action == 'desktop.screenshot':
                result = interactive_desktop.screenshot(workspace, quality=int(raw.get('quality') or 55))
            else:  # pragma: no cover
                raise ValueError(action)
            results.append({
                'index': index,
                'action': action,
                'ok': True,
                'elapsed_ms': int((time.monotonic() - step_started) * 1000),
                'result': result,
            })
        except Exception as exc:
            failed = {
                'index': index,
                'action': action,
                'ok': False,
                'elapsed_ms': int((time.monotonic() - step_started) * 1000),
                'error': f'{type(exc).__name__}: {exc}',
            }
            results.append(failed)
            if stop_on_error:
                return {
                    'plan_ok': False,
                    'failed_step': index,
                    'steps_completed': index,
                    'elapsed_ms': int((time.monotonic() - started) * 1000),
                    'results': results,
                }

    return {
        'plan_ok': all(item.get('ok') for item in results),
        'failed_step': None,
        'steps_completed': len(results),
        'elapsed_ms': int((time.monotonic() - started) * 1000),
        'results': results,
    }
