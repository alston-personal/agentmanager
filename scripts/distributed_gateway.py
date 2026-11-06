#!/usr/bin/env python3
"""Run the Distributed AgentOS Control Plane HTTP gateway."""

from __future__ import annotations

import argparse
import os
import threading

from agent_core.continuity_mirror import GitHubContinuityMirror, MirroringDispatchingGatewayService
from agent_core.dispatching_gateway import DispatchingGatewayService
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer
from agent_core.push_dispatch import ExactGitHubActionsDispatchTransport, ResilientRuntimeDispatcher
from agent_core.runtime_dispatcher import RuntimeTarget, WebhookDispatchTransport


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _enabled(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def _build_dispatcher(
    store: DistributedControlPlane,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> ResilientRuntimeDispatcher:
    dispatcher = ResilientRuntimeDispatcher(
        store,
        dispatch_timeout_seconds=args.dispatch_timeout_seconds,
        dispatch_retry_seconds=args.dispatch_retry_seconds,
    )

    if _enabled("AGENTOS_GITHUB_DISPATCH_ENABLED"):
        github_token = os.getenv("AGENTOS_GITHUB_TOKEN")
        if github_token:
            dispatcher.register_transport(ExactGitHubActionsDispatchTransport(github_token))

        if args.github_repository:
            capabilities = _csv(args.github_capabilities)
            missing = []
            if not github_token:
                missing.append("AGENTOS_GITHUB_TOKEN")
            if not args.public_url:
                missing.append("--public-url / AGENTOS_CONTROL_PLANE_PUBLIC_URL")
            if not capabilities:
                missing.append("--github-capabilities / AGENTOS_GITHUB_CAPABILITIES")
            if missing:
                parser.error("GitHub Actions dispatcher requires: " + ", ".join(missing))

            dispatcher.register_target(
                RuntimeTarget(
                    target_id=args.github_runtime_id,
                    kind="github_actions",
                    capabilities=capabilities,
                    priority=args.github_priority,
                    config={
                        "repository": args.github_repository,
                        "workflow": args.github_workflow,
                        "ref": args.github_ref,
                        "control_plane_url": args.public_url,
                    },
                )
            )

    if _enabled("AGENTOS_PROVIDER_DISPATCH_ENABLED") and args.provider_bridge_endpoint:
        capabilities = _csv(args.provider_capabilities)
        missing = []
        if not args.public_url:
            missing.append("--public-url / AGENTOS_CONTROL_PLANE_PUBLIC_URL")
        if not capabilities:
            missing.append("--provider-capabilities / AGENTOS_PROVIDER_CAPABILITIES")
        if missing:
            parser.error("Provider Bridge dispatcher requires: " + ", ".join(missing))

        bridge_token = os.getenv("AGENTOS_PROVIDER_BRIDGE_TOKEN")
        token_map = {args.provider_runtime_id: bridge_token} if bridge_token else {}
        dispatcher.register_transport(WebhookDispatchTransport(tokens=token_map))
        dispatcher.register_target(
            RuntimeTarget(
                target_id=args.provider_runtime_id,
                kind="webhook",
                capabilities=capabilities,
                priority=args.provider_priority,
                config={
                    "endpoint": args.provider_bridge_endpoint,
                    "control_plane_url": args.public_url,
                },
            )
        )
    return dispatcher


def _build_service(
    store: DistributedControlPlane,
    dispatcher: ResilientRuntimeDispatcher,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
):
    if not _enabled("AGENTOS_CONTINUITY_MIRROR_ENABLED"):
        return DispatchingGatewayService(store, dispatcher)
    if not args.continuity_mirror_repository:
        parser.error("continuity mirror requires AGENTOS_CONTINUITY_MIRROR_REPOSITORY")

    mirror_token = os.getenv("AGENTOS_CONTINUITY_MIRROR_TOKEN")
    if not mirror_token:
        parser.error("continuity mirror requires AGENTOS_CONTINUITY_MIRROR_TOKEN")
    mirror = GitHubContinuityMirror(
        args.continuity_mirror_repository,
        mirror_token,
        branch=args.continuity_mirror_branch,
        root=args.continuity_mirror_root,
    )
    return MirroringDispatchingGatewayService(store, dispatcher, mirror)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("AGENTOS_CONTROL_PLANE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AGENTOS_CONTROL_PLANE_PORT", "8765")))
    parser.add_argument("--db", default=os.getenv("AGENTOS_CONTROL_PLANE_DB"))
    parser.add_argument("--public-url", default=os.getenv("AGENTOS_CONTROL_PLANE_PUBLIC_URL"))
    parser.add_argument("--dispatch-timeout-seconds", type=int, default=120)
    parser.add_argument("--dispatch-retry-seconds", type=int, default=60)
    parser.add_argument(
        "--dispatch-interval-seconds",
        type=float,
        default=float(os.getenv("AGENTOS_DISPATCH_INTERVAL_SECONDS", "5")),
    )
    parser.add_argument(
        "--dispatch-limit",
        type=int,
        default=int(os.getenv("AGENTOS_DISPATCH_LIMIT", "100")),
    )

    parser.add_argument("--github-repository", default=os.getenv("AGENTOS_GITHUB_REPOSITORY"))
    parser.add_argument(
        "--github-workflow",
        default=os.getenv("AGENTOS_GITHUB_WORKFLOW", "distributed-agentos-worker.yml"),
    )
    parser.add_argument("--github-ref", default=os.getenv("AGENTOS_GITHUB_REF", "main"))
    parser.add_argument(
        "--github-runtime-id",
        default=os.getenv("AGENTOS_GITHUB_RUNTIME_ID", "github-actions-worker"),
    )
    parser.add_argument(
        "--github-capabilities",
        default=os.getenv("AGENTOS_GITHUB_CAPABILITIES"),
        help="Comma-separated capabilities eligible for GitHub Actions dispatch",
    )
    parser.add_argument(
        "--github-priority",
        type=int,
        default=int(os.getenv("AGENTOS_GITHUB_PRIORITY", "100")),
    )

    parser.add_argument(
        "--provider-bridge-endpoint",
        default=os.getenv("AGENTOS_PROVIDER_BRIDGE_ENDPOINT"),
        help="HTTPS /v1/runtime-dispatch endpoint for the Agent Provider Bridge",
    )
    parser.add_argument(
        "--provider-runtime-id",
        default=os.getenv("AGENTOS_PROVIDER_RUNTIME_ID", "provider-bridge"),
    )
    parser.add_argument(
        "--provider-capabilities",
        default=os.getenv("AGENTOS_PROVIDER_CAPABILITIES"),
        help="Comma-separated capabilities routed to the Provider Bridge",
    )
    parser.add_argument(
        "--provider-priority",
        type=int,
        default=int(os.getenv("AGENTOS_PROVIDER_PRIORITY", "50")),
    )

    parser.add_argument(
        "--continuity-mirror-repository",
        default=os.getenv("AGENTOS_CONTINUITY_MIRROR_REPOSITORY"),
        help="Private owner/name GitHub Data Layer repo used for connector-readable continuity checkpoints",
    )
    parser.add_argument(
        "--continuity-mirror-branch",
        default=os.getenv("AGENTOS_CONTINUITY_MIRROR_BRANCH", "main"),
    )
    parser.add_argument(
        "--continuity-mirror-root",
        default=os.getenv("AGENTOS_CONTINUITY_MIRROR_ROOT", "projects"),
    )
    args = parser.parse_args()

    token = os.getenv("AGENTOS_CONTROL_PLANE_TOKEN")
    store = DistributedControlPlane(args.db) if args.db else DistributedControlPlane()
    dispatcher = _build_dispatcher(store, args, parser)
    service = _build_service(store, dispatcher, args, parser)
    server = DistributedGatewayServer((args.host, args.port), service, token=token)

    stop_event = threading.Event()
    if dispatcher.targets and args.dispatch_interval_seconds > 0:
        sweep_thread = threading.Thread(
            target=dispatcher.run_sweep_loop,
            args=(stop_event,),
            kwargs={
                "interval_seconds": args.dispatch_interval_seconds,
                "limit": args.dispatch_limit,
            },
            name="agentos-runtime-dispatcher",
            daemon=True,
        )
        sweep_thread.start()

    target_count = len(dispatcher.targets)
    mirror_mode = "enabled" if _enabled("AGENTOS_CONTINUITY_MIRROR_ENABLED") else "disabled"
    print(
        f"Distributed AgentOS gateway listening on http://{args.host}:{args.port} "
        f"(active-dispatch targets={target_count}, continuity-mirror={mirror_mode})"
    )
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
