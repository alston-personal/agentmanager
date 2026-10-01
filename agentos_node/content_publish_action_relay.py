"""Bounded ubuntu-owned Action Relay probe for legacy ZeusWriter X auth.

This action accepts only an optional expected username. Credential path, keys,
HTTP endpoint and probe implementation are source-owned. No caller shell, path,
token, cookie, or endpoint is accepted.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from agentos_node.action_relay import ACTIONS, ActionRelayClient
from runtime_core.x_auth_probe import CREDENTIAL_KEYS, inspect_x_auth


ACTION = "agentos.content.x.auth.inspect"
CAPABILITY = "content.publish.x.auth.inspect"
DEFAULT_RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/action-relay")
LEGACY_ENV = Path("/home/ubuntu/zeus-writer/.env")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{0,50}$")


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
        value = value[1:-1]
    return value


def _load_credentials(path: Path = LEGACY_ENV) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    wanted = set(CREDENTIAL_KEYS)
    found: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in wanted:
            found[key] = _parse_env_value(value)
    return found


def _expected_username(params: Mapping[str, Any]) -> str:
    if set(params) - {"expected_username"}:
        raise ValueError("x-auth inspect accepts only expected_username")
    value = str(params.get("expected_username") or "").strip().lstrip("@")
    if not _USERNAME_RE.fullmatch(value):
        raise ValueError("expected_username invalid")
    return value


def inspect_legacy_x_auth(
    params: Mapping[str, Any],
    *,
    env_path: Path = LEGACY_ENV,
) -> dict[str, Any]:
    expected = _expected_username(params)
    try:
        credentials = _load_credentials(env_path)
    except (OSError, UnicodeError):
        credentials = {}
    result = inspect_x_auth(credentials, expected_username=expected)
    return {
        "ok": result.get("authentication_success") is True,
        "capability": CAPABILITY,
        "status": result.get("status"),
        "authentication_status": result.get("authentication_status"),
        "authentication_success": bool(result.get("authentication_success")),
        "credential_presence": dict(result.get("credential_presence") or {}),
        "write_entitlement": result.get("write_entitlement", "UNKNOWN"),
        "media_entitlement": result.get("media_entitlement", "UNKNOWN"),
        "account_identity": result.get("account_identity"),
        "reason": result.get("reason"),
        "http_status": result.get("http_status"),
        "credential_exposed": False,
        "side_effect": False,
        "credential_source": "legacy-zeus-writer-node-local",
    }


def _execute(params: dict[str, Any]) -> dict[str, Any]:
    return inspect_legacy_x_auth(params)


if ACTION in ACTIONS and ACTIONS[ACTION] is not _execute:
    raise RuntimeError("content-publish X auth action already registered differently")
ACTIONS[ACTION] = _execute


class ContentPublishXAuthDispatcher:
    def __init__(self, root: str | Path = DEFAULT_RELAY_ROOT):
        self.root = Path(root)
        self.client = ActionRelayClient(self.root)

    def submit(self, *, expected_username: str = "") -> dict[str, Any]:
        params = {"expected_username": str(expected_username or "").strip()}
        _expected_username(params)
        capsule = self.client.submit(ACTION, params)
        return {
            "schema": "agentos.content-x-auth-submission/v1",
            "ok": True,
            "action": CAPABILITY,
            "task_id": str(capsule["capsule_id"]),
            "state": "queued",
        }

    def inspect(self, task_id: str) -> dict[str, Any] | None:
        receipt = self.client.receipt(str(task_id))
        if receipt is None:
            return None
        if receipt.get("action") not in (None, ACTION):
            raise RuntimeError("content_x_auth_receipt_action_mismatch")
        return {
            "schema": "agentos.content-x-auth-receipt/v1",
            "task_id": str(task_id),
            "action": CAPABILITY,
            "executor_user": receipt.get("executor_user"),
            "status": receipt.get("status"),
            "authentication_status": receipt.get("authentication_status"),
            "authentication_success": bool(receipt.get("authentication_success")),
            "credential_presence": dict(receipt.get("credential_presence") or {}),
            "write_entitlement": receipt.get("write_entitlement", "UNKNOWN"),
            "media_entitlement": receipt.get("media_entitlement", "UNKNOWN"),
            "account_identity": receipt.get("account_identity"),
            "reason": receipt.get("reason"),
            "http_status": receipt.get("http_status"),
            "credential_exposed": False,
            "side_effect": False,
        }
