"""Local HTTP service for Milkcat Credits.

The service is intentionally server-to-server. It binds to loopback by default and
can require a bearer token. User identity is not established here: callers must
supply an account/subject that they resolved from a trusted Milkcat World session
(or an explicitly anonymous shadow subject during the pre-login rollout).
"""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config
from .credit_ledger import CreditLedger
from .credit_service import CreditBilling

MAX_BODY = 64 * 1024
DEFAULT_PRICING = Path(__file__).resolve().parent.parent / ".agent" / "governance" / "credit_pricing.json"


class CreditHTTPHandler(BaseHTTPRequestHandler):
    billing: CreditBilling
    bearer_token: str | None = None
    server_version = "MilkcatCredits/0.1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not self.bearer_token:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {self.bearer_token}"

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("request body size is invalid")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "milkcat-credits",
                    "version": "0.1",
                    "mode": self.billing.mode,
                },
            )
            return

        if not self._require_auth():
            return

        if parsed.path == "/quote":
            try:
                action_id = parse_qs(parsed.query).get("action_id", [""])[0]
                self._json(HTTPStatus.OK, {"ok": True, "quote": self.billing.quote(action_id)})
            except (ValueError, KeyError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        prefix = "/account/"
        suffix = "/usage-summary"
        if parsed.path.startswith(prefix) and parsed.path.endswith(suffix):
            account_id = unquote(parsed.path[len(prefix):-len(suffix)]).strip("/")
            try:
                usage = self.billing.usage_summary(account_id)
                wallet = self.billing.ledger.summary(account_id)
                self._json(HTTPStatus.OK, {"ok": True, "wallet": wallet, "usage": usage})
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/usage":
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        if not self._require_auth():
            return
        try:
            body = self._body()
            success = body.get("success")
            if not isinstance(success, bool):
                raise ValueError("success must be a boolean")
            metadata = body.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be an object")
            receipt = self.billing.execute(
                account_id=str(body.get("account_id") or ""),
                action_id=str(body.get("action_id") or ""),
                operation_id=str(body.get("operation_id") or ""),
                success=success,
                metadata=metadata,
            )
            self._json(HTTPStatus.OK, {"ok": True, "receipt": receipt})
        except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        return


def handler_for(billing: CreditBilling, bearer_token: str | None = None):
    class Handler(CreditHTTPHandler):
        pass

    Handler.billing = billing
    Handler.bearer_token = bearer_token
    return Handler


def build_billing(
    *,
    mode: str | None = None,
    db_path: str | Path | None = None,
    pricing_path: str | Path | None = None,
) -> CreditBilling:
    db = Path(db_path or (config.RUNTIME_DIR / "credits.sqlite3"))
    ledger = CreditLedger(db)
    return CreditBilling(
        ledger=ledger,
        pricing_path=Path(pricing_path or DEFAULT_PRICING),
        mode=mode or os.environ.get("MILKCAT_CREDITS_MODE", "shadow"),
        usage_db_path=db,
    )


def serve(
    host: str = "127.0.0.1",
    port: int = 8767,
    *,
    mode: str | None = None,
    db_path: str | Path | None = None,
    pricing_path: str | Path | None = None,
    bearer_token: str | None = None,
) -> None:
    billing = build_billing(mode=mode, db_path=db_path, pricing_path=pricing_path)
    token = bearer_token if bearer_token is not None else os.environ.get("MILKCAT_CREDITS_TOKEN")
    server = ThreadingHTTPServer((host, port), handler_for(billing, token))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--mode", choices=("off", "shadow", "enforce"))
    parser.add_argument("--db")
    parser.add_argument("--pricing")
    args = parser.parse_args(argv)
    serve(
        args.host,
        args.port,
        mode=args.mode,
        db_path=args.db,
        pricing_path=args.pricing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
