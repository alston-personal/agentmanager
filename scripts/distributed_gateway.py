#!/usr/bin/env python3
"""Run the Distributed AgentOS Control Plane HTTP gateway."""

from __future__ import annotations

import argparse
import os
import threading

from agent_core.dispatching_gateway import DispatchingGatewayService
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer
from agent_core.runtime_dispatcher import (
    GitHubActionsDispatchTransport,
    RuntimeDispatcher,
    RuntimeTarget,
)


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def _build_dispatcher(
    store: DistributedControlPlane,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> RuntimeDispatcher:
    dispatcher = RuntimeDispatcher(
        store,
        dispatch_timeout_seconds=args.dispatch_timeout_seconds,
        dispatch_retry_seconds=args.dispatch_retry_seconds,
    )

    token = os.getenv("AGENTOS_GITHUB_TOKEN")
    if token:
        dispatcher.register_transport(GitHubActionsDispatchTransport(token))

    if args.github_repository:
        capabilities = _csv(args.github_capabilities)
        missing = []
        if not token:
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
    return dispatcher


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
    args = parser.parse_args()

    token = os.getenv("AGENTOS_CONTROL_PLANE_TOKEN")
    store = DistributedControlPlane(args.db) if args.db else DistributedControlPlane()
    dispatcher = _build_dispatcher(store, args, parser)
    service = DispatchingGatewayService(store, dispatcher)
    server = DistributedGatewayServer((args.host, args.port), service, token=token)

    stop_event = threading.Event()
    sweep_thread = None
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
    print(
        f"Distributed AgentOS gateway listening on http://{args.host}:{args.port} "
        f"(active-dispatch targets={target_count})"
    )
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
