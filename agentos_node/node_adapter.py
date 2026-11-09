from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Iterable, Protocol


class NodeAdapter(Protocol):
    """Device/runtime adapter contract for AgentOS Thin Client.

    Adapters contribute capabilities to a Node without becoming Node identities.
    The Thin Client remains the transport, policy, heartbeat and receipt boundary.
    """

    adapter_id: str

    def capabilities(self) -> Iterable[str]:
        ...

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        ...

    def describe(self) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    capabilities: tuple[str, ...]
    metadata: dict[str, Any]


class AdapterRegistry:
    """Deterministic local adapter registry.

    v0.1 deliberately allows only one adapter provider for a given capability
    inside a Node. A hardware adapter may internally expose multiple devices
    (for example front/back cameras) through task parameters.
    """

    def __init__(self, adapters: Iterable[NodeAdapter] = ()):
        self._adapters: dict[str, NodeAdapter] = {}
        self._actions: dict[str, str] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: NodeAdapter) -> None:
        adapter_id = str(getattr(adapter, "adapter_id", "") or "").strip()
        if not adapter_id:
            raise ValueError("adapter_id is required")
        if adapter_id in self._adapters:
            raise ValueError(f"duplicate adapter_id: {adapter_id}")

        capabilities = tuple(sorted({
            str(item).strip()
            for item in adapter.capabilities()
            if str(item).strip()
        }))
        if not capabilities:
            raise ValueError(f"adapter has no capabilities: {adapter_id}")

        for action in capabilities:
            owner = self._actions.get(action)
            if owner:
                raise ValueError(
                    f"duplicate adapter capability: {action} ({owner}, {adapter_id})"
                )

        self._adapters[adapter_id] = adapter
        for action in capabilities:
            self._actions[action] = adapter_id

    def capabilities(self) -> list[str]:
        return sorted(self._actions)

    def resolve(self, action: str) -> NodeAdapter | None:
        adapter_id = self._actions.get(str(action))
        return self._adapters.get(adapter_id) if adapter_id else None

    def describe(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for adapter_id in sorted(self._adapters):
            adapter = self._adapters[adapter_id]
            metadata = adapter.describe()
            if not isinstance(metadata, dict):
                raise ValueError(f"adapter describe() must return object: {adapter_id}")
            result.append({
                "adapter_id": adapter_id,
                "capabilities": sorted({
                    str(item).strip()
                    for item in adapter.capabilities()
                    if str(item).strip()
                }),
                "metadata": dict(metadata),
            })
        return result


def _load_adapter_spec(spec: str) -> NodeAdapter:
    """Load an explicitly configured adapter.

    Supported forms:
      module.name
      module.name:create_adapter
      module.name:ADAPTER

    No filesystem/module auto-discovery is performed. This keeps adapter loading
    an explicit local authority decision.
    """

    module_name, sep, symbol = spec.partition(":")
    module_name = module_name.strip()
    symbol = symbol.strip()
    if not module_name:
        raise ValueError("adapter module name is required")

    module = importlib.import_module(module_name)
    if sep:
        target = getattr(module, symbol)
        adapter = target() if callable(target) else target
    elif hasattr(module, "create_adapter"):
        adapter = module.create_adapter()
    elif hasattr(module, "ADAPTER"):
        adapter = module.ADAPTER
    else:
        raise ValueError(
            f"adapter module must expose create_adapter() or ADAPTER: {module_name}"
        )

    if not getattr(adapter, "adapter_id", None):
        raise ValueError(f"invalid adapter from {spec}: missing adapter_id")
    if not callable(getattr(adapter, "capabilities", None)):
        raise ValueError(f"invalid adapter from {spec}: missing capabilities()")
    if not callable(getattr(adapter, "execute", None)):
        raise ValueError(f"invalid adapter from {spec}: missing execute()")
    if not callable(getattr(adapter, "describe", None)):
        raise ValueError(f"invalid adapter from {spec}: missing describe()")
    return adapter


def load_configured_adapters(value: str | None = None) -> list[NodeAdapter]:
    raw = os.environ.get("AGENTOS_NODE_ADAPTERS", "") if value is None else value
    specs = [item.strip() for item in str(raw).split(",") if item.strip()]
    return [_load_adapter_spec(spec) for spec in specs]
