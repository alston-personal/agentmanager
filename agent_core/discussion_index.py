"""ONE-owned cross-Node discussion provenance index.

Discussion records answer "where did we discuss this?" without promoting
vendor chat history into Canonical IR or Experience authority.
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Iterator

RECORD_SCHEMA = "agentos.discussion-record/v1"
SEARCH_RESULT_SCHEMA = "agentos.discussion-search-result/v1"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+"),
)
REF_KEYS = ("canonical_ir", "experience", "issues", "receipts", "assignments")
STORAGE_CLASSES = {"indexed_projection", "private_projection", "vault_linked"}


def _data_root() -> Path:
    return Path(
        os.environ.get("AGENT_DATA_ROOT")
        or os.environ.get("AGENTOS_DATA_ROOT")
        or "/home/ubuntu/agent-data"
    ).expanduser()


def discussion_path(project_id: str, *, data_root: Path | None = None) -> Path:
    project = _safe_id(project_id, "project_id", required=True)
    root = data_root or _data_root()
    return root / "discussion-index" / project / "records.jsonl"


def _bounded_string(value: Any, field: str, *, required: bool = False, max_len: int = 4096) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_len:
        raise ValueError(f"{field} is too long")
    return text


def _safe_id(value: Any, field: str, *, required: bool = False) -> str:
    text = _bounded_string(value, field, required=required, max_len=192)
    if text and not ID_RE.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def _string_list(value: Any, field: str, *, limit: int = 64, item_max: int = 512) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{field} must be a bounded list")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _bounded_string(item, field, max_len=item_max)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def contains_secret_like(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def semantic_digest(record: dict[str, Any]) -> str:
    identity = {
        "project_id": record["project_id"],
        "provenance": record["provenance"],
        "semantic": record["semantic"],
        "source_digest": record.get("source_digest"),
    }
    return "sha256:" + sha256(_canonical_bytes(identity)).hexdigest()


def validate_record(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != RECORD_SCHEMA:
        raise ValueError("unsupported discussion record schema")

    discussion_id = _safe_id(value.get("discussion_id"), "discussion_id", required=True)
    project_id = _safe_id(value.get("project_id"), "project_id", required=True)
    realm_id = _safe_id(value.get("realm_id"), "realm_id")
    observed_start = _bounded_string(
        value.get("observed_start"), "observed_start", required=True, max_len=64
    )
    observed_end = _bounded_string(value.get("observed_end"), "observed_end", max_len=64)

    provenance = value.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")
    canonical_provenance = {
        "node_id": _safe_id(provenance.get("node_id"), "node_id"),
        "surface": _safe_id(provenance.get("surface"), "surface"),
        "executor_adapter": _safe_id(
            provenance.get("executor_adapter"), "executor_adapter"
        ),
        "backend_model": _bounded_string(
            provenance.get("backend_model") or "unknown", "backend_model", max_len=192
        ),
        "session_ref": _bounded_string(
            provenance.get("session_ref"), "session_ref", max_len=512
        ),
        "source_ref": _bounded_string(
            provenance.get("source_ref"), "source_ref", required=True, max_len=1024
        ),
    }

    semantic = value.get("semantic")
    if not isinstance(semantic, dict):
        raise ValueError("semantic must be an object")
    canonical_semantic = {
        "summary": _bounded_string(
            semantic.get("summary"), "summary", required=True, max_len=8192
        ),
        "topics": _string_list(semantic.get("topics"), "topics", limit=32),
        "entities": _string_list(semantic.get("entities"), "entities", limit=64),
        "keywords": _string_list(semantic.get("keywords"), "keywords", limit=64),
    }
    searchable = "\n".join(
        [
            canonical_semantic["summary"],
            *canonical_semantic["topics"],
            *canonical_semantic["entities"],
            *canonical_semantic["keywords"],
        ]
    )
    if contains_secret_like(searchable):
        raise ValueError("secret-like content is not allowed in discussion projection")

    refs = value.get("refs") or {}
    if not isinstance(refs, dict):
        raise ValueError("refs must be an object")
    canonical_refs = {
        key: _string_list(refs.get(key), f"refs.{key}", limit=64, item_max=512)
        for key in REF_KEYS
    }

    promoted_to = _string_list(
        value.get("promoted_to"), "promoted_to", limit=64, item_max=512
    )
    privacy = value.get("privacy") or {}
    if not isinstance(privacy, dict):
        raise ValueError("privacy must be an object")
    storage_class = _bounded_string(
        privacy.get("storage_class") or "indexed_projection",
        "storage_class",
        max_len=64,
    )
    if storage_class not in STORAGE_CLASSES:
        raise ValueError("unsupported storage_class")

    source_digest = _bounded_string(value.get("source_digest"), "source_digest", max_len=80)
    if source_digest and not SHA256_RE.fullmatch(source_digest):
        raise ValueError("invalid source_digest")

    canonical = {
        "schema": RECORD_SCHEMA,
        "discussion_id": discussion_id,
        "project_id": project_id,
        "realm_id": realm_id or None,
        "observed_start": observed_start,
        "observed_end": observed_end or observed_start,
        "provenance": canonical_provenance,
        "semantic": canonical_semantic,
        "refs": canonical_refs,
        "promoted_to": promoted_to,
        "privacy": {"storage_class": storage_class},
        "source_digest": source_digest or None,
    }
    canonical["semantic_digest"] = semantic_digest(canonical)
    supplied = _bounded_string(value.get("semantic_digest"), "semantic_digest", max_len=80)
    if supplied and supplied != canonical["semantic_digest"]:
        raise ValueError("discussion semantic_digest mismatch")
    return canonical


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise ValueError("discussion lock path must not be a symlink")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_records(project_id: str, *, data_root: Path | None = None) -> list[dict[str, Any]]:
    path = discussion_path(project_id, data_root=data_root)
    if path.is_symlink():
        raise ValueError("discussion store path must not be a symlink")
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            raw = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid discussion record JSON at line {number}") from exc
        records.append(validate_record(raw))
    return records


def append_record(
    record: dict[str, Any], *, data_root: Path | None = None
) -> dict[str, Any]:
    canonical = validate_record(record)
    path = discussion_path(canonical["project_id"], data_root=data_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _lock(path):
        current = read_records(canonical["project_id"], data_root=data_root)
        for existing in current:
            if existing["discussion_id"] != canonical["discussion_id"]:
                continue
            if existing["semantic_digest"] != canonical["semantic_digest"]:
                raise ValueError("discussion_id already exists with a different semantic digest")
            return {
                "schema": "agentos.discussion-append-receipt/v1",
                "ok": True,
                "persisted": False,
                "discussion_id": canonical["discussion_id"],
                "project_id": canonical["project_id"],
                "semantic_digest": canonical["semantic_digest"],
                "credential_exposed": False,
            }

        if path.is_symlink():
            raise ValueError("discussion store path must not be a symlink")
        with path.open("ab") as handle:
            handle.write(_canonical_bytes(canonical))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o640)

    return {
        "schema": "agentos.discussion-append-receipt/v1",
        "ok": True,
        "persisted": True,
        "discussion_id": canonical["discussion_id"],
        "project_id": canonical["project_id"],
        "semantic_digest": canonical["semantic_digest"],
        "credential_exposed": False,
    }


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in TOKEN_RE.finditer(text)}


def score_record(record: dict[str, Any], query: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    semantic = record["semantic"]
    haystack = " ".join(
        [semantic["summary"], *semantic["topics"], *semantic["entities"], *semantic["keywords"]]
    )
    overlap = len(query_tokens & _tokens(haystack)) / len(query_tokens)
    phrase_boost = 0.35 if query.casefold() in haystack.casefold() else 0.0
    exact_tag_boost = (
        0.15
        if any(
            query.casefold() == item.casefold()
            for item in semantic["topics"] + semantic["entities"] + semantic["keywords"]
        )
        else 0.0
    )
    return min(1.0, overlap + phrase_boost + exact_tag_boost)


def search_records(
    records: Iterable[dict[str, Any]],
    *,
    text: str,
    project_id: str | None = None,
    node_id: str | None = None,
    surface: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    query = _bounded_string(text, "text", required=True, max_len=2048)
    safe_limit = max(1, min(int(limit), 50))
    hits: list[tuple[float, dict[str, Any]]] = []

    for raw in records:
        record = validate_record(raw)
        if project_id and record["project_id"] != project_id:
            continue
        if node_id and record["provenance"]["node_id"] != node_id:
            continue
        if surface and record["provenance"]["surface"] != surface:
            continue
        score = score_record(record, query)
        if score <= 0:
            continue
        hits.append((score, record))

    hits.sort(
        key=lambda item: (
            -item[0],
            item[1]["observed_start"],
            item[1]["discussion_id"],
        )
    )
    results = []
    for score, record in hits[:safe_limit]:
        results.append(
            {
                "score": round(score, 6),
                "discussion_id": record["discussion_id"],
                "project_id": record["project_id"],
                "observed_start": record["observed_start"],
                "observed_end": record["observed_end"],
                "provenance": record["provenance"],
                "summary": record["semantic"]["summary"],
                "topics": record["semantic"]["topics"],
                "refs": record["refs"],
                "promoted_to": record["promoted_to"],
                "semantic_digest": record["semantic_digest"],
            }
        )
    return {
        "schema": SEARCH_RESULT_SCHEMA,
        "query": query,
        "count": len(results),
        "results": results,
        "read_only": True,
        "canonical_authority": False,
    }


def search_from_one(
    *,
    project_id: str,
    text: str,
    node_id: str | None = None,
    surface: str | None = None,
    limit: int = 10,
    data_root: Path | None = None,
) -> dict[str, Any]:
    return search_records(
        read_records(project_id, data_root=data_root),
        text=text,
        project_id=project_id,
        node_id=node_id,
        surface=surface,
        limit=limit,
    )
