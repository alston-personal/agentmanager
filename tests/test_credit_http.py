import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from http.server import ThreadingHTTPServer

from agent_core.credit_http import handler_for
from agent_core.credit_ledger import CreditLedger
from agent_core.credit_service import CreditBilling


def _pricing(tmp_path: Path) -> Path:
    path = tmp_path / "pricing.json"
    path.write_text(
        '{"schema":"milkcat.credit-pricing/v1","currency":"credit","actions":'
        '{"fengshui.view":0,"fengshui.analysis.generate":2}}',
        encoding="utf-8",
    )
    return path


def _server(tmp_path: Path, token: str | None = "secret"):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    billing = CreditBilling(
        ledger=ledger,
        pricing_path=_pricing(tmp_path),
        mode="shadow",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(billing, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, ledger


def _json(url: str, *, method="GET", token="secret", body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_health_does_not_require_token(tmp_path: Path):
    server, _ = _server(tmp_path)
    try:
        host, port = server.server_address
        status, payload = _json(f"http://{host}:{port}/healthz", token=None)
        assert status == 200
        assert payload["mode"] == "shadow"
    finally:
        server.shutdown()
        server.server_close()


def test_usage_requires_token_and_shadow_does_not_charge(tmp_path: Path):
    server, ledger = _server(tmp_path)
    try:
        host, port = server.server_address
        url = f"http://{host}:{port}/usage"
        try:
            _json(
                url,
                method="POST",
                token=None,
                body={
                    "account_id": "anon:abc",
                    "action_id": "fengshui.analysis.generate",
                    "operation_id": "op-1",
                    "success": True,
                },
            )
            raise AssertionError("expected unauthorized")
        except HTTPError as exc:
            assert exc.code == 401

        status, payload = _json(
            url,
            method="POST",
            body={
                "account_id": "anon:abc",
                "action_id": "fengshui.analysis.generate",
                "operation_id": "op-1",
                "success": True,
                "metadata": {"surface": "fengshui"},
            },
        )
        assert status == 200
        assert payload["receipt"]["quotedCost"] == 2
        assert payload["receipt"]["chargedCost"] == 0
        assert ledger.summary("anon:abc")["balance"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_quote_and_usage_summary(tmp_path: Path):
    server, _ = _server(tmp_path)
    try:
        host, port = server.server_address
        status, payload = _json(
            f"http://{host}:{port}/quote?action_id=fengshui.analysis.generate"
        )
        assert status == 200
        assert payload["quote"]["cost"] == 2

        _json(
            f"http://{host}:{port}/usage",
            method="POST",
            body={
                "account_id": "anon:abc",
                "action_id": "fengshui.analysis.generate",
                "operation_id": "op-2",
                "success": False,
            },
        )
        status, payload = _json(
            f"http://{host}:{port}/account/anon%3Aabc/usage-summary"
        )
        assert status == 200
        assert payload["usage"]["actions"]["fengshui.analysis.generate"]["quotedCost"] == 2
        assert payload["wallet"]["available"] == 0
    finally:
        server.shutdown()
        server.server_close()
