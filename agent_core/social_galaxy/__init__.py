"""
Social Relationship Galaxy Multi-Platform Engine (跨社群關係宇宙引擎)
"""
from __future__ import annotations

from .models import CanonicalSocialEvent, RelationshipGraph, IdentityResolver
from .adapters.base import BaseSocialAdapter

__all__ = [
    "CanonicalSocialEvent",
    "RelationshipGraph",
    "IdentityResolver",
    "BaseSocialAdapter",
]
