from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


WORK_INTENT_REF_SCHEMA = "agentos.employee-work-intent-ref/v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class WorkIntentRef:
    """Content-addressed pointer to product-owned work state.

    The reference is deliberately non-executable.  It carries no URL, path,
    command, module, argv, environment, credential, transport, or Node authority.
    Product adapters may resolve a recognized ``product_id``/``state_key`` pair
    through their own fixed source-controlled boundary and MUST verify ``digest``
    before consuming the referenced state.
    """

    schema: str
    product_id: str
    state_key: str
    revision: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def identity(self) -> str:
        return f"{self.product_id}\0{self.state_key}\0{self.revision}\0{self.digest}"


def _token(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not _TOKEN_RE.fullmatch(text):
        raise ValueError(f"invalid_work_intent_{field}")
    lowered = text.casefold()
    if lowered.startswith(("http:", "https:", "file:", "ssh:")) or ".." in text:
        raise ValueError(f"invalid_work_intent_{field}")
    return text


def parse_work_intent_ref(value: Mapping[str, Any] | WorkIntentRef | None) -> WorkIntentRef | None:
    if value is None:
        return None
    if isinstance(value, WorkIntentRef):
        candidate = value
    else:
        if not isinstance(value, Mapping):
            raise ValueError("invalid_work_intent_ref")
        allowed = {"schema", "product_id", "state_key", "revision", "digest"}
        if set(value) != allowed:
            raise ValueError("invalid_work_intent_ref_fields")
        candidate = WorkIntentRef(
            schema=str(value.get("schema") or ""),
            product_id=_token(value.get("product_id"), field="product_id"),
            state_key=_token(value.get("state_key"), field="state_key"),
            revision=int(value.get("revision") or 0),
            digest=str(value.get("digest") or ""),
        )

    if candidate.schema != WORK_INTENT_REF_SCHEMA:
        raise ValueError("invalid_work_intent_ref_schema")
    _token(candidate.product_id, field="product_id")
    _token(candidate.state_key, field="state_key")
    if candidate.revision < 1:
        raise ValueError("invalid_work_intent_revision")
    if not _DIGEST_RE.fullmatch(candidate.digest):
        raise ValueError("invalid_work_intent_digest")
    return candidate
