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
    cdp_url: str
    profile_key: str

_BINDINGS = {
    "mio": PersonaDMBinding("mio", "mio.milkcat", "mio", "mio", True, 2, 120, "http://127.0.0.1:9222", "mio"),
    "oursong": PersonaDMBinding("oursong", "oursong_alstonhuang", "oursong", "oursong", False, 2, 120, "http://127.0.0.1:9223", "oursong"),
}

def binding_for(persona_id: str) -> PersonaDMBinding:
    key=str(persona_id or "").strip().lower()
    try:
        return _BINDINGS[key]
    except KeyError as exc:
        raise ValueError("persona DM binding is not allowlisted") from exc

def bindings() -> tuple[PersonaDMBinding, ...]:
    return tuple(_BINDINGS.values())


def account_from_profile_hrefs(hrefs: list[str]) -> str | None:
    """Resolve the logged-in persona from profile-navigation href metadata only.

    This intentionally does not consume message/body text. Ambiguous or unknown
    account metadata fails closed.
    """
    from urllib.parse import urlparse, unquote

    allowed = {binding.account.lower(): binding.account for binding in bindings()}
    found: set[str] = set()
    for raw in hrefs:
        try:
            parsed = urlparse(str(raw or ""))
        except Exception:
            continue
        host = (parsed.hostname or "").lower()
        if host and host not in {"threads.com", "www.threads.com"}:
            continue
        path = unquote(parsed.path or "").strip("/")
        if not path.startswith("@"):
            continue
        handle = path[1:].split("/", 1)[0].lower()
        if handle in allowed:
            found.add(allowed[handle])
    return next(iter(found)) if len(found) == 1 else None
