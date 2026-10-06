#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any


def _check(name: str, ok: bool, detail: str, *, blocking: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "blocking": blocking, "detail": detail}


def inspect_worker(provider: str, *, env: dict[str, str] | None = None, root: Path = Path("/")) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    provider = provider.strip().lower()
    if provider not in {"docker", "aws"}:
        raise ValueError("provider must be docker or aws")

    machine = platform.machine().lower()
    checks: list[dict[str, Any]] = []
    checks.append(_check("x86_64_host", machine in {"x86_64", "amd64"}, f"machine={machine}"))

    if provider == "docker":
        kvm = root / "dev" / "kvm"
        checks.append(_check("kvm_available", kvm.exists(), f"path={kvm} exists={kvm.exists()}"))
        qemu = shutil.which("qemu-system-x86_64") or shutil.which("qemu-system-x86")
        checks.append(_check("qemu_available", bool(qemu), f"qemu={qemu or 'missing'}"))
        checks.append(_check(
            "hf_token_present",
            bool(env.get("HF_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN")),
            "HF_TOKEN/HUGGING_FACE_HUB_TOKEN present" if (env.get("HF_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN")) else "missing Hugging Face token",
        ))
        checks.append(_check(
            "website_suffix_present",
            bool(env.get("WEBSITE_HOST_SUFFIX")),
            f"WEBSITE_HOST_SUFFIX={env.get('WEBSITE_HOST_SUFFIX') or 'missing'}",
        ))
    else:
        required = [
            "AWS_REGION",
            "AWS_SUBNET_ID",
            "AWS_SECURITY_GROUP_ID",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]
        for key in required:
            checks.append(_check(
                key.lower(),
                bool(env.get(key)),
                f"{key}={'present' if env.get(key) else 'missing'}",
            ))
        checks.append(_check(
            "aws_region_us_east_1",
            env.get("AWS_REGION") == "us-east-1",
            f"AWS_REGION={env.get('AWS_REGION') or 'missing'}; official v2.1 AMI is pinned in us-east-1",
        ))
        checks.append(_check(
            "hf_token_present",
            bool(env.get("HF_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN")),
            "HF token present" if (env.get("HF_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN")) else "missing Hugging Face token",
        ))
        checks.append(_check(
            "website_suffix_present",
            bool(env.get("WEBSITE_HOST_SUFFIX")),
            f"WEBSITE_HOST_SUFFIX={env.get('WEBSITE_HOST_SUFFIX') or 'missing'}",
        ))

    blocking = [c for c in checks if c["blocking"] and not c["ok"]]
    return {
        "schema": "agentos.osworld-worker-preflight/v1",
        "benchmark": "OSWorld-V2",
        "release": "osworld-v2.1",
        "provider": provider,
        "host": {
            "machine": machine,
            "system": platform.system(),
            "release": platform.release(),
        },
        "checks": checks,
        "ready": not blocking,
        "blocking_failures": [c["name"] for c in blocking],
        "recommended_role": (
            "benchmark-worker"
            if not blocking
            else (
                "control-orchestrator-only"
                if "x86_64_host" in {c["name"] for c in blocking}
                else "benchmark-worker-needs-prerequisites"
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OSWorld-V2.1 benchmark worker preflight")
    parser.add_argument("--provider", choices=["docker", "aws"], required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    result = inspect_worker(args.provider)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
