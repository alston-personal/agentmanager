"""Plan post-join experience recovery from explicitly harvestable executors."""
from __future__ import annotations

from typing import Any

from agentos_node.session_bridge import FileSessionBridge


SCHEMA = "agentos.executor-experience-recovery/v1"
HARVEST_CAPABILITY = "agent.context.harvest"


def plan_executor_experience_recovery(manifest: dict[str, Any]) -> dict[str, Any]:
    """Classify Node surfaces without scraping any private executor history.

    A provider is eligible only when its own manifest declares a ready session
    bridge with the harvest operation. Process presence alone is never access.
    """
    inventory = manifest.get("surface_inventory") if isinstance(manifest, dict) else {}
    surfaces = inventory.get("surfaces") if isinstance(inventory, dict) else []
    entries: list[dict[str, Any]] = []
    for surface in surfaces if isinstance(surfaces, list) else []:
        if not isinstance(surface, dict):
            continue
        provider = str(surface.get("provider") or "").strip()
        if not provider:
            continue
        caps = {str(item) for item in (surface.get("capabilities") or [])}
        running = bool(surface.get("running"))
        eligible = running and HARVEST_CAPABILITY in caps
        entries.append({
            "provider": provider,
            "surface_id": surface.get("surface_id"),
            "running": running,
            "harvest_declared": HARVEST_CAPABILITY in caps,
            "eligible": eligible,
            "reason": "eligible_for_governed_harvest" if eligible else (
                "executor_not_running" if not running else "no_declared_harvest_bridge"
            ),
        })
    return {
        "schema": SCHEMA,
        "node_id": manifest.get("node_id"),
        "executors": entries,
        "eligible_providers": [item["provider"] for item in entries if item["eligible"]],
        "harvest_requests_enqueued": 0,
        "experience_promoted": 0,
        "promotion_requires_governed_evidence": True,
        "raw_conversation_scraped": False,
        "credential_exposed": False,
    }


def enqueue_executor_experience_harvest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Queue one bounded, summary-only harvest request for each eligible executor.

    The provider owns any private conversation history and must return only
    approved summary-derived Historical IR.  This function never reads chats,
    waits for a provider, or promotes an Experience.
    """
    report = plan_executor_experience_recovery(manifest)
    requests: list[dict[str, Any]] = []
    for provider in report["eligible_providers"]:
        request = FileSessionBridge.from_environment(provider).request(
            "harvest",
            payload={
                "schema": "agentos.experience-harvest-request/v1",
                "output_schema": "agentos.historical-ir/v1",
                "summary_only": True,
                "raw_conversation_allowed": False,
                "credential_exposed": False,
                "max_items": 100,
            },
        )
        requests.append({"provider": provider, "request_id": request["request_id"]})
    report["harvest_requests_enqueued"] = len(requests)
    report["harvest_requests"] = requests
    return report
