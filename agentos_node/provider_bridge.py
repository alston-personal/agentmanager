"""Agent Provider Bridge for Distributed AgentOS.

The bridge turns model/provider APIs into one capability runtime. Providers only
return semantic output; trusted AgentOS code owns task leasing, input binding,
and continuation lineage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeResult

from .control_plane_client import ControlPlaneClient
from .web_agent_adapter import RESPONSE_PROTOCOL, WebAgentAdapter


DISPATCH_PROTOCOL = "agentos.runtime-dispatch/v1"
PROVIDER_REQUEST_PROTOCOL = "agentos.provider-request/v1"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ProviderError(RuntimeError):
    pass


def _json_from_model_text(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"provider did not return valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProviderError("provider semantic response must be a JSON object")
    return value


def _validate_semantic_response(value: dict[str, Any]) -> dict[str, Any]:
    status = value.get("status")
    if status not in {"succeeded", "failed"}:
        raise ProviderError("provider status must be succeeded or failed")
    result = value.get("result")
    if not isinstance(result, dict):
        raise ProviderError("provider result must be an object")
    next_capability = value.get("next_capability")
    if next_capability is not None and not isinstance(next_capability, str):
        raise ProviderError("provider next_capability must be a string")
    auto_continue = value.get("auto_continue", False)
    if not isinstance(auto_continue, bool):
        raise ProviderError("provider auto_continue must be boolean")
    continuation = value.get("continuation") or {}
    if not isinstance(continuation, dict):
        raise ProviderError("provider continuation metadata must be an object")
    return {
        "status": status,
        "result": result,
        "next_capability": next_capability,
        "auto_continue": auto_continue,
        "continuation": continuation,
    }


def _provider_prompt(request_envelope: dict[str, Any]) -> str:
    return (
        "You are an execution provider inside Distributed AgentOS.\n"
        "Read the Canonical IR and perform only the requested capability.\n"
        "Return exactly one JSON object with these fields:\n"
        "- status: succeeded or failed\n"
        "- result: JSON object containing your semantic output\n"
        "- next_capability: optional string\n"
        "- auto_continue: optional boolean (default false)\n"
        "- continuation: optional non-authoritative metadata object\n"
        "Do not create continuation_ir and do not modify project_id, ir_id, parent_ir_id, digest, or hop_count.\n"
        "No Markdown fences or prose outside the JSON object.\n\n"
        "AgentOS request envelope:\n"
        + json.dumps(request_envelope, ensure_ascii=False, sort_keys=True)
    )


class ProviderAdapter(ABC):
    provider_id: str

    @abstractmethod
    def invoke(self, request_envelope: dict[str, Any]) -> dict[str, Any]:
        """Return an untrusted semantic response object."""


class _HTTPProvider(ProviderAdapter):
    def __init__(
        self,
        provider_id: str,
        *,
        timeout: float = 90.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not provider_id:
            raise ValueError("provider_id is required")
        self.provider_id = provider_id
        self.timeout = timeout
        self.opener = opener

    def _send(self, request: Request) -> dict[str, Any]:
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ProviderError(f"provider HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise ProviderError(f"provider unavailable: {exc.reason}") from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("provider HTTP response is not JSON") from exc
        if not isinstance(value, dict):
            raise ProviderError("provider HTTP response root must be an object")
        return value


class OpenAIResponsesProvider(_HTTPProvider):
    """Direct OpenAI Responses API adapter."""

    def __init__(
        self,
        provider_id: str,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 90.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        super().__init__(provider_id, timeout=timeout, opener=opener)
        if not model or not api_key:
            raise ValueError("OpenAI model and api_key are required")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def invoke(self, request_envelope: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}/responses",
            data=json.dumps({"model": self.model, "input": _provider_prompt(request_envelope)}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = self._send(request)
        text = payload.get("output_text")
        if not isinstance(text, str):
            fragments: list[str] = []
            for item in payload.get("output") or []:
                if not isinstance(item, dict):
                    continue
                for content in item.get("content") or []:
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        fragments.append(content["text"])
            text = "".join(fragments)
        if not text:
            raise ProviderError("OpenAI Responses payload contains no output text")
        return _validate_semantic_response(_json_from_model_text(text))


class OpenAICompatibleChatProvider(_HTTPProvider):
    """OpenAI-compatible /chat/completions adapter for LiteLLM/Ollama proxies."""

    def __init__(
        self,
        provider_id: str,
        *,
        model: str,
        api_key: str = "",
        base_url: str,
        timeout: float = 90.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        super().__init__(provider_id, timeout=timeout, opener=opener)
        if not model or not base_url:
            raise ValueError("chat provider model and base_url are required")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def invoke(self, request_envelope: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": _provider_prompt(request_envelope)}],
                    "stream": False,
                }
            ).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        payload = self._send(request)
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unexpected OpenAI-compatible chat response shape") from exc
        if not isinstance(text, str):
            raise ProviderError("chat completion content must be text")
        return _validate_semantic_response(_json_from_model_text(text))


class GeminiGenerateContentProvider(_HTTPProvider):
    """Google Gemini generateContent adapter with JSON response mode."""

    def __init__(
        self,
        provider_id: str,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 90.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        super().__init__(provider_id, timeout=timeout, opener=opener)
        if not model or not api_key:
            raise ValueError("Gemini model and api_key are required")
        self.model = model.removeprefix("models/")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def invoke(self, request_envelope: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/models/{quote(self.model, safe='.-_')}:generateContent"
        request = Request(
            url,
            data=json.dumps(
                {
                    "contents": [{"parts": [{"text": _provider_prompt(request_envelope)}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                }
            ).encode("utf-8"),
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = self._send(request)
        fragments: list[str] = []
        for candidate in payload.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            if not isinstance(content, dict):
                continue
            for part in content.get("parts") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    fragments.append(part["text"])
        text = "".join(fragments)
        if not text:
            raise ProviderError("Gemini payload contains no generated text")
        return _validate_semantic_response(_json_from_model_text(text))


class RelayWebhookProvider(_HTTPProvider):
    """Relay adapter for browser extensions, desktop bridges, or vendor agents."""

    def __init__(
        self,
        provider_id: str,
        *,
        endpoint: str,
        token: str | None = None,
        timeout: float = 90.0,
        allow_insecure_http: bool = False,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        super().__init__(provider_id, timeout=timeout, opener=opener)
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("relay endpoint must be absolute http(s)")
        if parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS and not allow_insecure_http:
            raise ValueError("non-loopback relay endpoint requires HTTPS")
        self.endpoint = endpoint
        self.token = token

    def invoke(self, request_envelope: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            self.endpoint,
            data=json.dumps(
                {
                    "protocol": PROVIDER_REQUEST_PROTOCOL,
                    "provider_id": self.provider_id,
                    "request": request_envelope,
                    "instruction": _provider_prompt(request_envelope),
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        payload = self._send(request)
        semantic = payload.get("semantic_response", payload)
        if not isinstance(semantic, dict):
            raise ProviderError("relay semantic_response must be an object")
        return _validate_semantic_response(semantic)


@dataclass(frozen=True)
class ProviderRegistration:
    adapter: ProviderAdapter
    capabilities: tuple[str, ...]
    priority: int = 100

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class ProviderRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, ProviderRegistration] = {}

    def register(
        self,
        adapter: ProviderAdapter,
        capabilities: Iterable[str],
        *,
        priority: int = 100,
    ) -> None:
        normalized = tuple(sorted({item for item in capabilities if isinstance(item, str) and item}))
        if not normalized:
            raise ValueError("provider capabilities are required")
        self._registrations[adapter.provider_id] = ProviderRegistration(adapter, normalized, priority)

    @property
    def capabilities(self) -> list[str]:
        return sorted({cap for reg in self._registrations.values() for cap in reg.capabilities})

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "providerId": provider_id,
                "capabilities": list(reg.capabilities),
                "priority": reg.priority,
                "adapter": type(reg.adapter).__name__,
            }
            for provider_id, reg in sorted(
                self._registrations.items(), key=lambda item: (item[1].priority, item[0])
            )
        ]

    def resolve(self, ir: CanonicalIR) -> ProviderAdapter:
        policy = ir.context.get("provider_policy") if isinstance(ir.context, dict) else None
        policy = policy if isinstance(policy, dict) else {}
        denied = {
            item for item in (policy.get("deny_providers") or [])
            if isinstance(item, str)
        }
        candidates = [
            (provider_id, reg)
            for provider_id, reg in self._registrations.items()
            if reg.supports(ir.capability) and provider_id not in denied
        ]
        preferred = policy.get("preferred_provider")
        if isinstance(preferred, str):
            for provider_id, reg in candidates:
                if provider_id == preferred:
                    return reg.adapter
        if not candidates:
            raise ProviderError(f"no provider registered for capability {ir.capability}")
        candidates.sort(key=lambda item: (item[1].priority, item[0]))
        return candidates[0][1].adapter


class AgentProviderBridge:
    """Lease an exact dispatched task, call a provider, and complete it safely."""

    def __init__(
        self,
        runtime_id: str,
        registry: ProviderRegistry,
        *,
        control_plane_url: str | None = None,
        control_plane_token: str | None = None,
        lease_seconds: int = 300,
        allow_insecure_control_plane: bool = False,
    ) -> None:
        if not runtime_id:
            raise ValueError("runtime_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        self.runtime_id = runtime_id
        self.registry = registry
        self.control_plane_url = control_plane_url
        self.control_plane_token = control_plane_token
        self.lease_seconds = lease_seconds
        self.allow_insecure_control_plane = allow_insecure_control_plane

    def _client(self, envelope: dict[str, Any]) -> ControlPlaneClient:
        url = str(envelope.get("control_plane_url") or self.control_plane_url or "")
        if not url:
            raise ProviderError("dispatch envelope has no control_plane_url")
        return ControlPlaneClient(
            url,
            token=self.control_plane_token,
            allow_insecure_http=self.allow_insecure_control_plane,
        )

    def process_dispatch(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope.get("protocol") != DISPATCH_PROTOCOL:
            raise ProviderError("unsupported runtime dispatch protocol")
        task_id = str(envelope.get("task_id") or "")
        runtime_id = str(envelope.get("runtime_id") or "")
        if not task_id or runtime_id != self.runtime_id:
            raise ProviderError("dispatch task_id/runtime_id binding is invalid")
        raw_ir = envelope.get("canonical_ir")
        if not isinstance(raw_ir, dict):
            raise ProviderError("dispatch canonical_ir must be an object")
        announced_ir = CanonicalIR.from_dict(raw_ir)
        if envelope.get("input_digest") != announced_ir.digest():
            raise ProviderError("dispatch Canonical IR digest mismatch")
        if envelope.get("capability") != announced_ir.capability:
            raise ProviderError("dispatch capability mismatch")

        client = self._client(envelope)
        lease = client.lease_task(task_id, self.runtime_id, lease_seconds=self.lease_seconds)
        if lease is None:
            return {
                "status": "duplicate_or_claimed",
                "task_id": task_id,
                "runtime_id": self.runtime_id,
            }
        if str(lease.get("taskId")) != task_id:
            raise ProviderError("Control Plane returned the wrong exact task lease")
        raw_leased_ir = lease.get("canonicalIR")
        if not isinstance(raw_leased_ir, dict):
            raise ProviderError("lease Canonical IR must be an object")
        ir = CanonicalIR.from_dict(raw_leased_ir)
        if lease.get("inputDigest") != ir.digest() or ir.digest() != announced_ir.digest():
            raise ProviderError("leased Canonical IR does not match dispatched IR")

        adapter = self.registry.resolve(ir)
        web_adapter = WebAgentAdapter(self.runtime_id)
        provider_request = web_adapter.build_request(ir)
        try:
            semantic = adapter.invoke(provider_request)
            continuation = dict(semantic.get("continuation") or {})
            continuation["provider_id"] = adapter.provider_id
            trusted_response = {
                "protocol": RESPONSE_PROTOCOL,
                "runtime_id": self.runtime_id,
                "input_ir_id": ir.ir_id,
                "input_digest": ir.digest(),
                "status": semantic["status"],
                "result": semantic["result"],
                "auto_continue": semantic.get("auto_continue", False),
                "continuation": continuation,
            }
            if semantic.get("next_capability"):
                trusted_response["next_capability"] = semantic["next_capability"]
            result = web_adapter.consume_response(ir, trusted_response)
        except Exception as exc:
            result = RemoteRuntimeResult(
                status="failed",
                runtime_id=self.runtime_id,
                input_ir_id=ir.ir_id,
                input_digest=ir.digest(),
                result={
                    "error": "provider_failed",
                    "provider_id": adapter.provider_id,
                    "message": str(exc),
                },
            )

        completed = client.complete(task_id, result)
        return {
            "status": result.status,
            "task_id": task_id,
            "runtime_id": self.runtime_id,
            "provider_id": adapter.provider_id,
            "completed": completed,
        }
