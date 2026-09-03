#!/usr/bin/env python3
"""Sanitized Oracle executor discovery for AgentOS Core Issue #117.

This probe is deliberately read-only. It discovers executable surfaces and
identity/session *signals* without persisting credentials, prompts, environment
variables, or session contents.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from typing import Any

UBUNTU_HOME = Path("/home/ubuntu")
ANTIGRAVITY_EXTENSION_ROOTS = (
    UBUNTU_HOME / ".antigravity-ide-server" / "extensions",
    UBUNTU_HOME / ".antigravity-server" / "extensions",
)
CODEX_HOME = UBUNTU_HOME / ".codex"
MAX_CAPTURE = 2000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stat_summary(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return result
    try:
        st = path.stat()
        result.update(
            {
                "type": "dir" if path.is_dir() else "file",
                "mode": oct(st.st_mode & 0o777),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "uid": st.st_uid,
                "gid": st.st_gid,
            }
        )
        try:
            result["owner"] = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            result["owner"] = None
    except Exception as exc:
        result["stat_error"] = f"{type(exc).__name__}: {exc}"
    return result


def can_sudo_ubuntu() -> bool:
    try:
        proc = subprocess.run(
            ["sudo", "-n", "-u", "ubuntu", "/usr/bin/id", "-u"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "1001"
    except Exception:
        return False


def ubuntu_argv(argv: list[str], *, sudo_ok: bool) -> tuple[list[str], dict[str, str], str]:
    env = {**os.environ, "HOME": str(UBUNTU_HOME), "CI": "1"}
    if os.geteuid() == 1001:
        return argv, env, "ubuntu-current"
    if sudo_ok:
        return ["sudo", "-n", "-u", "ubuntu", "env", f"HOME={UBUNTU_HOME}", "CI=1", *argv], os.environ.copy(), "sudo-ubuntu"
    return argv, env, "runner-with-ubuntu-home"


def run_probe(argv: list[str], *, sudo_ok: bool, timeout: int = 15) -> dict[str, Any]:
    launched, env, identity_mode = ubuntu_argv(argv, sudo_ok=sudo_ok)
    result: dict[str, Any] = {
        "identity_mode": identity_mode,
        "argv_family": Path(argv[0]).name + " " + " ".join(argv[1:3]),
    }
    try:
        proc = subprocess.run(
            launched,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env,
        )
        result.update(
            {
                "returncode": proc.returncode,
                "timed_out": False,
                "stdout_tail": (proc.stdout or "")[-MAX_CAPTURE:],
                "stderr_tail": (proc.stderr or "")[-MAX_CAPTURE:],
            }
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        result.update(
            {
                "returncode": None,
                "timed_out": True,
                "stdout_tail": stdout[-MAX_CAPTURE:],
                "stderr_tail": stderr[-MAX_CAPTURE:],
            }
        )
    except Exception as exc:
        result.update(
            {
                "returncode": None,
                "timed_out": False,
                "launch_error": f"{type(exc).__name__}: {exc}",
                "stdout_tail": "",
                "stderr_tail": "",
            }
        )
    return result


def sanitize_auth_probe(raw: dict[str, Any], family: str) -> dict[str, Any]:
    """Reduce auth command output to non-secret state labels."""
    text = f"{raw.get('stdout_tail', '')}\n{raw.get('stderr_tail', '')}".strip()
    lowered = text.lower()
    state = "unknown"
    method = None
    if family == "codex":
        if raw.get("returncode") == 0 and ("logged in" in lowered or "chatgpt" in lowered or "api key" in lowered):
            state = "logged_in"
        elif "not logged in" in lowered or "login required" in lowered:
            state = "not_logged_in"
        if "chatgpt" in lowered:
            method = "chatgpt"
        elif "api key" in lowered:
            method = "api_key"
    elif family == "claude":
        parsed = None
        try:
            parsed = json.loads(raw.get("stdout_tail") or "")
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            logged = parsed.get("loggedIn")
            if isinstance(logged, bool):
                state = "logged_in" if logged else "not_logged_in"
            value = parsed.get("authMethod") or parsed.get("auth_method")
            if isinstance(value, str) and value:
                method = value[:80]
        elif raw.get("returncode") == 0:
            state = "logged_in"
        elif "not logged" in lowered or "login" in lowered:
            state = "not_logged_in"
    return {
        "identity_mode": raw.get("identity_mode"),
        "returncode": raw.get("returncode"),
        "timed_out": raw.get("timed_out"),
        "launch_error": raw.get("launch_error"),
        "state": state,
        "method": method,
    }


def sanitize_version_probe(raw: dict[str, Any]) -> dict[str, Any]:
    text = (raw.get("stdout_tail") or raw.get("stderr_tail") or "").strip()
    return {
        "identity_mode": raw.get("identity_mode"),
        "returncode": raw.get("returncode"),
        "timed_out": raw.get("timed_out"),
        "launch_error": raw.get("launch_error"),
        "version_text": text[:300] if text else None,
    }


def extension_manifests(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not root.is_dir():
        return items
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name)
    except Exception:
        return items
    for child in children:
        low = child.name.lower()
        if not any(token in low for token in ("claude", "codex", "openai", "chatgpt")):
            continue
        item: dict[str, Any] = {"extension_dir": child.name}
        package = child / "package.json"
        if package.is_file():
            try:
                data = json.loads(package.read_text(encoding="utf-8"))
                for key in ("name", "displayName", "publisher", "version"):
                    value = data.get(key)
                    if isinstance(value, str):
                        item[key] = value[:200]
            except Exception as exc:
                item["package_read_error"] = type(exc).__name__
        items.append(item)
    return items


def find_executables(root: Path, family: str) -> list[str]:
    if not root.is_dir():
        return []
    found: list[str] = []
    family_tokens = {"codex": ("codex",), "claude": ("claude",)}[family]
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) >= 7:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", "out", "dist"}]
        for filename in filenames:
            low = filename.lower()
            if not any(token in low for token in family_tokens):
                continue
            path = Path(dirpath) / filename
            try:
                if path.is_file() and os.access(path, os.X_OK):
                    found.append(str(path))
            except OSError:
                continue
    return sorted(set(found))


def proc_executor_paths() -> dict[str, list[str]]:
    result = {"codex": [], "claude": []}
    proc = Path("/proc")
    for child in proc.iterdir():
        if not child.name.isdigit():
            continue
        try:
            comm = (child / "comm").read_text(encoding="utf-8").strip().lower()
        except Exception:
            continue
        family = None
        if "codex" in comm:
            family = "codex"
        elif "claude" in comm:
            family = "claude"
        if family is None:
            continue
        try:
            exe = str((child / "exe").resolve())
        except Exception:
            exe = None
        if exe and exe not in result[family]:
            result[family].append(exe)
    for values in result.values():
        values.sort()
    return result


def codex_state_summary() -> dict[str, Any]:
    result: dict[str, Any] = {"home": stat_summary(CODEX_HOME), "known_files": {}, "session_roots": []}
    for name in ("auth.json", "config.toml", ".env", "version.json"):
        result["known_files"][name] = stat_summary(CODEX_HOME / name)
    for name in ("sessions", "archived_sessions"):
        root = CODEX_HOME / name
        item: dict[str, Any] = {"name": name, **stat_summary(root)}
        if root.is_dir():
            count = 0
            newest_mtime = None
            newest_rel = None
            try:
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    count += 1
                    try:
                        mtime = path.stat().st_mtime
                    except Exception:
                        continue
                    if newest_mtime is None or mtime > newest_mtime:
                        newest_mtime = mtime
                        newest_rel = str(path.relative_to(root))
            except Exception as exc:
                item["scan_error"] = f"{type(exc).__name__}: {exc}"
            item["file_count"] = count
            if newest_mtime is not None:
                item["newest_mtime"] = datetime.fromtimestamp(newest_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                item["newest_file_basename"] = Path(newest_rel or "").name[:200]
        result["session_roots"].append(item)
    return result


def select_best(paths: list[str], family: str) -> str | None:
    if not paths:
        return None
    exact = [p for p in paths if Path(p).name.lower() == family]
    if exact:
        return sorted(exact)[-1]
    return sorted(paths)[-1]


def discover() -> dict[str, Any]:
    sudo_ok = can_sudo_ubuntu()
    proc_paths = proc_executor_paths()
    roots: list[dict[str, Any]] = []
    codex_paths: list[str] = []
    claude_paths: list[str] = []
    for root in ANTIGRAVITY_EXTENSION_ROOTS:
        codex = find_executables(root, "codex")
        claude = find_executables(root, "claude")
        codex_paths.extend(codex)
        claude_paths.extend(claude)
        roots.append({"root": stat_summary(root), "relevant_extensions": extension_manifests(root), "codex_executables": codex, "claude_executables": claude})
    codex_paths.extend(proc_paths["codex"])
    claude_paths.extend(proc_paths["claude"])
    path_codex = shutil.which("codex")
    if path_codex:
        codex_paths.append(path_codex)
    path_claude = shutil.which("claude")
    if path_claude:
        claude_paths.append(path_claude)
    codex_paths = sorted(set(codex_paths))
    claude_paths = sorted(set(claude_paths))
    codex_exe = select_best(codex_paths, "codex")
    claude_exe = select_best(claude_paths, "claude")

    codex_probes: dict[str, Any] = {}
    if codex_exe:
        codex_probes["version"] = sanitize_version_probe(run_probe([codex_exe, "--version"], sudo_ok=sudo_ok, timeout=10))
        codex_probes["auth"] = sanitize_auth_probe(run_probe([codex_exe, "login", "status"], sudo_ok=sudo_ok, timeout=15), "codex")

    claude_probes: dict[str, Any] = {}
    if claude_exe:
        claude_probes["version"] = sanitize_version_probe(run_probe([claude_exe, "--version"], sudo_ok=sudo_ok, timeout=10))
        claude_probes["auth"] = sanitize_auth_probe(run_probe([claude_exe, "auth", "status"], sudo_ok=sudo_ok, timeout=15), "claude")
        liveness = run_probe([claude_exe, "--bare", "--print", "--output-format", "text", "--effort", "low", "Return exactly OK."], sudo_ok=sudo_ok, timeout=30)
        claude_probes["minimal_print"] = {
            "identity_mode": liveness.get("identity_mode"),
            "returncode": liveness.get("returncode"),
            "timed_out": liveness.get("timed_out"),
            "launch_error": liveness.get("launch_error"),
            "stdout_is_ok": (liveness.get("stdout_tail") or "").strip() == "OK",
            "stderr_present": bool((liveness.get("stderr_tail") or "").strip()),
        }

    return {
        "schema": "agentos.oracle-executor-discovery/v0",
        "timestamp": utc_now(),
        "runner": {"uid": os.geteuid(), "user": pwd.getpwuid(os.geteuid()).pw_name, "home": str(Path.home()), "sudo_as_ubuntu": sudo_ok},
        "antigravity_extension_roots": roots,
        "process_executor_paths": proc_paths,
        "codex": {"path_executable": path_codex, "candidate_executables": codex_paths, "selected_executable": codex_exe, "state": codex_state_summary(), "probes": codex_probes},
        "claude": {"path_executable": path_claude, "candidate_executables": claude_paths, "selected_executable": claude_exe, "probes": claude_probes},
        "redaction": "Read-only sanitized metadata only. No auth/session/config contents, tokens, environment variables, prompts, or arbitrary process command lines are persisted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = discover()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"runner": result["runner"], "codex_selected": result["codex"]["selected_executable"], "codex_auth": result["codex"]["probes"].get("auth"), "codex_sessions": result["codex"]["state"].get("session_roots"), "claude_selected": result["claude"]["selected_executable"], "claude_auth": result["claude"]["probes"].get("auth"), "claude_minimal_print": result["claude"]["probes"].get("minimal_print")}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
