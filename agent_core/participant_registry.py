from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SUPPORTED_PROTOCOL_VERSIONS = ("1.0",)
REQUIRED_V1_METHODS = ("describe", "probe", "invoke", "status", "receipt", "shutdown")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _user_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


class ParticipantRegistry:
    """ONE-side enrollment/negotiation state for generic Participants.

    This store deliberately does not execute provider-specific logic. A Host
    Runtime may carry transport on behalf of a hosted Participant, but the
    Participant keeps its own stable logical identity.
    """

    def __init__(self, path: str | Path | None = None):
        data_root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
        self.path = Path(path) if path else data_root / "runtime" / "participants.json"

    def _empty(self) -> dict[str, Any]:
        return {
            "schema": "agentos.participant-registry/v1",
            "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "join_requests": {},
            "participants": {},
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema") != "agentos.participant-registry/v1":
            raise ValueError(f"invalid Participant registry: {self.path}")
        data.setdefault("supported_protocol_versions", list(SUPPORTED_PROTOCOL_VERSIONS))
        data.setdefault("join_requests", {})
        data.setdefault("participants", {})
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def _normalize_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        participant = dict(manifest.get("participant") or {})
        participant_id = str(participant.get("id") or "").strip()
        instance_id = str(participant.get("instance_id") or "").strip()
        roles = [str(x).strip() for x in (participant.get("roles") or []) if str(x).strip()]
        if not participant_id:
            raise ValueError("participant.id is required")
        if not instance_id:
            raise ValueError("participant.instance_id is required")
        if not roles:
            raise ValueError("participant.roles must not be empty")

        protocol = dict(manifest.get("protocol") or {})
        if protocol.get("name") != "agentos-participant":
            raise ValueError("protocol.name must be agentos-participant")
        supported = [str(x) for x in (protocol.get("supported") or []) if str(x)]
        if not supported:
            raise ValueError("protocol.supported must not be empty")

        adapter = dict(manifest.get("adapter") or {})
        if not str(adapter.get("name") or "").strip():
            raise ValueError("adapter.name is required")
        if not str(adapter.get("version") or "").strip():
            raise ValueError("adapter.version is required")

        normalized = dict(manifest)
        normalized["participant"] = {**participant, "id": participant_id, "instance_id": instance_id, "roles": roles}
        normalized["protocol"] = {**protocol, "supported": supported, "negotiated": None}
        normalized.setdefault("methods", {})
        normalized.setdefault("capabilities", {})
        normalized.setdefault("features", {})
        normalized.setdefault("requirements", [])
        normalized.setdefault("relationships", [])
        normalized.setdefault("health", {"observable": False})
        normalized.setdefault("receipt", {"supported": True})
        return normalized

    def _negotiate(self, manifest: dict[str, Any]) -> str:
        participant_supported = set(manifest["protocol"]["supported"])
        common = [v for v in SUPPORTED_PROTOCOL_VERSIONS if v in participant_supported]
        if not common:
            raise ValueError("NO_COMMON_PROTOCOL_VERSION")
        return common[-1]

    def request_join(
        self,
        *,
        manifest: dict[str, Any],
        host_runtime_id: str,
        expires_minutes: int = 10,
    ) -> dict[str, Any]:
        data = self.load()
        normalized = self._normalize_manifest(manifest)
        participant_id = normalized["participant"]["id"]
        existing = data["participants"].get(participant_id)
        if existing and not existing.get("revoked_at"):
            raise ValueError("participant already enrolled")

        request_id = "pjoin_" + secrets.token_hex(10)
        claim_secret = secrets.token_urlsafe(32)
        challenge = secrets.token_urlsafe(24)
        user_code = _user_code()
        existing_codes = {str(v.get("user_code") or "") for v in data["join_requests"].values()}
        while user_code in existing_codes:
            user_code = _user_code()

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=max(1, min(int(expires_minutes), 30)))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        negotiated = self._negotiate(normalized)
        data["join_requests"][request_id] = {
            "request_id": request_id,
            "participant_id": participant_id,
            "host_runtime_id": str(host_runtime_id or "").strip(),
            "manifest": normalized,
            "negotiated_protocol": negotiated,
            "challenge": challenge,
            "challenge_verified_at": None,
            "challenge_response_digest": None,
            "claim_secret_hash": _hash_secret(claim_secret),
            "user_code": user_code,
            "created_at": _utc_now(),
            "expires_at": expires_at,
            "approved_at": None,
            "denied_at": None,
            "claimed_at": None,
        }
        self.save(data)
        return {
            "schema": "agentos.participant-join-request/v1",
            "request_id": request_id,
            "participant_id": participant_id,
            "user_code": user_code,
            "claim_secret": claim_secret,
            "challenge": challenge,
            "negotiated_protocol": negotiated,
            "status": "pending",
            "expires_at": expires_at,
        }

    def _find_join(self, data: dict[str, Any], selector: str) -> tuple[str, dict[str, Any]]:
        selector = str(selector or "").strip().upper()
        if not selector:
            raise ValueError("participant join selector is required")
        for request_id, entry in data["join_requests"].items():
            if request_id.upper() == selector or str(entry.get("user_code") or "").upper() == selector:
                return request_id, entry
        raise KeyError(selector)

    def verify_challenge(self, *, request_id: str, claim_secret: str, response: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        entry = data["join_requests"].get(request_id)
        if not entry or not secrets.compare_digest(str(entry.get("claim_secret_hash") or ""), _hash_secret(claim_secret)):
            raise PermissionError("invalid participant join credential")
        if _parse_utc(entry["expires_at"]) < datetime.now(timezone.utc):
            raise PermissionError("participant join request expired")
        if str(response.get("request_id") or "") != request_id:
            raise ValueError("challenge response request_id mismatch")
        if str(response.get("participant_id") or "") != entry["participant_id"]:
            raise ValueError("challenge response participant_id mismatch")
        if str(response.get("challenge") or "") != entry["challenge"]:
            raise ValueError("challenge response challenge mismatch")
        if str(response.get("protocol") or "") != f"agentos-participant/{entry['negotiated_protocol']}":
            raise ValueError("challenge response protocol mismatch")
        ack = str(response.get("ack") or "").strip()
        if ack != "ACCEPT":
            raise ValueError("challenge response ack must be ACCEPT")
        canonical = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        entry["challenge_verified_at"] = _utc_now()
        entry["challenge_response_digest"] = digest
        data["join_requests"][request_id] = entry
        self.save(data)
        return {
            "schema": "agentos.participant-challenge-verification/v1",
            "ok": True,
            "request_id": request_id,
            "participant_id": entry["participant_id"],
            "verified_at": entry["challenge_verified_at"],
            "response_digest": digest,
        }

    def approve_join(self, selector: str) -> dict[str, Any]:
        data = self.load()
        request_id, entry = self._find_join(data, selector)
        if entry.get("claimed_at"):
            raise ValueError("participant join request already claimed")
        if entry.get("denied_at"):
            raise ValueError("participant join request was denied")
        if _parse_utc(entry["expires_at"]) < datetime.now(timezone.utc):
            raise PermissionError("participant join request expired")
        entry["approved_at"] = entry.get("approved_at") or _utc_now()
        data["join_requests"][request_id] = entry
        self.save(data)
        return {
            "schema": "agentos.participant-join-approval/v1",
            "ok": True,
            "request_id": request_id,
            "participant_id": entry["participant_id"],
            "user_code": entry["user_code"],
            "approved_at": entry["approved_at"],
        }

    def join_status(self, *, request_id: str, claim_secret: str) -> dict[str, Any]:
        data = self.load()
        entry = data["join_requests"].get(request_id)
        if not entry or not secrets.compare_digest(str(entry.get("claim_secret_hash") or ""), _hash_secret(claim_secret)):
            raise PermissionError("invalid participant join credential")
        if entry.get("claimed_at"):
            status = "claimed"
        elif entry.get("denied_at"):
            status = "denied"
        elif _parse_utc(entry["expires_at"]) < datetime.now(timezone.utc):
            status = "expired"
        elif entry.get("approved_at"):
            status = "approved"
        else:
            status = "pending"
        return {
            "schema": "agentos.participant-join-status/v1",
            "request_id": request_id,
            "participant_id": entry["participant_id"],
            "status": status,
            "negotiated_protocol": entry["negotiated_protocol"],
        }

    def claim_join(self, *, request_id: str, claim_secret: str) -> dict[str, Any]:
        data = self.load()
        entry = data["join_requests"].get(request_id)
        if not entry or not secrets.compare_digest(str(entry.get("claim_secret_hash") or ""), _hash_secret(claim_secret)):
            raise PermissionError("invalid participant join credential")
        if entry.get("claimed_at"):
            raise PermissionError("participant join request already claimed")
        if entry.get("denied_at"):
            raise PermissionError("participant join request denied")
        if _parse_utc(entry["expires_at"]) < datetime.now(timezone.utc):
            raise PermissionError("participant join request expired")
        if not entry.get("approved_at"):
            return {
                "schema": "agentos.participant-join-status/v1",
                "request_id": request_id,
                "status": "pending",
            }

        if not entry.get("challenge_verified_at"):
            raise PermissionError("participant challenge not verified")
        token = secrets.token_urlsafe(32)
        participant_id = entry["participant_id"]
        manifest = dict(entry["manifest"])
        manifest["protocol"] = {**manifest["protocol"], "negotiated": entry["negotiated_protocol"]}
        missing_required_methods = [
            name
            for name in REQUIRED_V1_METHODS
            if not bool((manifest.get("methods") or {}).get(name, {}).get("implemented"))
        ]
        data["participants"][participant_id] = {
            "participant_id": participant_id,
            "instance_id": manifest["participant"]["instance_id"],
            "roles": manifest["participant"]["roles"],
            "host_runtime_id": entry.get("host_runtime_id"),
            "token_hash": _hash_secret(token),
            "manifest": manifest,
            "negotiated_protocol": entry["negotiated_protocol"],
            "enrolled_at": _utc_now(),
            "acceptance_level": "A3",
            "core_conformance": "pending",
            "capability_conformance": "pending",
            "missing_required_methods": missing_required_methods,
            "revoked_at": None,
        }
        entry["claimed_at"] = _utc_now()
        data["join_requests"][request_id] = entry
        self.save(data)
        return {
            "schema": "agentos.participant-enrollment-result/v1",
            "status": "enrolled",
            "participant_id": participant_id,
            "participant_token": token,
            "negotiated_protocol": entry["negotiated_protocol"],
            "acceptance_level": "A3",
            "missing_required_methods": missing_required_methods,
        }

    def authenticate(self, participant_id: str, token: str) -> dict[str, Any]:
        data = self.load()
        participant = data["participants"].get(participant_id)
        if not participant or participant.get("revoked_at"):
            raise PermissionError("unknown or revoked participant")
        if not secrets.compare_digest(str(participant.get("token_hash") or ""), _hash_secret(token)):
            raise PermissionError("invalid participant credential")
        return participant

    def describe(self, participant_id: str, token: str) -> dict[str, Any]:
        participant = self.authenticate(participant_id, token)
        return {
            "schema": "agentos.participant-record/v1",
            **{k: v for k, v in participant.items() if k != "token_hash"},
        }
