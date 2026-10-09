from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformCapability:
    platform: str
    operation: str
    available: bool
    adapter: str | None = None
    note: str = ""


# This matrix describes runtime adapter availability, not product intent.
# A platform-neutral orchestrator must consult it instead of assuming that
# every social network exposes the same operations.
_CAPABILITIES = (
    # Threads: live adapter.
    PlatformCapability("threads", "identity.read", True, "ThreadsCapability"),
    PlatformCapability("threads", "post.read", True, "ThreadsCapability"),
    PlatformCapability("threads", "post.insights.read", True, "ThreadsCapability"),
    PlatformCapability("threads", "replies.read", True, "ThreadsCapability"),
    PlatformCapability("threads", "keyword.search", True, "ThreadsCapability"),
    PlatformCapability("threads", "publish", True, "ThreadsCapability"),
    PlatformCapability("threads", "reply", True, "ThreadsCapability"),
    PlatformCapability("threads", "disconnect", True, "ThreadsCapability"),
    # Follow/unfollow is intentionally not claimed until a provider adapter
    # has a verified, supported provider operation and acceptance contract.
    PlatformCapability("threads", "follow", False, None, "provider_operation_not_verified"),
    PlatformCapability("threads", "unfollow", False, None, "provider_operation_not_verified"),

    # Contract-level platform names already exist, but live provider adapters
    # are not yet accepted for these platforms.
    PlatformCapability("instagram", "publish", False, None, "adapter_not_implemented"),
    PlatformCapability("instagram", "reply", False, None, "adapter_not_implemented"),
    PlatformCapability("instagram", "post.insights.read", False, None, "adapter_not_implemented"),
    PlatformCapability("instagram", "follow", False, None, "adapter_not_implemented"),
    PlatformCapability("facebook", "publish", False, None, "adapter_not_implemented"),
    PlatformCapability("facebook", "reply", False, None, "adapter_not_implemented"),
    PlatformCapability("facebook", "post.insights.read", False, None, "adapter_not_implemented"),
    PlatformCapability("facebook", "follow", False, None, "adapter_not_implemented"),

    # X: contract surface is registered, but no live transport is accepted yet.
    # First rollout must be a secret-free auth/entitlement health probe; public
    # publishing remains fail-closed until an official API transport is accepted.
    PlatformCapability("x", "status", False, None, "health_probe_not_implemented"),
    PlatformCapability("x", "identity.read", False, None, "adapter_not_implemented"),
    PlatformCapability("x", "post.read", False, None, "adapter_not_implemented"),
    PlatformCapability("x", "publish", False, None, "transport_not_runtime_accepted"),
    PlatformCapability("x", "reply", False, None, "transport_not_runtime_accepted"),
)


def capability_matrix() -> tuple[PlatformCapability, ...]:
    return _CAPABILITIES


def platform_supports(platform: str, operation: str) -> bool:
    return any(
        row.platform == platform and row.operation == operation and row.available
        for row in _CAPABILITIES
    )


def platform_capabilities(platform: str) -> dict[str, bool]:
    return {
        row.operation: row.available
        for row in _CAPABILITIES
        if row.platform == platform
    }
