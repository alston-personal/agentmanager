from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

EXTENSION_KEY = "OPENAI_model2ir_character_ir"
EXTENSION_VERSION = "0.2.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def ir_digest(ir: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(ir).encode("utf-8")).hexdigest()


def embed_ir_in_gltf(gltf: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any]:
    """Return a glTF document carrying a lossless Character IR sidecar.

    The carrier lives in root extras rather than a registered glTF extension so the
    resulting asset remains standards-compatible without claiming Khronos registry
    status. Geometry is untouched.
    """
    out = copy.deepcopy(gltf)
    extras = out.setdefault("extras", {})
    extras[EXTENSION_KEY] = {
        "version": EXTENSION_VERSION,
        "encoding": "json",
        "digest": ir_digest(ir),
        "character_ir": copy.deepcopy(ir),
        "truth_class": "embedded_canonical_ir",
    }
    return out


def recover_embedded_ir(gltf: dict[str, Any]) -> dict[str, Any] | None:
    payload = (gltf.get("extras") or {}).get(EXTENSION_KEY)
    if not isinstance(payload, dict):
        return None
    ir = payload.get("character_ir")
    if not isinstance(ir, dict):
        return None
    expected = payload.get("digest")
    actual = ir_digest(ir)
    if expected and expected != actual:
        raise ValueError("embedded Character IR digest mismatch")
    return copy.deepcopy(ir)


def reversible_status(gltf: dict[str, Any]) -> dict[str, Any]:
    payload = (gltf.get("extras") or {}).get(EXTENSION_KEY)
    if not isinstance(payload, dict):
        return {
            "mode": "inferred",
            "lossless": False,
            "reason": "asset has no model2ir embedded canonical IR",
        }
    ir = recover_embedded_ir(gltf)
    return {
        "mode": "embedded-canonical",
        "lossless": True,
        "digest": payload.get("digest") or ir_digest(ir or {}),
        "version": payload.get("version"),
    }
