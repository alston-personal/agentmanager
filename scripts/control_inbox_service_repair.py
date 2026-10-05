"""Fixed-host Control Inbox maintenance; never print credentials or API bodies."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UNIT = "agentos-control-inbox.service"
ENV_PATH = Path("/home/ubuntu/.config/agentos/control-inbox.env")
CONTROLLER_PATH = Path("/home/ubuntu/.config/agentos/controller.env")
GITHUB_READ = "https://api.github.com/repos/alston-personal/agentmanager/issues/50/comments?per_page=1"
ONE_READ = "http://127.0.0.1:8780/v1/controller/nodes"
# Incident #845's observed count is the maintenance budget, not unlimited cleanup.
MAX_IGNORED_LINES = 7


class RepairFailure(Exception):
    pass


def parse_env(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            previous = text.splitlines()[line_number - 2] if line_number > 1 else ""
            previous_continuation = previous.rstrip().endswith("\\")
            export_like = line.lstrip().startswith("export ")
            raise RepairFailure(
                "environment_malformed_missing_equals_line_"
                f"{line_number}_prev_cont_{int(previous_continuation)}"
                f"_exportlike_{int(export_like)}"
            )
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise RepairFailure(f"environment_malformed_invalid_key_line_{line_number}")
        if key in result:
            raise RepairFailure(f"environment_malformed_duplicate_key_line_{line_number}")
        result[key] = value
    return result


def normalize_env_shape(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    malformed: list[int] = []
    continuation_count = 0
    export_count = 0
    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "=" in raw:
            continue
        previous = lines[index - 1].rstrip("\r\n") if index > 0 else ""
        malformed.append(index)
        continuation_count += int(previous.rstrip().endswith("\\"))
        export_count += int(raw.lstrip().startswith("export "))
    if not malformed:
        return text, False
    # EnvironmentFile ignores independent lines without '=' (systemd.exec).
    # systemd v249's KEY state treats quotes literally until '='; a quote in
    # an independent non-assignment or comment cannot open a multiline value.
    # Quotes in assignments and backslashes still reject normalization.
    # Python splitlines also recognizes separators that systemd does not.
    ignored = set(malformed)
    structural = dict(assignment_quotes=0, ignored_quotes=0, comment_quotes=0,
                      backslash=0, control=0, bare_cr=0)
    lexical_unsafe = 0
    for index, line in enumerate(lines):
        quoted = any(char in "\"'" for char in line)
        comment = not line.strip() or line.lstrip().startswith("#")
        assignment_quote = quoted and index not in ignored and not comment
        structural["assignment_quotes"] += int(assignment_quote)
        structural["ignored_quotes"] += int(quoted and index in ignored)
        structural["comment_quotes"] += int(quoted and comment)
        escaped = "\\" in line
        control = any((ord(char) < 32 and char not in "\t\r\n")
                      or ord(char) == 127 or char in "\x85\u2028\u2029\ufeff"
                      for char in line)
        bare_cr = re.search(r"\r(?!\n)", line) is not None
        structural["backslash"] += int(escaped)
        structural["control"] += int(control)
        structural["bare_cr"] += int(bare_cr)
        lexical_unsafe += int(assignment_quote or escaped or control or bare_cr)
    if len(malformed) > MAX_IGNORED_LINES or continuation_count or export_count or lexical_unsafe:
        # A parser's first failing line cannot prove the total defect count.
        # Report structural counts only; never include line text, keys or values.
        raise RepairFailure(
            "environment_shape_not_safely_normalizable"
            f"_missing_equals_{len(malformed)}"
            f"_prev_cont_{continuation_count}_exportlike_{export_count}"
            f"_lexical_unsafe_{lexical_unsafe}"
            + "".join(f"_{name}_{count}" for name, count in structural.items())
        )
    return "".join(line for i, line in enumerate(lines) if i not in ignored), True


def valid_token(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value))


def replace_credentials(text: str, updates: dict[str, str]) -> str:
    allowed = {"AGENTOS_GITHUB_TOKEN", "AGENTOS_CONTROLLER_TOKEN"}
    if not set(updates) <= allowed or not all(valid_token(v) for v in updates.values()):
        raise RepairFailure("credential_update_invalid")
    env = parse_env(text)
    if not set(updates) <= env.keys():
        raise RepairFailure("credential_key_missing")
    lines = []
    for line in text.splitlines(keepends=True):
        key = line.partition("=")[0]
        if key in updates:
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            line = key + "=" + updates[key] + ending
        lines.append(line)
    return "".join(lines)


def http_status(url: str, token: str) -> int:
    if not valid_token(token):
        return 401
    request = Request(url, headers={"Authorization": "Bearer " + token,
                                    "Accept": "application/json", "User-Agent": "AgentOS-Control-Inbox-Repair"})
    try:
        with urlopen(request, timeout=10) as response:
            # Status only: no Node map, DM content, or GitHub comment body is read.
            return response.status
    except HTTPError as exc:
        return exc.code
    except (URLError, TimeoutError, OSError):
        return 0


def command(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GIT_TRACE", "GIT_TRACE_CURL", "GIT_CURL_VERBOSE"):
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(args, input=input_text, capture_output=True, text=True,
                          timeout=20, check=False, env=env)


def github_candidate() -> str:
    try:
        candidate = command(["gh", "auth", "token"]).stdout.strip()
        if http_status(GITHUB_READ, candidate) == 200:
            return candidate
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        output = command(["git", "credential", "fill"], input_text="protocol=https\nhost=github.com\n\n").stdout
        candidate = next((line.partition("=")[2] for line in output.splitlines() if line.startswith("password=")), "")
        if http_status(GITHUB_READ, candidate) == 200:
            return candidate
    except (OSError, subprocess.TimeoutExpired):
        pass
    raise RepairFailure("no_valid_host_github_credential")


def read_private(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
        raise RepairFailure("private_configuration_unavailable")
    return path.read_bytes().decode("utf-8")


def atomic_write(path: Path, text: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".control-inbox-repair-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restart_bridge() -> None:
    try:
        if command(["systemctl", "--user", "restart", UNIT]).returncode:
            raise RepairFailure("bridge_restart_failed")
        if command(["systemctl", "--user", "is-active", "--quiet", UNIT]).returncode:
            raise RepairFailure("bridge_not_active")
    except (OSError, subprocess.TimeoutExpired):
        raise RepairFailure("bridge_restart_unavailable") from None


def repair() -> dict[str, object]:
    if pwd.getpwuid(os.getuid()).pw_name != "ubuntu":
        raise RepairFailure("wrong_service_identity")
    binding = command(["systemctl", "--user", "show", UNIT, "-p", "EnvironmentFiles", "--value"])
    if binding.returncode or binding.stdout.strip() != str(ENV_PATH) + " (ignore_errors=no)":
        raise RepairFailure("service_configuration_binding_mismatch")
    original = read_private(ENV_PATH)
    normalized, shape_changed = normalize_env_shape(original)
    env = parse_env(normalized)
    for key, expected in {"AGENTOS_CONTROL_REPOSITORY": "alston-personal/agentmanager",
                          "AGENTOS_CONTROL_ISSUE": "50", "AGENTOS_CONTROL_ALLOWED_LOGIN": "alstonhuang",
                          "AGENTOS_ONE_URL": "http://127.0.0.1:8780"}.items():
        if env.get(key) != expected:
            raise RepairFailure("configuration_scope_mismatch")
    if not env.get("AGENTOS_CONTROL_ALLOWED_ACTIONS") or not env.get("AGENTOS_CONTROL_STATE"):
        raise RepairFailure("configuration_incomplete")

    updates: dict[str, str] = {}
    github_before = http_status(GITHUB_READ, env.get("AGENTOS_GITHUB_TOKEN", ""))
    if github_before in (401, 403):
        updates["AGENTOS_GITHUB_TOKEN"] = github_candidate()
    elif github_before != 200:
        raise RepairFailure("github_read_unavailable")
    one_before = http_status(ONE_READ, env.get("AGENTOS_CONTROLLER_TOKEN", ""))
    if one_before in (401, 403):
        candidate = parse_env(read_private(CONTROLLER_PATH)).get("AGENTOS_CONTROLLER_TOKEN", "")
        if http_status(ONE_READ, candidate) != 200:
            raise RepairFailure("controller_auth_unavailable")
        updates["AGENTOS_CONTROLLER_TOKEN"] = candidate
    elif one_before != 200:
        raise RepairFailure("one_controller_unavailable")

    repaired = replace_credentials(normalized, updates)
    # Re-read before writing: another deployment must not be silently overwritten.
    if read_private(ENV_PATH) != original:
        raise RepairFailure("configuration_changed_during_preflight")
    changed = repaired != original
    if changed:
        atomic_write(ENV_PATH, repaired)
    try:
        restart_bridge()
        active_text = read_private(ENV_PATH)
        if active_text != repaired:
            raise RepairFailure("configuration_changed_during_postcheck")
        active = parse_env(active_text)
        if http_status(GITHUB_READ, active["AGENTOS_GITHUB_TOKEN"]) != 200:
            raise RepairFailure("github_postcheck_failed")
        if http_status(ONE_READ, active["AGENTOS_CONTROLLER_TOKEN"]) != 200:
            raise RepairFailure("controller_postcheck_failed")
    except Exception:
        if changed:
            if read_private(ENV_PATH) != repaired:
                raise RepairFailure("rollback_blocked_configuration_changed") from None
            atomic_write(ENV_PATH, original)
            restart_bridge()
        raise
    return {"schema": "agentos.control-inbox-repair/v1", "ok": True,
            "github_before_http": github_before, "controller_before_http": one_before,
            "credentials_changed": bool(updates), "configuration_shape_repaired": shape_changed, "bridge_active": True,
            "configuration_ignored_lines_removed": len(original.splitlines()) - len(normalized.splitlines()),
            "github_read_ok": True, "controller_auth_ok": True,
            "action_allowlist_preserved": True, "durable_state_preserved": True,
            "credential_exposed": False, "end_to_end_verified": False}


def main() -> int:
    try:
        if pwd.getpwuid(os.getuid()).pw_name != "ubuntu":
            raise RepairFailure("wrong_service_identity")
        os.umask(0o077)
        fd = os.open(ENV_PATH.parent / ".control-inbox-repair.lock",
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            if os.fstat(lock.fileno()).st_uid != os.getuid():
                raise RepairFailure("repair_lock_owner_mismatch")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = repair()
        print(json.dumps(result, sort_keys=True))
        return 0
    except RepairFailure as exc:
        print(json.dumps({"schema": "agentos.control-inbox-repair/v1", "ok": False,
                          "error": str(exc), "credential_exposed": False}))
    except Exception:
        print(json.dumps({"schema": "agentos.control-inbox-repair/v1", "ok": False,
                          "error": "repair_failed", "credential_exposed": False}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
