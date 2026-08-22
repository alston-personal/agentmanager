"""Durable AgentOS Node directory.

Stores content-addressed capability manifests and current onboarding checkpoints.
The directory is descriptive state only; authorization remains owned by the
GovernanceRegistry and cannot be manufactured by directory writes.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3

from runtime_core.node_v1 import CapabilityObservation, CapabilityState, NodeCapabilityManifest, NodeIdentity
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint, validate_transition


class NodeDirectoryStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS node_manifests (
                    manifest_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_node_manifests_node_time
                    ON node_manifests(node_id, observed_at);

                CREATE TABLE IF NOT EXISTS node_heads (
                    node_id TEXT PRIMARY KEY,
                    manifest_id TEXT,
                    checkpoint_json TEXT NOT NULL,
                    FOREIGN KEY(manifest_id) REFERENCES node_manifests(manifest_id)
                );
                """
            )

    @staticmethod
    def _manifest_payload(manifest: NodeCapabilityManifest) -> str:
        return json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _parse_manifest(payload: str) -> NodeCapabilityManifest:
        data = json.loads(payload)
        identity_payload = data["identity"]
        identity_payload["labels"] = tuple(identity_payload.get("labels", ()))
        identity = NodeIdentity(**identity_payload)
        capabilities = tuple(
            CapabilityObservation(
                capability=item["capability"],
                source=item["source"],
                state=CapabilityState(item["state"]),
                device_ref=item.get("device_ref"),
                adapter=item.get("adapter"),
                attributes=item.get("attributes", {}),
                risk_tags=tuple(item.get("risk_tags", ())),
            )
            for item in data["capabilities"]
        )
        return NodeCapabilityManifest(
            identity=identity,
            observed_at=data["observed_at"],
            capabilities=capabilities,
            metadata=data.get("metadata", {}),
            schema_version=data.get("schema_version", "agentos.node-capability-manifest/v1"),
        )

    @staticmethod
    def _checkpoint_payload(checkpoint: OnboardingCheckpoint) -> str:
        payload = asdict(checkpoint)
        payload["lifecycle"] = checkpoint.lifecycle.value
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _parse_checkpoint(payload: str) -> OnboardingCheckpoint:
        data = json.loads(payload)
        data["lifecycle"] = NodeLifecycle(data["lifecycle"])
        return OnboardingCheckpoint(**data)

    def save_manifest(self, manifest: NodeCapabilityManifest) -> str:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO node_manifests(manifest_id, node_id, observed_at, payload_json) VALUES (?, ?, ?, ?)",
                (manifest.manifest_id, manifest.identity.node_id, manifest.observed_at, self._manifest_payload(manifest)),
            )
        return manifest.manifest_id

    def initialize_node(self, checkpoint: OnboardingCheckpoint) -> None:
        with self._connect() as db:
            existing = db.execute("SELECT 1 FROM node_heads WHERE node_id = ?", (checkpoint.node_id,)).fetchone()
            if existing is not None:
                raise ValueError(f"Node already initialized: {checkpoint.node_id}")
            db.execute(
                "INSERT INTO node_heads(node_id, manifest_id, checkpoint_json) VALUES (?, ?, ?)",
                (checkpoint.node_id, checkpoint.capability_manifest_id, self._checkpoint_payload(checkpoint)),
            )

    def advance(self, checkpoint: OnboardingCheckpoint) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT checkpoint_json FROM node_heads WHERE node_id = ?", (checkpoint.node_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown Node: {checkpoint.node_id}")
            current = self._parse_checkpoint(row["checkpoint_json"])
            validate_transition(current.lifecycle, checkpoint.lifecycle)
            if checkpoint.lifecycle is NodeLifecycle.ACTIVE and not checkpoint.governance_ref:
                raise PermissionError("ACTIVE checkpoint requires governance_ref")
            db.execute(
                "UPDATE node_heads SET manifest_id = ?, checkpoint_json = ? WHERE node_id = ?",
                (checkpoint.capability_manifest_id, self._checkpoint_payload(checkpoint), checkpoint.node_id),
            )

    def checkpoint(self, node_id: str) -> OnboardingCheckpoint | None:
        with self._connect() as db:
            row = db.execute("SELECT checkpoint_json FROM node_heads WHERE node_id = ?", (node_id,)).fetchone()
        return self._parse_checkpoint(row["checkpoint_json"]) if row else None

    def latest_manifest(self, node_id: str) -> NodeCapabilityManifest | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT m.payload_json
                FROM node_heads h JOIN node_manifests m ON h.manifest_id = m.manifest_id
                WHERE h.node_id = ?
                """,
                (node_id,),
            ).fetchone()
        return self._parse_manifest(row["payload_json"]) if row else None

    def node_ids(self) -> tuple[str, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT node_id FROM node_heads ORDER BY node_id").fetchall()
        return tuple(row["node_id"] for row in rows)

    def nodes_with_capability(self, capability: str) -> tuple[str, ...]:
        matches: list[str] = []
        for node_id in self.node_ids():
            manifest = self.latest_manifest(node_id)
            if manifest and manifest.capability(capability) is not None:
                matches.append(node_id)
        return tuple(matches)
