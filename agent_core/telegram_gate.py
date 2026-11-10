from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("TelegramGate")

AGENTMANAGER_ROOT = Path(os.environ.get("AGENTMANAGER_ROOT", "/home/ubuntu/agentmanager"))
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
RECEIPT_LOG = AGENT_DATA_ROOT / "logs" / "telegram_receipts.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_current_node_id() -> str:
    """Resolve current machine node id from environment, fabric or hostname."""
    env_node = os.environ.get("AGENTOS_NODE_ID")
    if env_node:
        return env_node.strip()

    # Check fabric local state if present
    fabric_path = AGENT_DATA_ROOT / "realm" / "nodes.json"
    if fabric_path.exists():
        try:
            data = json.loads(fabric_path.read_text(encoding="utf-8"))
            nodes = data.get("nodes", {})
            import platform
            hostname = platform.node().lower()
            for nid, nmeta in nodes.items():
                if nmeta.get("hostname", "").lower() == hostname or nid.lower() == hostname:
                    return nid
        except Exception:
            pass

    import platform
    return platform.node() or "unknown-node"


def is_one_core_runtime() -> tuple[bool, str]:
    """
    Enforce that ONLY the designated AgentOS ONE core runtime node can communicate with Telegram.
    Secondary nodes, client clones, and test boxes are fenced out to prevent duplicate message storms.
    """
    # Explicit master override
    explicit_gate = os.environ.get("AGENTOS_TELEGRAM_GATEWAY_ENABLED")
    if explicit_gate is not None:
        if explicit_gate.lower() in ("0", "false", "no", "disabled"):
            return False, "explicitly_disabled_by_env"
        if explicit_gate.lower() in ("1", "true", "yes", "enabled"):
            return True, "explicitly_enabled_by_env"

    node_id = resolve_current_node_id()

    # The canonical Core node is oracle-core-node
    if node_id == "oracle-core-node" or os.environ.get("AGENTOS_ONE_RUNTIME") == "true":
        return True, f"core_node_match:{node_id}"

    # Check node role in Realm nodes.json
    fabric_path = AGENT_DATA_ROOT / "realm" / "nodes.json"
    if fabric_path.exists():
        try:
            data = json.loads(fabric_path.read_text(encoding="utf-8"))
            node_entry = data.get("nodes", {}).get(node_id, {})
            if node_entry.get("role") == "core":
                return True, f"core_role_match:{node_id}"
        except Exception:
            pass

    # If local tg_bridge service (Port 8085) is verified running on loopback, allow local dispatch
    try:
        resp = requests.get("http://127.0.0.1:8085/health", timeout=1)
        if resp.status_code == 200:
            return True, "local_tg_bridge_active"
    except Exception:
        pass

    return False, f"non_core_node_fenced:{node_id}"


def record_local_receipt(message: str, reason: str, metadata: dict[str, Any] | None = None) -> None:
    try:
        RECEIPT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": _utc_now(),
            "node_id": resolve_current_node_id(),
            "reason": reason,
            "message_chars": len(message),
            "summary": message[:120],
            "metadata": metadata or {},
        }
        with open(RECEIPT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning(f"Failed to record telegram receipt: {exc}")


def send_governed_telegram(
    message: str,
    *,
    project_name: str | None = None,
    interactive: bool = False,
    parse_mode: str = "Markdown",
) -> bool:
    """
    Governed Telegram dispatch entry-point.
    Enforces that only AgentOS ONE runtime executes outbound Telegram deliveries.
    """
    allowed, reason = is_one_core_runtime()
    if not allowed:
        logger.info(
            f"🚫 [Telegram Gate] Outbound message blocked ({reason}). Notification preserved locally."
        )
        record_local_receipt(message, reason=reason, metadata={"project_name": project_name})
        return False

    payload = {"message": message}
    if project_name:
        payload["project_name"] = project_name
    if interactive:
        payload["interactive"] = True

    # Method 1: Local HTTP Bridge (provided by tg_bridge.py, default port 8085)
    try:
        res = requests.post("http://127.0.0.1:8085/alert", json=payload, timeout=5)
        if res.status_code == 200:
            logger.info("✅ Governed Telegram sent via local HTTP Bridge.")
            return True
    except Exception:
        pass

    # Method 2: Direct Telegram API fallback (Only for ONE Core Runtime)
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_SUNLAKE_CC_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if bot_token and channel_id:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            direct_payload = {
                "chat_id": channel_id,
                "text": message,
                "parse_mode": parse_mode,
            }
            res = requests.post(url, json=direct_payload, timeout=10)
            if res.status_code == 200:
                logger.info("✅ Governed Telegram sent via direct Telegram API fallback.")
                return True
            else:
                logger.error(f"❌ Telegram API returned error: {res.text}")
        except Exception as ex:
            logger.error(f"❌ Telegram API direct call failed: {ex}")
    else:
        logger.warning("⚠️ Governed Telegram missing credentials in environment.")

    record_local_receipt(message, reason="dispatch_fallback_exhausted", metadata={"project_name": project_name})
    return False
