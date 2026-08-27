from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Callable

from agentos_node import interactive_desktop


DESKTOP_CAPABILITIES = (
    'desktop.session.inspect',
    'desktop.windows.inspect',
    'desktop.screenshot',
    'desktop.open_url',
    'desktop.mouse',
    'desktop.keyboard',
)


@dataclass(frozen=True)
class ExecutorDescriptor:
    executor_id: str
    kind: str
    status: str
    capabilities: tuple[str, ...]
    reason: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'executor_id': self.executor_id,
            'kind': self.kind,
            'status': self.status,
            'capabilities': list(self.capabilities),
        }
        if self.reason:
            payload['reason'] = self.reason
        if self.details:
            payload['details'] = self.details
        return payload


class ExecutorRegistry:
    """Discover runtime executors independently from the Node transport lifecycle.

    The Node Runtime may stay online in a non-interactive service session while the
    desktop executor is unavailable. Desktop capabilities are only advertised when
    the current process is actually attached to the active interactive session.
    """

    def __init__(
        self,
        *,
        platform_name: str | None = None,
        desktop_probe: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.platform_name = platform_name or platform.system()
        self.desktop_probe = desktop_probe or interactive_desktop.session_info

    def desktop(self) -> ExecutorDescriptor:
        if self.platform_name != 'Windows':
            return ExecutorDescriptor(
                executor_id='desktop',
                kind='interactive-desktop',
                status='unavailable',
                capabilities=(),
                reason='unsupported_platform',
                details={'platform': self.platform_name},
            )
        try:
            info = dict(self.desktop_probe())
        except Exception as exc:
            return ExecutorDescriptor(
                executor_id='desktop',
                kind='interactive-desktop',
                status='unavailable',
                capabilities=(),
                reason='probe_failed',
                details={'error': f'{type(exc).__name__}: {exc}'},
            )
        if not bool(info.get('interactive')):
            return ExecutorDescriptor(
                executor_id='desktop',
                kind='interactive-desktop',
                status='unavailable',
                capabilities=(),
                reason='not_interactive_session',
                details=info,
            )
        return ExecutorDescriptor(
            executor_id='desktop',
            kind='interactive-desktop',
            status='available',
            capabilities=DESKTOP_CAPABILITIES,
            details=info,
        )

    def inventory(self, *, local_capabilities: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        local = ExecutorDescriptor(
            executor_id='local',
            kind='node-local',
            status='available',
            capabilities=tuple(sorted(set(local_capabilities))),
        )
        return [local.as_dict(), self.desktop().as_dict()]

    def available_capabilities(self, *, local_capabilities: list[str] | tuple[str, ...]) -> list[str]:
        caps = set(local_capabilities)
        desktop = self.desktop()
        if desktop.status == 'available':
            caps.update(desktop.capabilities)
        return sorted(caps)

    def require_desktop(self) -> ExecutorDescriptor:
        desktop = self.desktop()
        if desktop.status != 'available':
            raise RuntimeError(f'desktop executor unavailable: {desktop.reason}')
        return desktop
