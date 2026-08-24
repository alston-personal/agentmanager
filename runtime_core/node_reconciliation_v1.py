"""Portable descriptor contract for Node-local cognition reconciliation.

The thin Node may emit these metadata/provenance descriptors without importing
Core governance/reconciliation implementation. Raw local content is not part of
this contract.
"""

from __future__ import annotations

from dataclasses import dataclass


LOCAL_COGNITION_DESCRIPTOR_SCHEMA = "agentos.local-cognition-descriptor/v1"


@dataclass(frozen=True)
class LocalCognitionDescriptor:
    local_ref: str
    content_hash: str
    kind: str
    provenance: str
    project_id: str | None = None
    supersedes_hash: str | None = None
    sensitive: bool = False
    node_local_only: bool = False
    schema_version: str = LOCAL_COGNITION_DESCRIPTOR_SCHEMA

    def __post_init__(self) -> None:
        if not self.local_ref.strip() or not self.content_hash.strip() or not self.kind.strip() or not self.provenance.strip():
            raise ValueError("local cognition identity/provenance fields are required")
