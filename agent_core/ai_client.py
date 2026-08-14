"""
agent_core/ai_client.py
=======================
AgentOS 統一 AI 呼叫入口。

設計原則：
  - 所有 AI HTTP call 強制 timeout（預設 30s）
  - 外部服務失敗時回傳 error string，不 raise（除非 raise_on_error=True）
  - endpoint 從環境變數讀取，不 hardcode
  - 相容 OpenAI-compatible API（Ollama proxy、LiteLLM 等）

使用方式：
    from agent_core.ai_client import chat_completion, list_models

    # 簡單呼叫
    reply = chat_completion([{"role": "user", "content": "你好"}])
    print(reply)

    # 自訂 model / timeout
    reply = chat_completion(
        messages=[{"role": "user", "content": "分析這段文字"}],
        model="qwen3.6:35b",
        timeout=60,
    )
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

# ──────────────────────────────────────────────
# 設定（優先讀環境變數，再用預設值）
# ──────────────────────────────────────────────
_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def _load_env_once() -> None:
    """簡易 .env loader（不依賴 python-dotenv）"""
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key and key not in os.environ:  # 已設的不覆蓋
                os.environ[key] = val


_load_env_once()

DEFAULT_BASE_URL = os.environ.get(
    "AI_API_BASE_URL",
    os.environ.get("AI_BASE_URL", "https://ai-api.myacademia.uk/v1"),
)
DEFAULT_API_KEY = os.environ.get(
    "AI_API_ACADEMIA_KEY",
    os.environ.get("AI_API_KEY", ""),
)
DEFAULT_MODEL = os.environ.get("AI_DEFAULT_MODEL", "gemma4:e4b")
DEFAULT_MAX_TOKENS = int(os.environ.get("AI_DEFAULT_MAX_TOKENS", "256"))
DEFAULT_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))


# ──────────────────────────────────────────────
# 核心函式
# ──────────────────────────────────────────────

def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
    stream: bool = False,
    max_tokens: int | None = None,
    temperature: float | None = None,
    raise_on_error: bool = False,
    **extra: Any,
) -> str:
    """
    送出 chat completion 請求，回傳 assistant 的文字內容。

    失敗時（網路錯誤、timeout、API error）：
      - raise_on_error=False（預設）：回傳以 "[AI_ERROR]" 開頭的描述字串
      - raise_on_error=True：重新 raise 原始例外

    Args:
        messages: OpenAI 格式的訊息列表
        model: 模型名稱，預設讀 AI_DEFAULT_MODEL
        base_url: API base URL，預設讀 AI_API_BASE_URL，兼容 AI_BASE_URL
        api_key: Bearer token，預設讀 AI_API_ACADEMIA_KEY，兼容 AI_API_KEY
        max_tokens: 輸出 token 數；未傳時預設讀 AI_DEFAULT_MAX_TOKENS（256）
        timeout: 秒數，預設讀 AI_TIMEOUT（30s）
        stream: 是否串流（目前強制 False，串流支援待實作）
        temperature: 溫度（0.0–2.0）
        raise_on_error: True 時不 swallow 例外
        **extra: 其他傳給 API 的參數
    """
    _model = model or DEFAULT_MODEL
    _base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    _api_key = api_key or DEFAULT_API_KEY
    _timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    payload: dict[str, Any] = {
        "model": _model,
        "messages": messages,
        "stream": False,  # 串流尚未支援
        **extra,
    }
    payload["max_tokens"] = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS
    if temperature is not None:
        payload["temperature"] = temperature

    url = f"{_base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentOS/1.0",
    }
    if _api_key:
        headers["Authorization"] = f"Bearer {_api_key}"

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=_timeout) as resp:
            raw = resp.read().decode("utf-8")
    except TimeoutError as e:
        msg = f"[AI_ERROR] Timeout ({_timeout}s) calling {url} — {e}"
        if raise_on_error:
            raise TimeoutError(msg) from e
        return msg
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")[:300]
        msg = f"[AI_ERROR] HTTP {e.code} from {url} — {body_err}"
        if raise_on_error:
            raise
        return msg
    except urllib.error.URLError as e:
        msg = f"[AI_ERROR] Connection failed to {url} — {e.reason}"
        if raise_on_error:
            raise
        return msg
    except Exception as e:  # noqa: BLE001
        msg = f"[AI_ERROR] Unexpected error calling {url} — {type(e).__name__}: {e}"
        if raise_on_error:
            raise
        return msg

    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        msg = f"[AI_ERROR] Unexpected response shape — {e}\nRaw: {raw[:300]}"
        if raise_on_error:
            raise ValueError(msg) from e
        return msg


def list_models(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
) -> list[str]:
    """
    列出遠端 AI proxy 支援的模型 ID 列表。
    失敗時回傳空列表。
    """
    _base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    _api_key = api_key or DEFAULT_API_KEY
    _timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    url = f"{_base_url}/models"
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentOS/1.0",
    }
    if _api_key:
        headers["Authorization"] = f"Bearer {_api_key}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m["id"] for m in data.get("data", [])]
    except Exception:  # noqa: BLE001
        return []


def quick_check(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """
    快速健康檢查：確認 AI proxy 是否可達。

    Returns:
        {"ok": True/False, "models": [...], "error": "..." or None}
    """
    models = list_models(base_url=base_url, api_key=api_key, timeout=timeout)
    if models:
        return {"ok": True, "models": models, "error": None}

    # 嘗試呼叫一個輕量問題確認服務是否存活
    reply = chat_completion(
        [{"role": "user", "content": "hi"}],
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_tokens=5,
    )
    ok = not reply.startswith("[AI_ERROR]")
    return {
        "ok": ok,
        "models": [],
        "error": reply if not ok else None,
    }
