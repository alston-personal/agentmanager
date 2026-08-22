"""Thin adapter over the external `ai-browser-bridge` CLI.

AgentOS intentionally does not own browser automation, provider DOM selectors,
Chrome profiles, or login persistence. This module only wraps the bridge's
stable non-interactive CLI surfaces and returns untrusted semantic results.

Live browser/session verification remains an operator/device concern.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class BrowserBridgeReply:
    provider: str
    ok: bool
    reply: str | None = None
    error: str | None = None
    elapsed_ms: int | None = None


@dataclass(frozen=True)
class BrowserConversationMatch:
    provider: str
    conversation_id: str | None
    title: str | None
    url: str


Runner = Callable[[Sequence[str], float], str]


def _default_runner(command: Sequence[str], timeout: float) -> str:
    completed = subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.stdout


class AiBrowserBridgeClient:
    """Stable AgentOS boundary around `bridge ask/search ... --json`."""

    def __init__(
        self,
        *,
        executable: str = "bridge",
        runner: Runner = _default_runner,
    ) -> None:
        self.executable = executable
        self.runner = runner

    def ask(
        self,
        prompt: str,
        *,
        providers: Sequence[str] = ("chatgpt",),
        timeout_seconds: float = 180.0,
    ) -> tuple[BrowserBridgeReply, ...]:
        prompt = str(prompt or "").strip()
        normalized = tuple(dict.fromkeys(str(item).strip() for item in providers if str(item).strip()))
        if not prompt:
            raise ValueError("prompt is required")
        if not normalized:
            raise ValueError("at least one provider is required")
        # Prompt is passed as one subprocess argv item, never through a shell.
        command = [
            self.executable,
            "ask",
            "--provider",
            ",".join(normalized),
            "--json",
            prompt,
        ]
        raw = self.runner(command, timeout_seconds)
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise RuntimeError("ai-browser-bridge ask output must be a JSON object")

        replies: list[BrowserBridgeReply] = []
        # Multi-provider bridge output is keyed by provider. For a future bridge
        # version returning a single result object, normalize it to the requested
        # provider when unambiguous.
        if "ok" in payload and len(normalized) == 1:
            payload = {normalized[0]: payload}
        for provider in normalized:
            item = payload.get(provider)
            if not isinstance(item, Mapping):
                replies.append(
                    BrowserBridgeReply(
                        provider=provider,
                        ok=False,
                        error="provider missing from bridge response",
                    )
                )
                continue
            replies.append(
                BrowserBridgeReply(
                    provider=provider,
                    ok=bool(item.get("ok")),
                    reply=str(item.get("reply")) if item.get("reply") is not None else None,
                    error=str(item.get("error")) if item.get("error") is not None else None,
                    elapsed_ms=int(item["elapsedMs"]) if item.get("elapsedMs") is not None else None,
                )
            )
        return tuple(replies)

    def search_conversations(
        self,
        query: str,
        *,
        providers: Sequence[str] = ("chatgpt",),
        limit: int = 10,
        timeout_seconds: float = 60.0,
    ) -> tuple[BrowserConversationMatch, ...]:
        query = str(query or "").strip()
        normalized = tuple(dict.fromkeys(str(item).strip() for item in providers if str(item).strip()))
        if not query:
            raise ValueError("query is required")
        if not normalized:
            raise ValueError("at least one provider is required")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        command = [
            self.executable,
            "chat",
            "search",
            query,
            "--provider",
            ",".join(normalized),
            "--limit",
            str(limit),
            "--json",
        ]
        raw = self.runner(command, timeout_seconds)
        payload = json.loads(raw)
        return self._conversation_matches(payload, normalized)

    @staticmethod
    def _conversation_matches(
        payload: Any,
        providers: Sequence[str],
    ) -> tuple[BrowserConversationMatch, ...]:
        matches: list[BrowserConversationMatch] = []

        def add(provider: str, value: Mapping[str, Any]) -> None:
            url = str(value.get("url") or value.get("href") or "").strip()
            if not url:
                return
            matches.append(
                BrowserConversationMatch(
                    provider=provider,
                    conversation_id=(
                        str(value.get("id") or value.get("conversationId"))
                        if value.get("id") is not None or value.get("conversationId") is not None
                        else None
                    ),
                    title=str(value.get("title")) if value.get("title") is not None else None,
                    url=url,
                )
            )

        # Accept the common list form and provider-keyed result form without
        # coupling AgentOS to bridge-internal provider/session representations.
        if isinstance(payload, list):
            provider = providers[0] if len(providers) == 1 else "unknown"
            for item in payload:
                if isinstance(item, Mapping):
                    add(str(item.get("provider") or provider), item)
        elif isinstance(payload, Mapping):
            for provider, value in payload.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, Mapping):
                            add(str(provider), item)
                elif isinstance(value, Mapping):
                    nested = value.get("results") or value.get("conversations")
                    if isinstance(nested, list):
                        for item in nested:
                            if isinstance(item, Mapping):
                                add(str(provider), item)
        else:
            raise RuntimeError("ai-browser-bridge search output must be JSON list/object")

        return tuple(matches)
