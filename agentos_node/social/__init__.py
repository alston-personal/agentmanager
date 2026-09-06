"""Generic governed social capability boundary owned by AgentOS Core."""

from .contracts import SocialRequest, SocialReceipt
from .governance import SocialWriteGate
from .registry import SocialCapabilityRegistry, default_registry

__all__ = [
    "SocialRequest",
    "SocialReceipt",
    "SocialWriteGate",
    "SocialCapabilityRegistry",
    "default_registry",
]
