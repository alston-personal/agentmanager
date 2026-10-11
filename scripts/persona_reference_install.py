#!/usr/bin/env python3
"""Install only Mio's already approved reference through the existing carrier."""
import argparse
import base64
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY = "alston-personal/my-agent-data"
PERSONA = "personas/sunlake-milkcat"
REFERENCE_ID = "mio-wardrobe-body-reference-v2.1"
SOURCE_COMMIT = "87320a45ad554ed61453eb8e0acef5b32552d5a6"
PACK_PATH = PERSONA + "/reference_pack.json"
ASSET_PATH = PERSONA + "/assets/references/" + REFERENCE_ID + ".jpg"
TRANSFER_PATH = PERSONA + "/assets/references/reference_transfer.json"
MAX_RESPONSE = 1_000_000
DATA_ROOT = Path("/home/ubuntu/agent-data")
CONFIG_ROOT = Path("/home/ubuntu/.config/agentos")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def github(endpoint):
    env = os.environ.copy()
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(key, None)
    try:
        result = subprocess.run(["/usr/bin/gh", "api", "repos/" + REPOSITORY + ("/" + endpoint if endpoint else "")],
                                env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=20, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("REFERENCE_SOURCE_TIMEOUT") from exc
    if result.returncode or len(result.stdout) > MAX_RESPONSE:
        raise ValueError("REFERENCE_SOURCE_FETCH_FAILED")
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("REFERENCE_SOURCE_INVALID") from exc
    if not isinstance(value, dict):
        raise ValueError("REFERENCE_SOURCE_INVALID")
    return value


def content(path, ref):
    value = github("contents/" + path + "?ref=" + ref)
    if value.get("path") != path or value.get("encoding") != "base64":
        raise ValueError("REFERENCE_SOURCE_INVALID")
    try:
        data = base64.b64decode("".join(value["content"].split()), validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("REFERENCE_SOURCE_INVALID") from exc
    if type(value.get("size")) is not int or len(data) != value["size"]:
        raise ValueError("REFERENCE_SOURCE_INVALID")
    return data


def approved(pack):
    asset = pack.get("canonical_asset") or {}
    if (pack.get("status") != "approved" or asset.get("reference_id") != REFERENCE_ID
            or REFERENCE_ID not in (pack.get("approved_reference_ids") or [])
            or REFERENCE_ID in (pack.get("rejected_reference_ids") or [])
            or asset.get("mime_type") != "image/jpeg"
            or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", "")))):
        raise ValueError("REFERENCE_NOT_APPROVED")
    return asset["sha256"]


def private_path(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("REFERENCE_PRIVATE_PATH_INVALID")


def atomic_private(path, data):
    # Refuse symlinks before any creation/replacement; never chmod shared parents.
    private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".reference-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install():
    if github("").get("private") is not True:
        raise ValueError("REFERENCE_SOURCE_NOT_PRIVATE")
    pack = json.loads(content(PACK_PATH, "main"))
    expected = approved(pack)
    transfer = json.loads(content(TRANSFER_PATH, SOURCE_COMMIT))
    if (transfer.get("schema") != "agentos.persona-reference-transfer/v1"
            or transfer.get("reference_id") != REFERENCE_ID
            or transfer.get("persona_path") != PERSONA
            or transfer.get("asset_path") != ASSET_PATH
            or transfer.get("approval_source") != PACK_PATH
            or transfer.get("sha256") != expected
            or transfer.get("mime_type") != "image/jpeg"
            or type(transfer.get("byte_size")) is not int
            or not 32 <= transfer["byte_size"] <= 700_000):
        raise ValueError("REFERENCE_TRANSFER_INVALID")
    data = content(ASSET_PATH, SOURCE_COMMIT)
    if (len(data) != transfer["byte_size"] or digest(data) != expected
            or not data.startswith(b"\xff\xd8\xff")):
        raise ValueError("REFERENCE_DIGEST_MISMATCH")
    # A newly revoked/superseded approval cannot be replayed after downloading.
    if approved(json.loads(content(PACK_PATH, "main"))) != expected:
        raise ValueError("REFERENCE_APPROVAL_CHANGED")
    image = DATA_ROOT / "media/mio/references" / (REFERENCE_ID + ".jpg")
    config = CONFIG_ROOT / "mio-reference.env"
    env = ('AGENTOS_MIO_REFERENCE_IMAGE="' + str(image) + '"\n').encode()
    changed = False
    private_path(image)
    private_path(config)
    for path, value in ((image, data), (config, env)):
        if (not path.is_file() or path.read_bytes() != value
                or path.stat().st_mode & 0o777 != 0o600):
            atomic_private(path, value)
            changed = True
    if digest(image.read_bytes()) != expected or config.read_bytes() != env:
        raise ValueError("REFERENCE_INSTALL_READBACK_FAILED")
    return {"reference_status": "MATCHED", "reference_sha256": expected,
            "private_file_mode": "0600", "environment_configured": True,
            "changed": changed, "asset_source_commit": SOURCE_COMMIT,
            "asset_source_repository_private": True}


def run(source_sha):
    receipt = {"schema": "agentos.execution-receipt/v1", "persona_path": PERSONA,
               "request_id": "mio-reference-install-" + source_sha[:12],
               "capability": "social.threads.publish.image", "operation": "canonical_reference.install",
               "environment": "production", "reference_id": REFERENCE_ID,
               "expected": {"source_sha": source_sha}, "publication_allowed": False,
               "authority": {"kind": "runtime_node", "sandbox_fallback_allowed": False},
               "node": socket.gethostname(),
               "installer_sha256": digest(Path(__file__).read_bytes()),
               "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    try:
        if os.getuid() != 1001:
            raise ValueError("REFERENCE_WRONG_USER")
        receipt.update(status="completed", parity="matched", observed=install())
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        known = {"REFERENCE_SOURCE_TIMEOUT", "REFERENCE_SOURCE_FETCH_FAILED", "REFERENCE_SOURCE_INVALID",
                 "REFERENCE_NOT_APPROVED", "REFERENCE_PRIVATE_PATH_INVALID", "REFERENCE_SOURCE_NOT_PRIVATE",
                 "REFERENCE_TRANSFER_INVALID", "REFERENCE_DIGEST_MISMATCH", "REFERENCE_APPROVAL_CHANGED",
                 "REFERENCE_INSTALL_READBACK_FAILED", "REFERENCE_WRONG_USER"}
        reason = str(exc) if str(exc) in known else "REFERENCE_INSTALL_INVALID"
        receipt.update(status="blocked", parity="unavailable", reason=reason)
    if os.getuid() == 1001:
        try:
            atomic_private(DATA_ROOT / "runtime/persona-media/reference-install.json",
                           (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode())
        except (OSError, ValueError):
            receipt.update(status="blocked", parity="unavailable", reason="REFERENCE_RECEIPT_PERSIST_FAILED")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        parser.error("source-sha must be an exact commit SHA")
    receipt = run(args.source_sha)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
