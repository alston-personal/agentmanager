from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Callable

from agentos_node import interactive_desktop
from agentos_node.executor_bridge import describe_executor_bridge


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

    A Node Runtime may stay online in a non-interactive service session while an
    interactive desktop executor lives in another user-session process. Desktop
    capabilities are advertised only when either the local process is interactive
    or a fresh local executor bridge reports them available.
    """

    def __init__(
        self,
        *,
        platform_name: str | None = None,
        desktop_probe: Callable[[], dict[str, Any]] | None = None,
        desktop_bridge_probe: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.platform_name = platform_name or platform.system()
        self.desktop_probe = desktop_probe or interactive_desktop.session_info
        self.desktop_bridge_probe = desktop_bridge_probe or (lambda: describe_executor_bridge('desktop'))

    def _bridged_desktop(self) -> ExecutorDescriptor | None:
        try:
            bridge = self.desktop_bridge_probe()
        except Exception:
            return None
        if not bridge or not bridge.get('ready'):
            return None
        advertised = {str(x) for x in (bridge.get('capabilities') or [])}
        allowed = tuple(cap for cap in DESKTOP_CAPABILITIES if cap in advertised)
        if not allowed:
            return None
        safe_details = {
            'execution_mode': 'local_executor_bridge',
            'heartbeat_age_seconds': bridge.get('heartbeat_age_seconds'),
            'root': bridge.get('root'),
            'security_boundary': bridge.get('security_boundary'),
            'details': bridge.get('details'),
        }
        return ExecutorDescriptor(
            executor_id='desktop',
            kind='interactive-desktop-bridge',
            status='available',
            capabilities=allowed,
            details=safe_details,
        )

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
            bridged = self._bridged_desktop()
            if bridged:
                return bridged
            return ExecutorDescriptor(
                executor_id='desktop',
                kind='interactive-desktop',
                status='unavailable',
                capabilities=(),
                reason='probe_failed',
                details={'error': f'{type(exc).__name__}: {exc}'},
            )
        if bool(info.get('interactive')):
            return ExecutorDescriptor(
                executor_id='desktop',
                kind='interactive-desktop',
                status='available',
                capabilities=DESKTOP_CAPABILITIES,
                details={'execution_mode': 'in_process', **info},
            )
        bridged = self._bridged_desktop()
        if bridged:
            return bridged
        return ExecutorDescriptor(
            executor_id='desktop',
            kind='interactive-desktop',
            status='unavailable',
            capabilities=(),
            reason='not_interactive_session',
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
