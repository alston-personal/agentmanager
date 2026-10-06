from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def roc_date_to_iso(value: str) -> str:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"unsupported ROC date: {value!r}")
    year, month, day = (int(x) for x in parts)
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def _number(value: str) -> float | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "--", "---", "X"}:
        return None
    return float(text)


def _integer(value: str) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


@dataclass(frozen=True)
class ArchiveReceipt:
    source: str
    instrument: str
    request_key: str
    raw_path: str
    sha256: str
    retrieved_at: str
    rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "agentos.market-data-archive-receipt/v1",
            "source": self.source,
            "instrument": self.instrument,
            "request_key": self.request_key,
            "raw_path": self.raw_path,
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "rows": self.rows,
        }


class ImmutableRawArchive:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def store(
        self,
        *,
        source: str,
        instrument: str,
        request_key: str,
        payload: dict[str, Any],
        retrieved_at: str | None = None,
    ) -> ArchiveReceipt:
        retrieved_at = retrieved_at or _utcnow()
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        directory = self.root / "raw" / source / instrument
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{request_key}.json"

        if path.exists():
            existing = path.read_text(encoding="utf-8")
            existing_digest = hashlib.sha256(existing.encode("utf-8")).hexdigest()
            if existing_digest != digest:
                raise ValueError(
                    f"immutable archive conflict for {path}: "
                    f"existing={existing_digest} incoming={digest}"
                )
        else:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(path)

        rows = len(payload.get("data") or []) if isinstance(payload, dict) else 0
        receipt = ArchiveReceipt(
            source=source,
            instrument=instrument,
            request_key=request_key,
            raw_path=str(path),
            sha256=digest,
            retrieved_at=retrieved_at,
            rows=rows,
        )
        receipt_path = path.with_suffix(".receipt.json")
        if not receipt_path.exists():
            receipt_path.write_text(
                json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return receipt


class TwseMonthlyStockLoader:
    source = "twse-stock-day"

    def build_url(self, stock_no: str, year: int, month: int) -> str:
        params = {
            "date": f"{year:04d}{month:02d}01",
            "stockNo": stock_no,
            "response": "json",
        }
        return f"{TWSE_STOCK_DAY_URL}?{urlencode(params)}"

    def fetch_month(self, stock_no: str, year: int, month: int, *, timeout: int = 30) -> dict[str, Any]:
        url = self.build_url(stock_no, year, month)
        request = Request(url, headers={"User-Agent": "AgentOS-Market-Learning/0.1"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("stat") != "OK":
            raise ValueError(f"TWSE returned non-OK status: {payload.get('stat')!r}")
        return payload

    def normalize(self, stock_no: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("data") or []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if len(row) < 9:
                raise ValueError(f"unexpected STOCK_DAY row: {row!r}")
            normalized.append(
                {
                    "schema": "agentos.market-bar/v1",
                    "source": self.source,
                    "market": "TWSE",
                    "instrument": stock_no,
                    "date": roc_date_to_iso(row[0]),
                    "trade_volume": _integer(row[1]),
                    "trade_value": _integer(row[2]),
                    "open": _number(row[3]),
                    "high": _number(row[4]),
                    "low": _number(row[5]),
                    "close": _number(row[6]),
                    "change": _number(row[7].replace("+", "")),
                    "transactions": _integer(row[8]),
                }
            )
        return normalized

    def archive_month(
        self,
        archive: ImmutableRawArchive,
        stock_no: str,
        year: int,
        month: int,
        payload: dict[str, Any],
    ) -> tuple[ArchiveReceipt, list[dict[str, Any]]]:
        request_key = f"{year:04d}-{month:02d}"
        receipt = archive.store(
            source=self.source,
            instrument=stock_no,
            request_key=request_key,
            payload=payload,
        )
        return receipt, self.normalize(stock_no, payload)


class TwseInstitutionalFlowLoader:
    """Daily TWSE three-major-institution flow adapter.

    The source report is market-wide. One raw response is archived per date, then
    instrument rows are projected without mutating the raw payload.
    """

    source = "twse-t86"

    FIELD_ALIASES = {
        "instrument": ("證券代號",),
        "foreign_net": ("外陸資買賣超股數(不含外資自營商)", "外陸資買賣超股數"),
        "investment_trust_net": ("投信買賣超股數",),
        "dealer_net": ("自營商買賣超股數",),
        "total_institutional_net": ("三大法人買賣超股數",),
    }

    def build_url(self, trading_date: str) -> str:
        digits = trading_date.replace("-", "")
        if len(digits) != 8 or not digits.isdigit():
            raise ValueError("trading_date must be YYYY-MM-DD")
        params = {
            "date": digits,
            "response": "json",
            "selectType": "ALLBUT0999",
        }
        return f"{TWSE_T86_URL}?{urlencode(params)}"

    def fetch_day(self, trading_date: str, *, timeout: int = 30) -> dict[str, Any]:
        url = self.build_url(trading_date)
        request = Request(url, headers={"User-Agent": "AgentOS-Market-Learning/0.1"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("stat") != "OK":
            raise ValueError(f"TWSE T86 returned non-OK status: {payload.get('stat')!r}")
        return payload

    @classmethod
    def _field_index(cls, fields: list[str], key: str) -> int:
        for alias in cls.FIELD_ALIASES[key]:
            if alias in fields:
                return fields.index(alias)
        raise ValueError(f"missing T86 field for {key}: aliases={cls.FIELD_ALIASES[key]!r}")

    def normalize(self, stock_no: str, trading_date: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        fields = [str(x).strip() for x in (payload.get("fields") or [])]
        rows = payload.get("data") or []
        if not fields:
            raise ValueError("T86 payload has no fields")

        idx = {key: self._field_index(fields, key) for key in self.FIELD_ALIASES}
        for row in rows:
            if str(row[idx["instrument"]]).strip() != stock_no:
                continue
            return {
                "schema": "agentos.market-institutional-flow/v1",
                "source": self.source,
                "market": "TWSE",
                "instrument": stock_no,
                "date": trading_date,
                "available_at": f"{trading_date}T20:00:00+08:00",
                "foreign_net": _integer(row[idx["foreign_net"]]),
                "investment_trust_net": _integer(row[idx["investment_trust_net"]]),
                "dealer_net": _integer(row[idx["dealer_net"]]),
                "total_institutional_net": _integer(row[idx["total_institutional_net"]]),
            }
        return None

    def archive_day(
        self,
        archive: ImmutableRawArchive,
        stock_no: str,
        trading_date: str,
        payload: dict[str, Any],
    ) -> tuple[ArchiveReceipt, dict[str, Any] | None]:
        receipt = archive.store(
            source=self.source,
            instrument="ALL",
            request_key=trading_date,
            payload=payload,
        )
        return receipt, self.normalize(stock_no, trading_date, payload)


def merge_daily_signals(
    bars: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge same-day derived signals into bar rows for EOD replay.

    Signal rows are keyed by instrument/date. Unknown dates are ignored and raw
    signal provenance remains available through their own archive.
    """
    by_key = {
        (str(signal.get("instrument")), str(signal.get("date"))): signal
        for signal in signals
    }
    out: list[dict[str, Any]] = []
    for bar in bars:
        row = dict(bar)
        signal = by_key.get((str(bar.get("instrument")), str(bar.get("date"))))
        if signal:
            for key in (
                "foreign_net",
                "investment_trust_net",
                "dealer_net",
                "total_institutional_net",
            ):
                if key in signal:
                    row[key] = signal[key]
        out.append(row)
    return out
