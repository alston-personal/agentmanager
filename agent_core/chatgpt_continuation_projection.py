from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ONE_ACTIVE_SCHEMA = "agentos.one-active-resolve/v1"
PROJECTION_SCHEMA = "agentos.chatgpt-continuation-projection/v1"
SOURCE = "ONE_ACTIVE_CONTINUATION"
TARGET_REPOSITORY = "alston-personal/my-agent-data"
TARGET_PATH = "projects/agentos-core/continuity/chatgpt-active.json"
TARGET_BRANCH = "main"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ProjectionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _json_request(method: str, url: str, *, token: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json" if "api.github.com" in url else "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AgentOS-ChatGPT-Continuation-Projection/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else None
    except HTTPError as exc:
        # Error bodies can contain private repository/runtime details. Never echo them.
        return int(exc.code), None
    except (URLError, TimeoutError, OSError) as exc:
        raise ProjectionError("transport_unavailable") from exc


def _validate_id(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not ID_RE.fullmatch(text):
        raise ProjectionError(f"invalid_{name}")
    return text


def _validate_active(payload: Any) -> tuple[dict[str, str], dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ProjectionError("one_active_protocol_error")
    if payload.get("schema") != ONE_ACTIVE_SCHEMA or payload.get("source") != SOURCE:
        raise ProjectionError("one_active_protocol_error")
    if payload.get("credential_exposed") is not False:
        raise ProjectionError("credential_boundary_violation")

    selector_raw = payload.get("selector")
    resolution = payload.get("resolution")
    if not isinstance(selector_raw, dict) or not isinstance(resolution, dict):
        raise ProjectionError("one_active_protocol_error")
    selector = {
        "project_id": _validate_id("project_id", selector_raw.get("project_id")),
        "index_id": _validate_id("index_id", selector_raw.get("index_id")),
        "ir_id": _validate_id("ir_id", selector_raw.get("ir_id")),
    }
    if selector["project_id"] != "agentos-core":
        raise ProjectionError("unsupported_project")

    project = resolution.get("project")
    continuation = resolution.get("continuation")
    execution_head = resolution.get("execution_head")
    if not isinstance(project, dict) or not isinstance(continuation, dict) or not isinstance(execution_head, dict):
        raise ProjectionError("one_active_protocol_error")
    if str(project.get("id") or "") != selector["project_id"]:
        raise ProjectionError("resolution_project_mismatch")

    canonical_ir = continuation.get("canonical_ir")
    if not isinstance(canonical_ir, dict):
        raise ProjectionError("canonical_ir_missing")
    if canonical_ir.get("schema_version") != "agentos.ir/v1":
        raise ProjectionError("canonical_ir_schema_error")
    if str(canonical_ir.get("ir_id") or "") != selector["ir_id"]:
        raise ProjectionError("canonical_ir_id_mismatch")
    if str(execution_head.get("index_id") or "") != selector["index_id"]:
        raise ProjectionError("execution_head_index_mismatch")
    nested_index = str(canonical_ir.get("index_id") or "").strip()
    if nested_index and nested_index != selector["index_id"]:
        raise ProjectionError("canonical_ir_index_mismatch")
    if not str(canonical_ir.get("goal") or "").strip():
        raise ProjectionError("canonical_ir_goal_missing")
    return selector, resolution


def _active_projection(one_url: str, controller_token: str) -> dict[str, Any]:
    status, payload = _json_request(
        "GET",
        one_url.rstrip("/") + "/v1/controller/continuation/active",
        token=controller_token,
    )
    if status != 200:
        raise ProjectionError(f"one_active_http_{status}")
    selector, resolution = _validate_active(payload)
    projection = {
        "schema": PROJECTION_SCHEMA,
        "source": SOURCE,
        "selector": selector,
        "resolution": resolution,
        "credential_exposed": False,
    }
    projection["projection_sha256"] = _sha256(projection)
    projection["published_at"] = _now()
    return projection


def _github_contents_url() -> str:
    encoded_path = "/".join(quote(part, safe="") for part in TARGET_PATH.split("/"))
    return f"https://api.github.com/repos/{TARGET_REPOSITORY}/contents/{encoded_path}"


def _existing_projection(github_token: str) -> tuple[str | None, dict[str, Any] | None]:
    status, payload = _json_request(
        "GET",
        _github_contents_url() + f"?ref={TARGET_BRANCH}",
        token=github_token,
    )
    if status == 404:
        return None, None
    if status != 200 or not isinstance(payload, dict):
        raise ProjectionError(f"github_read_http_{status}")
    sha = str(payload.get("sha") or "").strip() or None
    encoded = payload.get("content")
    if not isinstance(encoded, str):
        raise ProjectionError("github_read_protocol_error")
    try:
        decoded = base64.b64decode(encoded.replace("\n", "")).decode("utf-8")
        existing = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionError("github_projection_decode_error") from exc
    return sha, existing if isinstance(existing, dict) else None


def _same_generation(existing: dict[str, Any] | None, projection: dict[str, Any]) -> bool:
    if not isinstance(existing, dict):
        return False
    if existing.get("schema") != PROJECTION_SCHEMA or existing.get("source") != SOURCE:
        return False
    if existing.get("selector") != projection.get("selector"):
        return False
    return existing.get("projection_sha256") == projection.get("projection_sha256")


def publish_once(*, one_url: str, controller_token: str, github_token: str) -> dict[str, Any]:
    projection = _active_projection(one_url, controller_token)
    existing_sha, existing = _existing_projection(github_token)
    selector = dict(projection["selector"])
    if _same_generation(existing, projection):
        return {
            "ok": True,
            "updated": False,
            "selector": selector,
            "projection_sha256": projection["projection_sha256"],
            "target": f"{TARGET_REPOSITORY}:{TARGET_PATH}",
        }

    content = base64.b64encode((json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")).decode("ascii")
    body: dict[str, Any] = {
        "message": f"continuity(agentos-core): publish ChatGPT projection {selector['index_id']}",
        "content": content,
        "branch": TARGET_BRANCH,
    }
    if existing_sha:
        body["sha"] = existing_sha
    status, response = _json_request("PUT", _github_contents_url(), token=github_token, payload=body)
    if status not in (200, 201) or not isinstance(response, dict):
        raise ProjectionError(f"github_write_http_{status}")
    return {
        "ok": True,
        "updated": True,
        "selector": selector,
        "projection_sha256": projection["projection_sha256"],
        "target": f"{TARGET_REPOSITORY}:{TARGET_PATH}",
    }


def main() -> int:
    one_url = str(os.environ.get("AGENTOS_ONE_URL") or "http://127.0.0.1:8780").strip()
    controller_token = str(os.environ.get("AGENTOS_CONTROLLER_TOKEN") or "").strip()
    github_token = str(os.environ.get("AGENTOS_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not controller_token or not github_token:
        print("chatgpt_continuation_projection=ERROR missing_runtime_credential")
        return 2
    try:
        result = publish_once(one_url=one_url, controller_token=controller_token, github_token=github_token)
    except ProjectionError as exc:
        print(f"chatgpt_continuation_projection=ERROR {exc}")
        return 1
    selector = result["selector"]
    print("chatgpt_continuation_projection=PASS")
    print(f"updated={'YES' if result['updated'] else 'NO'}")
    print(f"project_id={selector['project_id']}")
    print(f"index_id={selector['index_id']}")
    print(f"ir_id={selector['ir_id']}")
    print(f"projection_sha256={result['projection_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
