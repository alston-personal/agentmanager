#!/usr/bin/env python3
"""Bounded, read-only Antigravity CLI identity and inference probe.

Standalone candidate for #623. Does not change ONE routing, MCP, auth, or config.
Output is deliberately restricted: never emit CLI stderr, full model text or secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

BINARY = Path("/home/ubuntu/.local/bin/agy")
EXPECTED = "AGENTOS_GEMINI_READY"
PROMPT = "Reply with exactly AGENTOS_GEMINI_READY. Do not call tools."
MAX_BINARY_BYTES = 512 * 1024 * 1024
AUTH_ERROR = ("unsupported_client", "this client is no longer supported")
AUTH_REQUIRED = ("login", "sign in", "authentication required", "unauthorized")
LIMIT_ERROR = ("rate limit", "quota", "resource exhausted")


def receipt(classification: str, **fields: object) -> dict[str, object]:
    return {
        "schema": "agentos.antigravity-cli-probe/v1",
        "surface": "antigravity-cli",
        "executor_class": "antigravity-cli",
        "classification": classification,
        "credential_exposed": False,
        "successful": classification == "ANTIGRAVITY_INFERENCE_PASS",
        **fields,
    }


def safe_run(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    # Neither a shell nor a caller-controlled command, workspace or prompt is allowed.
    return subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=timeout, check=False,
        cwd="/home/ubuntu", env=os.environ.copy(),
    )


def classify_error(data: str) -> str:
    low = data.casefold()
    if any(s in low for s in AUTH_ERROR):
        return "AUTH_UNSUPPORTED"
    if any(s in low for s in LIMIT_ERROR):
        return "RATE_LIMITED"
    if any(s in low for s in AUTH_REQUIRED):
        return "AUTH_REQUIRED"
    return "PROBE_COMMAND_FAILED"


def model_match(stdout: str) -> bool:
    # Permit JSON envelopes, but do not treat any occurrence of the token as success.
    try:
        value = json.loads(stdout)
    except (ValueError, TypeError):
        value = stdout
    if isinstance(value, str):
        return value.strip() == EXPECTED
    if isinstance(value, dict):
        for field in ("response", "text", "output"):
            response = value.get(field)
            if isinstance(response, str) and response.strip() == EXPECTED:
                return True
    return False


def main() -> int:
    if not BINARY.is_file() or BINARY.is_symlink():
        print(json.dumps(receipt("BINARY_MISSING")))
        return 1
    try:
        st = BINARY.stat()
        if not 0 < st.st_size <= MAX_BINARY_BYTES or not os.access(BINARY, os.X_OK):
            print(json.dumps(receipt("BINARY_INVALID")))
            return 1
        hasher = hashlib.sha256()
        with BINARY.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        if not BINARY.open("rb").read(4) == bytes((127, 69, 76, 70)):
            print(json.dumps(receipt("NOT_ELF_BINARY")))
            return 1
        version = safe_run([str(BINARY), "--version"], timeout=15)
        version_raw = (version.stdout or "") + "\n" + (version.stderr or "")
        # Match known CLI version forms, persist only normalized semver.
        version_match = re.search(r"(?im)^\s*(?:agy\s+(?:version\s+)?)?(v?\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9._-]+)?)\s*$", version_raw.strip())
        version_value = "agy " + version_match.group(1).lstrip("v") if version_match else ""
        if version.returncode or not version_match:
            print(json.dumps(receipt("VERSION_UNVERIFIED", executable=str(BINARY), sha256=digest,
                                     version_exit_code=version.returncode, version_detected=bool(version_match))))
            return 1
        start = time.monotonic()
        run = safe_run(
            [str(BINARY), "-p", PROMPT, "--output-format", "json", "--print-timeout", "60s"],
            timeout=75,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        # Fail closed: evidence is only a fixed expected token, not free-form output.
        classification = (
            "ANTIGRAVITY_INFERENCE_PASS" if run.returncode == 0 and model_match(run.stdout)
            else classify_error((run.stderr or "")[:8192] + "\n" + (run.stdout or "")[:8192])
            if run.returncode else "UNEXPECTED_MODEL_RESPONSE"
        )
        value = receipt(classification, executable=str(BINARY), sha256=digest,
                        version=version_value, returncode=run.returncode,
                        duration_ms=duration_ms, expected_marker_matched=model_match(run.stdout))
        print(json.dumps(value, sort_keys=True))
        return 0 if value["successful"] else 1
    except subprocess.TimeoutExpired:
        print(json.dumps(receipt("PROBE_TIMEOUT", executable=str(BINARY))))
        return 1
    except (OSError, UnicodeError):
        print(json.dumps(receipt("PROBE_RUNTIME_ERROR", executable=str(BINARY))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
