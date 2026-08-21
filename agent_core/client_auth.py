"""Scoped client authentication for the Distributed AgentOS Control Plane.

Human-facing IDE clients can exchange a short-lived GitHub credential for a
revocable AgentOS client token. GitHub credentials are verified in-memory and
are never persisted. Runtime/root credentials remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import secrets
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .distributed_control_plane import DistributedControlPlane


DEFAULT_IDE_PERMISSIONS = ("project.read", "task.read", "task.submit")
GITHUB_API_USER_URL = "https://api.github.com/user"
GITHUB_AUTH_USER_AGENT = "AgentOS-Control-Plane/0.3"
CLIENT_TOKEN_PREFIX = "agc_"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClientPrincipal:
    subject: str
    label: str
    permissions: tuple[str, ...]
    expires_at: str


class ClientTokenStore:
    """Durable hashed token registry stored beside Control Plane task state."""

    def __init__(self, store: DistributedControlPlane) -> None:
        self.store = store
        self._init_db()

    def _init_db(self) -> None:
        with self.store._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS client_tokens (
                    token_hash TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    label TEXT NOT NULL,
                    permissions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS client_tokens_subject
                    ON client_tokens(subject, revoked_at, expires_at);
                """
            )

    def issue(
        self,
        subject: str,
        *,
        label: str,
        permissions: Iterable[str] = DEFAULT_IDE_PERMISSIONS,
        ttl_days: int = 90,
    ) -> dict[str, Any]:
        subject = str(subject or "").strip()
        label = str(label or "").strip()[:128]
        normalized = tuple(sorted({item for item in permissions if isinstance(item, str) and item}))
        if not subject or not label:
            raise ValueError("client token subject and label are required")
        if not normalized:
            raise ValueError("client token permissions are required")
        if ttl_days < 1 or ttl_days > 365:
            raise ValueError("client token ttl_days must be between 1 and 365")

        token = CLIENT_TOKEN_PREFIX + secrets.token_urlsafe(36)
        created = _now()
        expires = created + timedelta(days=ttl_days)
        with self.store._connect() as connection:
            connection.execute(
                """
                INSERT INTO client_tokens(
                    token_hash, subject, label, permissions_json,
                    created_at, expires_at, last_used_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    _token_hash(token),
                    subject,
                    label,
                    json.dumps(normalized),
                    _timestamp(created),
                    _timestamp(expires),
                ),
            )
        return {
            "token": token,
            "subject": subject,
            "label": label,
            "permissions": list(normalized),
            "expiresAt": _timestamp(expires),
        }

    def principal(self, token: str) -> ClientPrincipal | None:
        if not token or not token.startswith(CLIENT_TOKEN_PREFIX):
            return None
        now = _now()
        with self.store._connect() as connection:
            row = connection.execute(
                "SELECT * FROM client_tokens WHERE token_hash=?",
                (_token_hash(token),),
            ).fetchone()
            if row is None or row["revoked_at"]:
                return None
            if _parse_timestamp(row["expires_at"]) <= now:
                return None
            permissions = tuple(json.loads(row["permissions_json"]))
            connection.execute(
                "UPDATE client_tokens SET last_used_at=? WHERE token_hash=?",
                (_timestamp(now), row["token_hash"]),
            )
            return ClientPrincipal(
                subject=row["subject"],
                label=row["label"],
                permissions=permissions,
                expires_at=row["expires_at"],
            )

    def revoke(self, token: str) -> bool:
        with self.store._connect() as connection:
            cursor = connection.execute(
                "UPDATE client_tokens SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (_timestamp(_now()), _token_hash(token)),
            )
            return cursor.rowcount == 1


class GitHubIdentityEnrollment:
    """Verify a GitHub credential and issue a scoped AgentOS IDE token."""

    def __init__(
        self,
        token_store: ClientTokenStore,
        allowed_users: Iterable[str],
        *,
        ttl_days: int = 90,
        timeout: float = 15.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.token_store = token_store
        self.allowed_users = {str(user).strip().lower() for user in allowed_users if str(user).strip()}
        if not self.allowed_users:
            raise ValueError("at least one allowed GitHub user is required")
        self.ttl_days = ttl_days
        self.timeout = timeout
        self.opener = opener

    def enroll(self, github_token: str, *, label: str) -> dict[str, Any]:
        github_token = str(github_token or "").strip()
        if not github_token:
            raise ValueError("github_token is required")
        request = Request(
            GITHUB_API_USER_URL,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": GITHUB_AUTH_USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise PermissionError(f"GitHub identity verification failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub identity verification unavailable: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("GitHub identity response was not valid JSON") from exc

        login = str(payload.get("login") or "").strip()
        if not login or login.lower() not in self.allowed_users:
            raise PermissionError("GitHub identity is not authorized for this AgentOS Core")
        return self.token_store.issue(
            f"github:{login}",
            label=label,
            permissions=DEFAULT_IDE_PERMISSIONS,
            ttl_days=self.ttl_days,
        )
