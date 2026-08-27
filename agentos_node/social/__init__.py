"""Reusable social-platform capabilities for AgentOS.

Secrets never appear in capability receipts. Callers refer to credentials by logical
name; the runtime resolves that binding locally.
"""

from .contracts import SocialReceipt
from .credentials import CredentialBinding, EnvironmentCredentialResolver
from .threads import ThreadsCapability

__all__ = [
    "SocialReceipt",
    "CredentialBinding",
    "EnvironmentCredentialResolver",
    "ThreadsCapability",
]
