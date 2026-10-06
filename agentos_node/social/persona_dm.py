from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PersonaDMBinding:
    persona_id: str
    account: str
    runtime_key: str
    decision_policy: str
    auto_reply: bool
    max_auto_hops: int
    cooldown_seconds: int

_BINDINGS = {
    "mio": PersonaDMBinding("mio", "mio.milkcat", "mio", "mio", True, 2, 120),
    "oursong": PersonaDMBinding("oursong", "oursong_alstonhuang", "oursong", "oursong", False, 2, 120),
}

def binding_for(persona_id: str) -> PersonaDMBinding:
    key=str(persona_id or "").strip().lower()
    try:
        return _BINDINGS[key]
    except KeyError as exc:
        raise ValueError("persona DM binding is not allowlisted") from exc

def bindings() -> tuple[PersonaDMBinding, ...]:
    return tuple(_BINDINGS.values())
