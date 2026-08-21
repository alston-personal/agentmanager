#!/usr/bin/env python3
"""Run the Distributed AgentOS Agent Provider Bridge.

Provider routes are non-secret JSON. Each route points to environment-variable
names for credentials so API keys are never persisted in the registry/config.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agentos_node.provider_bridge import (
    AgentProviderBridge,
    GeminiGenerateContentProvider,
    OpenAICompatibleChatProvider,
    OpenAIResponsesProvider,
    ProviderRegistry,
    RelayWebhookProvider,
)
from agentos_node.provider_bridge_server import ProviderBridgeServer


def _load_routes(path: str | None, inline: str | None) -> list[dict[str, Any]]:
    if path and inline:
        raise ValueError("provide only one of --routes-file or AGENTOS_PROVIDER_ROUTES_JSON")
    if path:
        raw = Path(path).read_text(encoding="utf-8")
    elif inline:
        raw = inline
    else:
        raise ValueError("provider routes are required")
    value = json.loads(raw)
    if not isinstance(value, list) or not value:
        raise ValueError("provider routes must be a non-empty JSON array")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("every provider route must be an object")
    return value


def _env_secret(route: dict[str, Any], field: str, default_env: str | None = None) -> str:
    if field.replace("_env", "") in route:
        raise ValueError("provider route must reference secrets by env name, not embed secret values")
    env_name = route.get(field) or default_env
    return os.getenv(str(env_name), "") if env_name else ""


def build_registry(routes: list[dict[str, Any]]) -> ProviderRegistry:
    registry = ProviderRegistry()
    for route in routes:
        provider_id = str(route.get("provider_id") or "")
        kind = str(route.get("kind") or "")
        model = str(route.get("model") or "")
        capabilities = route.get("capabilities") or []
        priority = int(route.get("priority", 100))
        timeout = float(route.get("timeout_seconds", 90))
        if not provider_id or not kind:
            raise ValueError("provider_id and kind are required")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) and item for item in capabilities):
            raise ValueError(f"provider {provider_id} capabilities must be non-empty strings")

        if kind == "openai_responses":
            api_key = _env_secret(route, "api_key_env", "OPENAI_API_KEY")
            adapter = OpenAIResponsesProvider(
                provider_id,
                model=model,
                api_key=api_key,
                base_url=str(route.get("base_url") or "https://api.openai.com/v1"),
                timeout=timeout,
            )
        elif kind == "openai_chat":
            api_key = _env_secret(route, "api_key_env", "AI_API_ACADEMIA_KEY")
            base_url = str(route.get("base_url") or os.getenv("AI_API_BASE_URL") or "")
            adapter = OpenAICompatibleChatProvider(
                provider_id,
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
        elif kind == "gemini_generate_content":
            api_key = _env_secret(route, "api_key_env", "GEMINI_API_KEY")
            adapter = GeminiGenerateContentProvider(
                provider_id,
                model=model,
                api_key=api_key,
                base_url=str(route.get("base_url") or "https://generativelanguage.googleapis.com/v1beta"),
                timeout=timeout,
            )
        elif kind == "relay_webhook":
            token = _env_secret(route, "token_env") or None
            adapter = RelayWebhookProvider(
                provider_id,
                endpoint=str(route.get("endpoint") or ""),
                token=token,
                timeout=timeout,
                allow_insecure_http=bool(route.get("allow_insecure_http", False)),
            )
        else:
            raise ValueError(f"unsupported provider kind: {kind}")

        registry.register(adapter, capabilities, priority=priority)
    return registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("AGENTOS_PROVIDER_BRIDGE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AGENTOS_PROVIDER_BRIDGE_PORT", "8775")))
    parser.add_argument("--runtime-id", default=os.getenv("AGENTOS_PROVIDER_RUNTIME_ID", "provider-bridge"))
    parser.add_argument("--control-plane-url", default=os.getenv("AGENTOS_CONTROL_PLANE_PUBLIC_URL"))
    parser.add_argument("--routes-file", default=os.getenv("AGENTOS_PROVIDER_ROUTES_FILE"))
    parser.add_argument("--lease-seconds", type=int, default=int(os.getenv("AGENTOS_PROVIDER_LEASE_SECONDS", "300")))
    parser.add_argument("--max-workers", type=int, default=int(os.getenv("AGENTOS_PROVIDER_MAX_WORKERS", "4")))
    parser.add_argument("--allow-insecure-control-plane", action="store_true")
    args = parser.parse_args()

    try:
        routes = _load_routes(args.routes_file, os.getenv("AGENTOS_PROVIDER_ROUTES_JSON"))
        registry = build_registry(routes)
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    bridge = AgentProviderBridge(
        args.runtime_id,
        registry,
        control_plane_url=args.control_plane_url,
        control_plane_token=os.getenv("AGENTOS_CONTROL_PLANE_TOKEN"),
        lease_seconds=args.lease_seconds,
        allow_insecure_control_plane=args.allow_insecure_control_plane,
    )
    server = ProviderBridgeServer(
        (args.host, args.port),
        bridge,
        token=os.getenv("AGENTOS_PROVIDER_BRIDGE_TOKEN"),
        max_workers=args.max_workers,
    )
    print(
        f"AgentOS Provider Bridge listening on http://{args.host}:{args.port} "
        f"runtime={args.runtime_id} providers={len(registry.describe())} "
        f"capabilities={','.join(registry.capabilities)}"
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
