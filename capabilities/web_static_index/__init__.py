"""Reusable AgentOS capability for machine-readable static web indexes."""

from .renderer import CAPABILITY_ID, render_static_index, render_to_file, validate_spec

__all__ = ["CAPABILITY_ID", "render_static_index", "render_to_file", "validate_spec"]
