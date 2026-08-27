"""Bounded Codex app-server executor for AgentOS.

This adapter deliberately exposes a cognitive, read-only execution surface
rather than an arbitrary Codex CLI. Model/effort are administrator-owned,
threads are ephemeral, approvals are never granted, the workspace is empty,
and any tool/command/file side-effect item makes the execution fail closed.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
from typing import Any, Protocol


RECEIPT_SCHEMA = "agentos.codex-executor-receipt/v0.1"
WORKING_SET_SCHEMA = "agentos.executor-working-set/v0.1"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_EFFORT = "low"
ALLOWED_ITEM_TYPES = {"userMessage", "agentMessage", "reasoning", "plan"}


class CodexSession(Protocol):
    def run(
        self,
        *,
        model: str,
        effort: str,
        cwd: Path,
        prompt: str,
        timeout_seconds: int,
    ) -> dict[str, Any]: ...


def discover_codex_binary() -> Path:
    patterns = [
        str(Path.home() / ".antigravity-ide-server/extensions/openai.chatgpt-*-linux-arm64/bin/linux-aarch64/codex"),
        str(Path.home() / ".antigravity-ide-server/extensions/openai.chatgpt-*/bin/linux-aarch64/codex"),
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        raise RuntimeError("no Codex binary discovered under the Antigravity extension tree")
    return Path(sorted(set(candidates), reverse=True)[0])


class StdioCodexAppServerSession:
    def __init__(self, binary: Path | None = None) -> None:
        self.binary = binary or discover_codex_binary()

    def run(
        self,
        *,
        model: str,
        effort: str,
        cwd: Path,
        prompt: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        proc = subprocess.Popen(
            [str(self.binary), "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(cwd),
        )
        assert proc.stdin and proc.stdout and proc.stderr
        responses: dict[int, dict[str, Any]] = {}
        notifications: list[str] = []
        server_requests: list[str] = []
        agent_texts: list[str] = []
        item_types: list[str] = []
        forbidden_items: list[str] = []
        completed_turn_id: str | None = None

        def send(message: dict[str, Any]) -> None:
            proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            proc.stdin.flush()

        def handle(message: Any) -> None:
            nonlocal completed_turn_id
            if not isinstance(message, dict):
                return
            method = message.get("method")
            if "id" in message and not method:
                try:
                    responses[int(message["id"])] = message
                except (TypeError, ValueError):
                    pass
                return
            if method and "id" in message:
                server_requests.append(str(method))
                if str(method).endswith("requestApproval"):
                    send({"id": message["id"], "result": {"decision": "decline"}})
                elif method == "currentTime/read":
                    send({"id": message["id"], "result": {"currentTimeAt": int(time.time())}})
                else:
                    send({"id": message["id"], "error": {"code": -32000, "message": "unsupported by bounded AgentOS executor"}})
                return
            if not method:
                return
            notifications.append(str(method))
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            if method == "turn/completed":
                turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
                raw_turn_id = turn.get("id") or params.get("turnId")
                if raw_turn_id:
                    completed_turn_id = str(raw_turn_id)
            if method == "item/completed":
                item = params.get("item") if isinstance(params.get("item"), dict) else {}
                item_type = item.get("type")
                if item_type:
                    item_type = str(item_type)
                    item_types.append(item_type)
                    if item_type not in ALLOWED_ITEM_TYPES:
                        forbidden_items.append(item_type)
                if item_type == "agentMessage" and isinstance(item.get("text"), str):
                    agent_texts.append(item["text"])

        def pump_until(predicate: Any, seconds: float) -> bool:
            deadline = time.time() + seconds
            while time.time() < deadline:
                if predicate():
                    return True
                ready, _, _ = select.select([proc.stdout], [], [], 0.5)
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue
                line = proc.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                handle(message)
            return bool(predicate())

        try:
            send({
                "method": "initialize",
                "id": 0,
                "params": {"clientInfo": {"name": "agentos_codex_executor", "title": "AgentOS bounded Codex executor", "version": "0.1.0"}},
            })
            if not pump_until(lambda: 0 in responses, 8) or "error" in responses.get(0, {}):
                raise RuntimeError(f"Codex app-server initialize failed: {responses.get(0)}")
            send({"method": "initialized", "params": {}})
            send({
                "method": "thread/start",
                "id": 10,
                "params": {
                    "model": model,
                    "cwd": str(cwd),
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "ephemeral": True,
                    "config": {"model_reasoning_effort": effort},
                },
            })
            if not pump_until(lambda: 10 in responses, 10) or "error" in responses.get(10, {}):
                raise RuntimeError(f"Codex app-server thread/start failed: {responses.get(10)}")
            thread = (responses[10].get("result") or {}).get("thread") or {}
            thread_id = str(thread.get("id") or "")
            if not thread_id:
                raise RuntimeError("Codex app-server did not return a thread id")

            send({
                "method": "turn/start",
                "id": 20,
                "params": {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "model": model,
                    "effort": effort,
                    "approvalPolicy": "never",
                },
            })
            if not pump_until(lambda: "turn/completed" in notifications, timeout_seconds):
                raise TimeoutError("Codex app-server bounded turn timed out")
            if 20 not in responses or "error" in responses[20]:
                raise RuntimeError(f"Codex app-server turn/start failed: {responses.get(20)}")
            turn_result = responses[20].get("result") if isinstance(responses[20].get("result"), dict) else {}
            turn = turn_result.get("turn") if isinstance(turn_result.get("turn"), dict) else {}
            turn_id = str(turn.get("id") or completed_turn_id or "")
            if forbidden_items:
                raise RuntimeError("bounded Codex executor attempted forbidden item types: " + ",".join(sorted(set(forbidden_items))))
            if not agent_texts:
                raise RuntimeError("bounded Codex executor returned no agent message")
            return {
                "thread_id": thread_id,
                "turn_id": turn_id or None,
                "output_text": agent_texts[-1],
                "item_types": item_types,
                "server_requests": server_requests,
                "forbidden_items": forbidden_items,
                "notifications": notifications[-40:],
            }
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
                proc.wait(timeout=3)


class BoundedCodexExecutor:
    def __init__(self, *, session: CodexSession | None = None) -> None:
        self.session = session or StdioCodexAppServerSession()

    def execute(self, *, project_id: str, working_set: dict[str, Any], instruction: str) -> dict[str, Any]:
        if working_set.get("schema") != WORKING_SET_SCHEMA:
            raise ValueError("working_set must use agentos.executor-working-set/v0.1")
        if str(working_set.get("project_id") or "") != project_id:
            raise ValueError("working_set project_id does not match task project")
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("instruction is required")
        if len(instruction) > 8000:
            raise ValueError("instruction exceeds 8000 characters")
        serialized = json.dumps(working_set, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 65536:
            raise ValueError("working_set exceeds 64 KiB")

        model = os.getenv("AGENTOS_CODEX_EXECUTOR_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        effort = os.getenv("AGENTOS_CODEX_EXECUTOR_EFFORT", DEFAULT_EFFORT).strip() or DEFAULT_EFFORT
        timeout_seconds = int(os.getenv("AGENTOS_CODEX_EXECUTOR_TIMEOUT_SECONDS", "90"))
        if timeout_seconds < 5 or timeout_seconds > 300:
            raise ValueError("AGENTOS_CODEX_EXECUTOR_TIMEOUT_SECONDS must be between 5 and 300")

        prompt = (
            "You are a bounded AgentOS cognitive executor. Use ONLY the supplied executor working set as project state. "
            "Do not inspect files, run commands, call tools, modify anything, or request approval. Follow the instruction and return only the requested answer.\n"
            f"INSTRUCTION={instruction}\n"
            f"EXECUTOR_WORKING_SET={serialized}"
        )
        with tempfile.TemporaryDirectory(prefix="agentos-codex-bounded-") as directory:
            outcome = self.session.run(
                model=model,
                effort=effort,
                cwd=Path(directory),
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )

        forbidden = outcome.get("forbidden_items") or []
        if forbidden:
            raise RuntimeError("bounded Codex executor side-effect audit failed")
        return {
            "schema": RECEIPT_SCHEMA,
            "project_id": project_id,
            "model": model,
            "reasoning_effort": effort,
            "thread_id": outcome.get("thread_id"),
            "turn_id": outcome.get("turn_id"),
            "output_text": str(outcome.get("output_text") or ""),
            "working_set_schema": working_set["schema"],
            "side_effect_audit": {
                "no_side_effects": True,
                "item_types": outcome.get("item_types") or [],
                "server_requests": outcome.get("server_requests") or [],
                "forbidden_items": [],
            },
        }
