#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import model2ir
from model2ir import audit_asset, extract_ir, profile_asset_structure, stabilize_external_ir

LAB_SCHEMA = "model2ir-lab-analysis/v0.1"
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
SUPPORTED_SUFFIXES = {".glb", ".vrm"}
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


class LabInputError(ValueError):
    status_code = 400
    code = "invalid-input"


class UnsupportedAssetError(LabInputError):
    status_code = 415
    code = "unsupported-asset"


class PayloadTooLargeError(LabInputError):
    status_code = 413
    code = "payload-too-large"


def _validate_filename(filename: str) -> tuple[str, str]:
    name = unquote((filename or "").strip())
    if not name:
        raise LabInputError("X-Model2IR-Filename is required")
    if len(name) > 180 or "\x00" in name or "/" in name or "\\" in name:
        raise LabInputError("filename must be a basename no longer than 180 characters")
    suffix = Path(name).suffix.lower()
    if suffix == ".gltf":
        raise UnsupportedAssetError(
            "multi-file .gltf bundles are not supported in Model2IR Lab v0.1; use a self-contained .glb or .vrm"
        )
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedAssetError("Model2IR Lab v0.1 accepts only self-contained .glb or .vrm files")
    return name, suffix


def _validate_glb_container(data: bytes) -> None:
    if not data:
        raise LabInputError("asset body is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError(f"asset exceeds the {MAX_UPLOAD_BYTES}-byte Lab v0.1 limit")
    if len(data) < 12:
        raise LabInputError("asset is too short to be a GLB 2.0 container")
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise LabInputError("asset does not have GLB magic")
    if version != 2:
        raise LabInputError("Model2IR Lab v0.1 accepts GLB container version 2 only")
    if declared_length != len(data):
        raise LabInputError("GLB declared length does not match the uploaded byte length")


def _dedupe_unresolved(*values: Any) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            try:
                key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            except Exception:
                key = repr(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def analyze_asset_bytes(filename: str, data: bytes, *, repeats: int = 3) -> dict[str, Any]:
    """Analyze one self-contained GLB/VRM with the real Model2IR Python library.

    The uploaded bytes exist only inside a TemporaryDirectory for the duration of this
    call. The function never promotes a stabilized candidate to canonical truth.
    """

    if repeats < 2:
        raise LabInputError("audit repeats must be >= 2")
    safe_name, suffix = _validate_filename(filename)
    _validate_glb_container(data)
    source_sha256 = hashlib.sha256(data).hexdigest()

    with tempfile.TemporaryDirectory(prefix="model2ir-lab-") as temp_dir:
        asset_path = Path(temp_dir) / f"asset{suffix}"
        asset_path.write_bytes(data)

        extracted = extract_ir(asset_path)
        profile = extracted.get("geometry_profile_evidence")
        if not isinstance(profile, dict):
            profile = profile_asset_structure(extracted)
        stabilized = stabilize_external_ir(extracted)
        audit = audit_asset(asset_path, repeats=repeats)
        # Never disclose server-local temporary paths as part of the public contract.
        audit = {**audit, "asset": safe_name}

    canonical = extracted.get("canonical_ir")
    has_embedded_canonical = isinstance(canonical, dict)
    result_role = "embedded-canonical" if has_embedded_canonical else "stabilized-candidate"
    candidate = stabilized if isinstance(stabilized, dict) else {}
    body_plan = candidate.get("body_plan") if isinstance(candidate.get("body_plan"), dict) else {"kind": "unknown"}
    unresolved = _dedupe_unresolved(
        profile.get("unresolved"),
        candidate.get("unresolved"),
        extracted.get("unresolved"),
    )

    audit_truth = audit.get("truth_policy") if isinstance(audit.get("truth_policy"), dict) else {}
    truth_policy = {
        **audit_truth,
        "result_role": result_role,
        "stabilized_candidate_is_canonical": has_embedded_canonical,
        "automatic_promotion_of_inference": False,
        "statement": (
            "An external stabilized result remains a candidate unless Model2IR recovered explicit embedded canonical IR; "
            "geometry/profile evidence never creates humanoid truth by appearance alone."
        ),
    }

    return {
        "schema": LAB_SCHEMA,
        "model2ir_version": model2ir.__version__,
        "analysis_source": "python-model2ir-library",
        "asset": {
            "filename": safe_name,
            "suffix": suffix,
            "bytes": len(data),
            "sha256": source_sha256,
            "persisted": False,
        },
        "summary": {
            "observed": profile.get("observed") or {},
            "inferred": {
                "geometry_profile": profile.get("inferred") or {},
                "stabilized_body_plan": body_plan,
                "semantic_authority": audit.get("semantic_authority"),
                "stability_status": audit.get("status"),
                "result_role": result_role,
            },
            "unresolved": unresolved,
        },
        "truth_policy": truth_policy,
        "evidence": {
            "geometry_profile": profile,
            "vrm_humanoid": extracted.get("vrm_humanoid_evidence"),
            "topology": extracted.get("topology_evidence"),
        },
        "results": {
            "stabilized_ir": stabilized,
            "audit": audit,
            "extracted_ir": extracted,
        },
    }


class Model2IRLabHTTPServer(HTTPServer):
    request_queue_size = 4


class Model2IRLabHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Model2IRLab/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _route(self) -> str:
        return urlsplit(self.path).path

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self._route() != "/healthz":
            self._send_json(404, {"ok": False, "error": "not-found"})
            return
        self._send_json(
            200,
            {
                "ok": True,
                "schema": "model2ir-lab-health/v0.1",
                "model2ir_version": model2ir.__version__,
                "bind_policy": "localhost-only",
                "single_worker": True,
                "max_upload_bytes": MAX_UPLOAD_BYTES,
                "accepted": [".glb", ".vrm"],
                "multi_file_gltf_supported": False,
            },
        )

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self._route() != "/v1/analyze":
            self._send_json(404, {"ok": False, "error": "not-found"})
            return

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._send_json(411, {"ok": False, "error": "content-length-required"})
            return
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(400, {"ok": False, "error": "invalid-content-length"})
            return
        if length <= 0:
            self._send_json(400, {"ok": False, "error": "empty-body"})
            return
        if length > MAX_UPLOAD_BYTES:
            self._send_json(
                413,
                {"ok": False, "error": "payload-too-large", "max_upload_bytes": MAX_UPLOAD_BYTES},
            )
            return

        data = self.rfile.read(length)
        if len(data) != length:
            self._send_json(400, {"ok": False, "error": "truncated-body"})
            return

        try:
            result = analyze_asset_bytes(self.headers.get("X-Model2IR-Filename", ""), data, repeats=3)
        except LabInputError as exc:
            self._send_json(exc.status_code, {"ok": False, "error": exc.code, "message": str(exc)})
            return
        except Exception as exc:  # public boundary: expose class, not a server-local traceback/path
            self._send_json(
                422,
                {
                    "ok": False,
                    "error": "analysis-failed",
                    "error_type": type(exc).__name__,
                    "message": "Model2IR could not analyze this GLB/VRM container",
                },
            )
            return

        self._send_json(200, {"ok": True, "analysis": result})

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep the standard server log useful without ever logging uploaded filenames or bodies.
        super().log_message(fmt, *args)


def run_server(host: str, port: int) -> None:
    if host not in LOCAL_HOSTS and os.environ.get("MODEL2IR_LAB_ALLOW_NONLOCAL") != "1":
        raise SystemExit("Model2IR Lab refuses a non-local bind; expose it through the governed reverse proxy")
    server = Model2IRLabHTTPServer((host, port), Model2IRLabHandler)
    try:
        print(
            json.dumps(
                {
                    "ok": True,
                    "schema": "model2ir-lab-start/v0.1",
                    "host": host,
                    "port": server.server_port,
                    "model2ir_version": model2ir.__version__,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Localhost-only Model2IR Lab v0.1 HTTP analysis service")
    parser.add_argument("--host", default=os.environ.get("MODEL2IR_LAB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MODEL2IR_LAB_PORT", "18766")))
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
