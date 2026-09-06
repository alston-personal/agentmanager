from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SocialCapabilitySpec:
    name: str
    platform: str
    operation: str
    write: bool
    runtime_accepted: bool = False


class SocialCapabilityRegistry:
    def __init__(self, specs: tuple[SocialCapabilitySpec, ...]) -> None:
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> SocialCapabilitySpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"unknown social capability: {name}") from exc

    def list(self) -> tuple[SocialCapabilitySpec, ...]:
        return tuple(sorted(self._specs.values(), key=lambda item: item.name))


def _platform_specs(platform: str) -> list[SocialCapabilitySpec]:
    reads = ("status", "identity.read", "post.read", "replies.read")
    writes = ("publish", "reply", "disconnect")
    specs = [SocialCapabilitySpec(f"social.{platform}.{op}", platform, op, False) for op in reads]
    specs.extend(SocialCapabilitySpec(f"social.{platform}.{op}", platform, op, True, False) for op in writes)
    return specs


_SPECS: list[SocialCapabilitySpec] = []
for _platform in ("threads", "facebook", "instagram"):
    _SPECS.extend(_platform_specs(_platform))
_SPECS.append(SocialCapabilitySpec("social.threads.public_post.read", "threads", "public_post.read", False))
_SPECS.append(SocialCapabilitySpec("social.threads.connect", "threads", "connect", False))

default_registry = SocialCapabilityRegistry(tuple(_SPECS))
