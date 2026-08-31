from __future__ import annotations

import copy
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reversible import embed_ir_in_gltf, ir_digest, recover_embedded_ir

GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
SUPPORTED_CONTAINER_SUFFIXES = {".glb", ".vrm"}


@dataclass(frozen=True)
class GlbChunk:
    type: int
    payload: bytes


@dataclass(frozen=True)
class GlbContainer:
    gltf: dict[str, Any]
    chunks: tuple[GlbChunk, ...]


def _bytes(value: str | Path | bytes | bytearray) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return Path(value).read_bytes()


def parse_glb_container(value: str | Path | bytes | bytearray) -> GlbContainer:
    """Parse a GLB 2.0 container without discarding non-JSON chunk bytes."""

    data = _bytes(value)
    if len(data) < 20:
        raise ValueError("GLB too small")
    magic, version, declared_total = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("not a GLB/VRM container")
    if version != GLB_VERSION:
        raise ValueError(f"unsupported GLB version {version}")
    if declared_total != len(data):
        raise ValueError(
            f"GLB declared length mismatch: header={declared_total} actual={len(data)}"
        )

    off = 12
    chunks: list[GlbChunk] = []
    while off < len(data):
        if off + 8 > len(data):
            raise ValueError("truncated GLB chunk header")
        length, chunk_type = struct.unpack_from("<II", data, off)
        off += 8
        if length % 4 != 0:
            raise ValueError("GLB chunk length must be 4-byte aligned")
        end = off + length
        if end > len(data):
            raise ValueError("GLB chunk exceeds declared container length")
        chunks.append(GlbChunk(chunk_type, data[off:end]))
        off = end

    if not chunks:
        raise ValueError("GLB has no chunks")
    if chunks[0].type != JSON_CHUNK:
        raise ValueError("GLB first chunk must be JSON")
    if sum(1 for chunk in chunks if chunk.type == JSON_CHUNK) != 1:
        raise ValueError("GLB must contain exactly one JSON chunk")

    raw_json = chunks[0].payload.rstrip(b"\x00 \t\r\n")
    try:
        gltf = json.loads(raw_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid GLB JSON chunk") from exc
    if not isinstance(gltf, dict):
        raise ValueError("GLB JSON chunk must contain an object")
    return GlbContainer(gltf=gltf, chunks=tuple(chunks))


def _resource_uris(gltf: dict[str, Any]) -> list[str]:
    uris: list[str] = []
    for item in gltf.get("buffers", []) or []:
        if isinstance(item, dict) and isinstance(item.get("uri"), str):
            uris.append(item["uri"])
    for item in gltf.get("images", []) or []:
        if isinstance(item, dict) and isinstance(item.get("uri"), str):
            uris.append(item["uri"])
    return uris


def external_resource_uris(gltf: dict[str, Any]) -> list[str]:
    """Return glTF resource URIs that are not embedded data URIs."""

    return [uri for uri in _resource_uris(gltf) if not uri.startswith("data:")]


def _encode_json_chunk(gltf: dict[str, Any]) -> bytes:
    payload = json.dumps(
        gltf,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    return payload


def _serialize(chunks: list[GlbChunk]) -> bytes:
    body = bytearray()
    for chunk in chunks:
        body.extend(struct.pack("<II", len(chunk.payload), chunk.type))
        body.extend(chunk.payload)
    total = 12 + len(body)
    return struct.pack("<4sII", GLB_MAGIC, GLB_VERSION, total) + bytes(body)


def _non_json_chunks(container: GlbContainer) -> tuple[GlbChunk, ...]:
    return tuple(chunk for chunk in container.chunks if chunk.type != JSON_CHUNK)


def _chunk_digest(chunk: GlbChunk) -> str:
    return "sha256:" + hashlib.sha256(chunk.payload).hexdigest()


def compile_reversible_glb(
    source: str | Path | bytes | bytearray,
    canonical_ir: dict[str, Any],
    *,
    require_relocatable: bool = True,
) -> bytes:
    """Embed Canonical Character IR into GLB/VRM while preserving non-JSON chunks.

    Only the JSON chunk is rewritten. Every non-JSON chunk is copied byte-for-byte,
    in the original order. By default assets with non-data external resource URIs
    are rejected because moving the output could otherwise silently break them.
    """

    container = parse_glb_container(source)
    external = external_resource_uris(container.gltf)
    if require_relocatable and external:
        raise ValueError(
            "GLB/VRM references external resources; refusing relocatable reversible output: "
            + ", ".join(external)
        )

    embedded = embed_ir_in_gltf(container.gltf, canonical_ir)
    new_chunks = [GlbChunk(JSON_CHUNK, _encode_json_chunk(embedded))]
    new_chunks.extend(copy.deepcopy(_non_json_chunks(container)))
    return _serialize(new_chunks)


def verify_glb_container_preservation(
    source: str | Path | bytes | bytearray,
    compiled: str | Path | bytes | bytearray,
    canonical_ir: dict[str, Any],
) -> dict[str, Any]:
    """Verify both canonical-IR recovery and non-JSON GLB chunk byte fidelity."""

    src = parse_glb_container(source)
    dst = parse_glb_container(compiled)
    src_non_json = _non_json_chunks(src)
    dst_non_json = _non_json_chunks(dst)

    chunks_exact = len(src_non_json) == len(dst_non_json) and all(
        a.type == b.type and a.payload == b.payload
        for a, b in zip(src_non_json, dst_non_json)
    )
    expected_gltf = embed_ir_in_gltf(src.gltf, canonical_ir)
    json_expected = dst.gltf == expected_gltf
    recovered = recover_embedded_ir(dst.gltf)
    canonical_exact = recovered == canonical_ir
    digest_exact = recovered is not None and ir_digest(recovered) == ir_digest(canonical_ir)

    source_chunks = [
        {"index": i, "type": chunk.type, "bytes": len(chunk.payload), "digest": _chunk_digest(chunk)}
        for i, chunk in enumerate(src_non_json)
    ]
    output_chunks = [
        {"index": i, "type": chunk.type, "bytes": len(chunk.payload), "digest": _chunk_digest(chunk)}
        for i, chunk in enumerate(dst_non_json)
    ]
    external = external_resource_uris(src.gltf)

    return {
        "schema": "model2ir-glb-preservation/v0.9",
        "canonical_ir": {
            "lossless": canonical_exact and digest_exact,
            "expected_digest": ir_digest(canonical_ir),
            "recovered_digest": ir_digest(recovered) if recovered is not None else None,
        },
        "container": {
            "json_expected": json_expected,
            "non_json_chunks_exact": chunks_exact,
            "non_json_chunk_count": len(src_non_json),
            "source_chunks": source_chunks,
            "output_chunks": output_chunks,
            "external_resource_uris": external,
            "relocatable": not external,
        },
        "lossless_reversible": canonical_exact and digest_exact and json_expected and chunks_exact,
    }


def save_reversible_glb(
    source: str | Path,
    canonical_ir: dict[str, Any],
    output: str | Path,
    *,
    require_relocatable: bool = True,
) -> Path:
    src = Path(source)
    dst = Path(output)
    if src.suffix.lower() not in SUPPORTED_CONTAINER_SUFFIXES:
        raise ValueError("reversible container writer supports .glb and .vrm only")
    if dst.suffix.lower() not in SUPPORTED_CONTAINER_SUFFIXES:
        raise ValueError("reversible container output must use .glb or .vrm")
    if src.resolve() == dst.resolve():
        raise ValueError("refusing to overwrite source asset in place")

    payload = compile_reversible_glb(
        src,
        canonical_ir,
        require_relocatable=require_relocatable,
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(payload)
    report = verify_glb_container_preservation(src, dst, canonical_ir)
    if not report["lossless_reversible"]:
        dst.unlink(missing_ok=True)
        raise ValueError("reversible GLB verification failed; output removed")
    return dst
