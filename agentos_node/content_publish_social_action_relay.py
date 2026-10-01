"""Host-local Social Runtime consumer bootstrap for content.publish.

The fixed actions in this module never accept token values, file paths, provider
URLs, shell commands, or arbitrary product IDs. They move an existing
ZeusWriter Threads credential into the shared Social Runtime vault under a
product-specific binding, then expose only a sanitized account-registry view.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Mapping
import urllib.error
import urllib.request

from agentos_node.action_relay import ACTIONS, ActionRelayClient
from agentos_node.social.credentials import AccountBinding
from agentos_node.social.runtime_storage import FileCredentialVault
from agentos_node.social.threads import (
    ThreadsProviderConfig,
    ThreadsProviderTransport,
    ThreadsProviderError,
)
from scripts.social_runtime_local_config import register_product


BOOTSTRAP_ACTION = "agentos.content.social.bootstrap"
INSPECT_ACTION = "agentos.content.social.inspect"
BOOTSTRAP_CAPABILITY = "content.publish.social.bootstrap"
INSPECT_CAPABILITY = "content.publish.social.inspect"
DEFAULT_RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/action-relay")
SOURCE_ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_CONFIG = SOURCE_ROOT / "config/content_publish_accounts.json"
LEGACY_ENV = Path("/home/ubuntu/zeus-writer/.env")
SOCIAL_ENV = Path("/home/ubuntu/.config/agentos/social-runtime.env")
SOCIAL_PRODUCT_DIR = Path("/home/ubuntu/.config/agentos/social-products")
SOCIAL_VAULT = Path("/home/ubuntu/.local/state/agentos/social/credentials.json")
ACCOUNT_REGISTRY = Path("/home/ubuntu/.config/agentos/content-publish/accounts.json")
SOCIAL_BASE = "http://127.0.0.1:8771"
PRODUCT_RETURN_BASE = "https://studio.milkcat.org"
_ALLOWED_ACCOUNT_REF = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def _parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _load_account_config(account_ref: str) -> dict[str, Any]:
    value = str(account_ref or "").strip()
    if not _ALLOWED_ACCOUNT_REF.fullmatch(value):
        raise ValueError("content_publish_account_ref_invalid")
    raw = json.loads(ACCOUNT_CONFIG.read_text(encoding="utf-8"))
    if raw.get("schema") != "agentos.content-publish-account-config/v1":
        raise RuntimeError("content_publish_account_config_schema_invalid")
    item = (raw.get("accounts") or {}).get(value)
    if not isinstance(item, dict):
        raise ValueError("content_publish_account_not_registered")
    if item.get("platform") != "threads" or item.get("product_id") != "content-publish":
        raise RuntimeError("content_publish_account_config_not_allowlisted")
    bootstrap = item.get("bootstrap")
    if not isinstance(bootstrap, dict) or bootstrap.get("kind") != "legacy-zeus-writer-env":
        raise RuntimeError("content_publish_account_bootstrap_not_allowlisted")
    if bootstrap.get("env_key") != "SOC_THREADS_TOKEN":
        raise RuntimeError("content_publish_account_bootstrap_key_not_allowlisted")
    return {"account_ref": value, **item}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    os.chmod(path, 0o600)


def _load_registry() -> dict[str, Any]:
    if not ACCOUNT_REGISTRY.is_file():
        return {"schema": "agentos.content-publish-account-registry/v1", "accounts": {}}
    value = json.loads(ACCOUNT_REGISTRY.read_text(encoding="utf-8"))
    if value.get("schema") != "agentos.content-publish-account-registry/v1" or not isinstance(value.get("accounts"), dict):
        raise RuntimeError("content_publish_account_registry_invalid")
    return value


def _threads_transport(env: Mapping[str, str]) -> ThreadsProviderTransport:
    config = ThreadsProviderConfig(
        app_id=str(env.get("AGENTOS_THREADS_APP_ID") or ""),
        app_secret=str(env.get("AGENTOS_THREADS_APP_SECRET") or ""),
        redirect_uri=str(env.get("AGENTOS_THREADS_REDIRECT_URI") or ""),
    )
    return ThreadsProviderTransport(lambda: config)


def _restart_social_runtime() -> None:
    restart = subprocess.run(
        ["systemctl", "--user", "--no-block", "restart", "agentos-social-runtime.service"],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if restart.returncode != 0:
        raise RuntimeError("social_runtime_restart_failed")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(SOCIAL_BASE + "/healthz", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("service") == "agentos-social-runtime":
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("social_runtime_restart_timeout")


def _product_key(product_id: str) -> str:
    path = SOCIAL_PRODUCT_DIR / f"{product_id}.env"
    env = _parse_env(path)
    if env.get("AGENTOS_SOCIAL_PRODUCT_ID") != product_id:
        raise RuntimeError("social_product_secret_identity_mismatch")
    key = str(env.get("AGENTOS_SOCIAL_PRODUCT_KEY") or "")
    if not key:
        raise RuntimeError("social_product_key_unavailable")
    return key


def _post_runtime(path: str, payload: Mapping[str, Any], *, product_key: str) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        SOCIAL_BASE + path,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-AgentOS-Product-Key": product_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"social_runtime_http_{int(exc.code)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("social_runtime_unreachable") from exc
    if not isinstance(value, dict):
        raise RuntimeError("social_runtime_response_invalid")
    return value


def bootstrap_account(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params) != {"account_ref"}:
        raise ValueError("content_publish_bootstrap_accepts_only_account_ref")
    cfg = _load_account_config(str(params.get("account_ref") or ""))
    legacy = _parse_env(LEGACY_ENV)
    token = str(legacy.get("SOC_THREADS_TOKEN") or "").strip()
    if not token:
        return {
            "ok": False,
            "capability": BOOTSTRAP_CAPABILITY,
            "account_ref": cfg["account_ref"],
            "status": "AUTH_REQUIRED",
            "credential_exposed": False,
            "side_effect": False,
        }

    social_env = _parse_env(SOCIAL_ENV)
    transport = _threads_transport(social_env)
    try:
        identity = transport.identity(token)
    except ThreadsProviderError:
        return {
            "ok": False,
            "capability": BOOTSTRAP_CAPABILITY,
            "account_ref": cfg["account_ref"],
            "status": "AUTH_REQUIRED",
            "credential_exposed": False,
            "side_effect": False,
        }

    provider_account_id = str(identity.get("id") or "").strip()
    username = str(identity.get("username") or "").strip()
    expected = str(cfg.get("expected_username") or "").lstrip("@")
    if not provider_account_id or not username:
        raise RuntimeError("content_publish_threads_identity_missing")
    if expected and username.casefold() != expected.casefold():
        return {
            "ok": False,
            "capability": BOOTSTRAP_CAPABILITY,
            "account_ref": cfg["account_ref"],
            "status": "PERMISSION_DENIED",
            "observed_username": username,
            "credential_exposed": False,
            "side_effect": False,
        }

    created, _secret_path = register_product(
        "content-publish",
        PRODUCT_RETURN_BASE,
        env_file=SOCIAL_ENV,
        product_secret_dir=SOCIAL_PRODUCT_DIR,
    )
    binding_id = f"content-publish:threads:{cfg.get('auth_profile') or 'persona'}:{provider_account_id}"
    vault = FileCredentialVault(SOCIAL_VAULT)
    vault.bind(
        AccountBinding(
            binding_id=binding_id,
            product_id="content-publish",
            platform="threads",
            provider_account_id=provider_account_id,
            username=username,
            auth_profile=str(cfg.get("auth_profile") or "persona"),
        ),
        token,
    )

    registry = _load_registry()
    registry["accounts"][cfg["account_ref"]] = {
        "platform": "threads",
        "product_id": "content-publish",
        "binding_id": binding_id,
        "provider_account_id": provider_account_id,
        "username": username,
        "auth_profile": str(cfg.get("auth_profile") or "persona"),
        "credential_exposed": False,
    }
    _atomic_json(ACCOUNT_REGISTRY, registry)
    _restart_social_runtime()

    return {
        "ok": True,
        "capability": BOOTSTRAP_CAPABILITY,
        "account_ref": cfg["account_ref"],
        "status": "BOUND",
        "product_id": "content-publish",
        "binding_id": binding_id,
        "provider_account_id": provider_account_id,
        "username": username,
        "product_registration": "CREATED" if created else "PRESERVED",
        "credential_exposed": False,
        "side_effect": False,
    }


def inspect_account(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params) != {"account_ref"}:
        raise ValueError("content_publish_inspect_accepts_only_account_ref")
    cfg = _load_account_config(str(params.get("account_ref") or ""))
    registry = _load_registry()
    item = registry["accounts"].get(cfg["account_ref"])
    if not isinstance(item, dict):
        return {
            "ok": False,
            "capability": INSPECT_CAPABILITY,
            "account_ref": cfg["account_ref"],
            "status": "AUTH_REQUIRED",
            "credential_exposed": False,
            "side_effect": False,
        }
    if item.get("product_id") != "content-publish" or item.get("platform") != "threads":
        raise RuntimeError("content_publish_account_registry_scope_invalid")

    request = {
        "schema": "agentos.social-request/v1",
        "product_id": "content-publish",
        "platform": "threads",
        "operation": "identity.read",
        "account_binding_id": str(item.get("binding_id") or ""),
    }
    receipt = _post_runtime(
        "/v1/social/status",
        request,
        product_key=_product_key("content-publish"),
    )
    result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
    identity = result.get("identity") if isinstance(result.get("identity"), dict) else {}
    username = str(identity.get("username") or item.get("username") or "")
    expected = str(cfg.get("expected_username") or "").lstrip("@")
    if receipt.get("ok") is not True:
        status = "AUTH_REQUIRED"
    elif expected and username.casefold() != expected.casefold():
        status = "PERMISSION_DENIED"
    else:
        status = "AUTHENTICATED"

    return {
        "ok": status == "AUTHENTICATED",
        "capability": INSPECT_CAPABILITY,
        "account_ref": cfg["account_ref"],
        "status": status,
        "product_id": "content-publish",
        "binding_id": str(item.get("binding_id") or ""),
        "provider_account_id": str(identity.get("provider_account_id") or item.get("provider_account_id") or ""),
        "username": username,
        "write_entitlement": "UNKNOWN",
        "credential_exposed": False,
        "side_effect": False,
    }


def _bootstrap_execute(params: dict[str, Any]) -> dict[str, Any]:
    return bootstrap_account(params)


def _inspect_execute(params: dict[str, Any]) -> dict[str, Any]:
    return inspect_account(params)


for action, fn in (
    (BOOTSTRAP_ACTION, _bootstrap_execute),
    (INSPECT_ACTION, _inspect_execute),
):
    if action in ACTIONS and ACTIONS[action] is not fn:
        raise RuntimeError("content-publish social action already registered differently")
    ACTIONS[action] = fn


class ContentPublishSocialDispatcher:
    def __init__(self, root: str | Path = DEFAULT_RELAY_ROOT):
        self.root = Path(root)
        self.client = ActionRelayClient(self.root)

    def submit_bootstrap(self, *, account_ref: str) -> dict[str, Any]:
        capsule = self.client.submit(BOOTSTRAP_ACTION, {"account_ref": account_ref})
        return {"task_id": str(capsule["capsule_id"]), "action": BOOTSTRAP_CAPABILITY, "state": "queued"}

    def submit_inspect(self, *, account_ref: str) -> dict[str, Any]:
        capsule = self.client.submit(INSPECT_ACTION, {"account_ref": account_ref})
        return {"task_id": str(capsule["capsule_id"]), "action": INSPECT_CAPABILITY, "state": "queued"}

    def inspect(self, task_id: str) -> dict[str, Any] | None:
        receipt = self.client.receipt(str(task_id))
        if receipt is None:
            return None
        action = str(receipt.get("action") or "")
        if action not in {BOOTSTRAP_ACTION, INSPECT_ACTION}:
            raise RuntimeError("content_publish_social_receipt_action_mismatch")
        allowed = {
            "ok", "capability", "account_ref", "status", "product_id", "binding_id",
            "provider_account_id", "username", "product_registration",
            "write_entitlement", "credential_exposed", "side_effect", "executor_user",
        }
        result = {key: receipt.get(key) for key in allowed if key in receipt}
        result["task_id"] = str(task_id)
        result["credential_exposed"] = False
        result["side_effect"] = False
        return result
