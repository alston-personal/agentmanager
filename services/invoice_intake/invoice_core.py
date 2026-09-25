from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps

ESSENTIAL_FIELDS = ("invoice_number", "invoice_date", "amount_before_tax", "total_amount")


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_invoice_number(text: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    for match in re.finditer(r"[A-Z0-9]{10}", compact):
        token = match.group(0)
        prefix = token[:2]
        digits = token[2:]
        digits = digits.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "G": "6", "Z": "2"}))
        if re.fullmatch(r"[A-Z]{2}", prefix) and re.fullmatch(r"\d{8}", digits):
            return prefix + digits
    for match in re.finditer(r"([A-Z]{2})\s*([0-9OILSBGZ][0-9OILSBGZ\s-]{7,12})", text.upper()):
        digits = re.sub(r"[^0-9OILSBGZ]", "", match.group(2))
        digits = digits.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "G": "6", "Z": "2"}))
        if len(digits) >= 8 and digits[:8].isdigit():
            return match.group(1) + digits[:8]
    return None


def normalize_roc_date(text: str) -> str | None:
    nums = [int(x) for x in re.findall(r"\d{1,4}", text)]
    candidates: list[tuple[int, int, int]] = []
    for i in range(max(0, len(nums) - 2)):
        y, m, d = nums[i:i+3]
        if 1 <= m <= 12 and 1 <= d <= 31:
            if 90 <= y <= 199:
                candidates.append((y + 1911, m, d))
            elif 2000 <= y <= 2200:
                candidates.append((y, m, d))
    compact = re.sub(r"\D", "", text)
    if not candidates and len(compact) in (6, 7):
        for y_len in (3, 4):
            if len(compact) <= y_len + 2:
                continue
            y = int(compact[:y_len])
            rest = compact[y_len:]
            for m_len in (1, 2):
                if len(rest) <= m_len:
                    continue
                m = int(rest[:m_len])
                d = int(rest[m_len:])
                yy = y + 1911 if 90 <= y <= 199 else y
                if 2000 <= yy <= 2200 and 1 <= m <= 12 and 1 <= d <= 31:
                    candidates.append((yy, m, d))
    for y, m, d in candidates:
        try:
            return datetime(y, m, d).date().isoformat()
        except ValueError:
            continue
    return None


def money_values(text: str) -> list[int]:
    out: list[int] = []
    for raw in re.findall(r"(?<!\d)\d[\d,\.\s]{1,12}(?!\d)", text):
        cleaned = re.sub(r"[^0-9]", "", raw)
        if 2 <= len(cleaned) <= 9:
            value = int(cleaned)
            if 0 < value < 1_000_000_000:
                out.append(value)
    return out


def choose_amounts(texts: list[str]) -> tuple[int | None, int | None, int | None, float]:
    best: tuple[int | None, int | None, int | None, float] = (None, None, None, 0.0)
    for text in texts:
        vals = money_values(text)
        for i, a in enumerate(vals):
            for j in range(i + 1, len(vals)):
                b = vals[j]
                for k in range(j + 1, len(vals)):
                    c = vals[k]
                    if a + b == c and a >= b and c >= 100:
                        return a, b, c, 0.98
        unique = []
        for v in vals:
            if v not in unique:
                unique.append(v)
        if len(unique) >= 2:
            for a in unique:
                for c in unique:
                    if c <= a:
                        continue
                    tax = c - a
                    if tax > 0 and abs(tax - round(a * 0.05)) <= 2:
                        best = (a, tax, c, 0.84)
    return best


def ocr_image(image: Image.Image, *, psm: int, whitelist: str | None = None, lang: str = "eng") -> str:
    prepared = ImageOps.autocontrast(ImageOps.grayscale(image))
    prepared = prepared.resize((prepared.width * 2, prepared.height * 2))
    prepared = ImageEnhance.Contrast(prepared).enhance(1.35)
    cmd = ["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    payload = BytesIO()
    prepared.save(payload, format="PNG")
    proc = subprocess.run(cmd, input=payload.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
    return proc.stdout.decode("utf-8", errors="replace") if proc.returncode == 0 else ""


def crop_rel(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = image.size
    l, t, r, b = box
    return image.crop((int(w*l), int(h*t), int(w*r), int(h*b)))


@dataclass
class Extraction:
    fields: dict[str, Any]
    confidence: dict[str, float]
    raw: dict[str, Any]
    review_required: bool


def extract_invoice(image_bytes: bytes) -> Extraction:
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.height > image.width * 1.08:
        image = image.rotate(90, expand=True)

    invoice_crop = crop_rel(image, (0.12, 0.02, 0.43, 0.22))
    date_crop = crop_rel(image, (0.43, 0.11, 0.79, 0.30))
    amount_crop = crop_rel(image, (0.46, 0.31, 0.73, 0.86))
    stamp_crop = crop_rel(image, (0.66, 0.58, 0.96, 0.96))

    invoice_texts = [
        ocr_image(invoice_crop, psm=7, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        ocr_image(invoice_crop, psm=6, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        ocr_image(invoice_crop, psm=11, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
    ]
    invoice_number = next((normalize_invoice_number(x) for x in invoice_texts if normalize_invoice_number(x)), None)

    date_texts = [
        ocr_image(date_crop, psm=6, whitelist="0123456789/-"),
        ocr_image(date_crop, psm=11, whitelist="0123456789/-"),
    ]
    invoice_date = next((normalize_roc_date(x) for x in date_texts if normalize_roc_date(x)), None)

    amount_texts = [
        ocr_image(amount_crop, psm=6, whitelist="0123456789,.-"),
        ocr_image(amount_crop, psm=11, whitelist="0123456789,.-"),
        ocr_image(amount_crop, psm=12, whitelist="0123456789,.-"),
    ]
    subtotal, tax, total, amount_conf = choose_amounts(amount_texts)

    stamp_text = ocr_image(stamp_crop, psm=11, whitelist="0123456789")
    tax_ids = re.findall(r"(?<!\d)\d{8}(?!\d)", re.sub(r"\s+", "", stamp_text))
    seller_tax_id = tax_ids[0] if tax_ids else None

    confidence = {
        "invoice_number": 0.95 if invoice_number else 0.0,
        "invoice_date": 0.90 if invoice_date else 0.0,
        "amount_before_tax": amount_conf if subtotal is not None else 0.0,
        "tax_amount": amount_conf if tax is not None else 0.0,
        "total_amount": amount_conf if total is not None else 0.0,
        "seller_tax_id": 0.72 if seller_tax_id else 0.0,
        "vendor_name": 0.0,
    }
    fields = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "vendor_name": None,
        "seller_tax_id": seller_tax_id,
        "amount_before_tax": subtotal,
        "tax_amount": tax,
        "total_amount": total,
    }
    review_required = any(fields.get(k) in (None, "") for k in ESSENTIAL_FIELDS) or any(
        confidence.get(k, 0.0) < 0.80 for k in ESSENTIAL_FIELDS
    )
    return Extraction(
        fields=fields,
        confidence=confidence,
        raw={
            "engine": "tesseract-layout-v1",
            "invoice_texts": invoice_texts,
            "date_texts": date_texts,
            "amount_texts": amount_texts,
            "stamp_text": stamp_text,
            "image_size": list(image.size),
        },
        review_required=review_required,
    )


class InvoiceStore:
    def __init__(self, root: Path):
        self.root = root
        self.originals = root / "originals"
        self.db_path = root / "invoice-intake.sqlite3"
        self.processing_lock = threading.Lock()
        self.originals.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY,
              sha256 TEXT NOT NULL UNIQUE,
              original_filename TEXT NOT NULL,
              mime_type TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              stored_path TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS extractions(
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES documents(id),
              engine TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoices(
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
              invoice_number TEXT,
              invoice_date TEXT,
              vendor_name TEXT,
              seller_tax_id TEXT,
              amount_before_tax INTEGER,
              tax_amount INTEGER,
              total_amount INTEGER,
              status TEXT NOT NULL,
              confidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews(
              id TEXT PRIMARY KEY,
              invoice_id TEXT NOT NULL REFERENCES invoices(id),
              actor TEXT NOT NULL,
              before_json TEXT NOT NULL,
              after_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices(created_at DESC);
            """)

    def ingest(self, image_bytes: bytes, filename: str, mime_type: str) -> dict[str, Any]:
        """Persist immutable original and provisional DB row quickly.

        OCR intentionally runs later so continuous scanning is not blocked
        by Tesseract latency.
        """
        sha = hashlib.sha256(image_bytes).hexdigest()
        with self.connect() as db:
            found = db.execute("""
              SELECT i.*, d.sha256, d.original_filename
              FROM documents d LEFT JOIN invoices i ON i.document_id=d.id
              WHERE d.sha256=?
            """, (sha,)).fetchone()
            if found:
                return self._row_payload(found, duplicate=True)

        ext = ".jpg"
        if mime_type == "image/png":
            ext = ".png"
        elif mime_type == "image/webp":
            ext = ".webp"

        now = datetime.now(timezone.utc)
        rel_dir = Path(f"{now.year:04d}") / f"{now.month:02d}"
        target_dir = self.originals / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        document_id = str(uuid.uuid4())
        invoice_id = str(uuid.uuid4())
        created = utcnow()
        target = target_dir / f"{document_id}{ext}"

        with target.open("xb") as fh:
            fh.write(image_bytes)

        with self.connect() as db:
            db.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                (document_id, sha, filename, mime_type, len(image_bytes), str(target), created),
            )
            db.execute("""
              INSERT INTO invoices(
                id,document_id,invoice_number,invoice_date,vendor_name,seller_tax_id,
                amount_before_tax,tax_amount,total_amount,status,confidence_json,created_at,updated_at
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                invoice_id, document_id, None, None, None, None,
                None, None, None, "processing", "{}", created, created
            ))

        return {
            "ok": True,
            "duplicate": False,
            "archived": True,
            "document_id": document_id,
            "invoice_id": invoice_id,
            "status": "processing",
            "fields": {
                "invoice_number": None,
                "invoice_date": None,
                "vendor_name": None,
                "seller_tax_id": None,
                "amount_before_tax": None,
                "tax_amount": None,
                "total_amount": None,
            },
            "confidence": {},
            "engine": "tesseract-layout-v2-async",
            "sha256": sha,
            "original_filename": filename,
        }

    def process(self, invoice_id: str) -> dict[str, Any]:
        """Run OCR for one archived invoice and update its DB row."""
        with self.processing_lock:
            with self.connect() as db:
                row = db.execute("""
                  SELECT i.*, d.stored_path, d.sha256, d.original_filename
                  FROM invoices i JOIN documents d ON d.id=i.document_id
                  WHERE i.id=?
                """, (invoice_id,)).fetchone()
                if not row:
                    raise KeyError(invoice_id)
                if row["status"] != "processing":
                    return self._row_payload(row)
                image_path = Path(row["stored_path"])

            try:
                image_bytes = image_path.read_bytes()
                extraction = extract_invoice(image_bytes)
                extraction_id = str(uuid.uuid4())
                updated = utcnow()
                status = "needs_review" if extraction.review_required else "extracted"
                f = extraction.fields

                with self.connect() as db:
                    db.execute(
                        "INSERT INTO extractions VALUES(?,?,?,?,?)",
                        (
                            extraction_id,
                            row["document_id"],
                            extraction.raw["engine"],
                            json.dumps(extraction.raw, ensure_ascii=False),
                            updated,
                        ),
                    )
                    db.execute("""
                      UPDATE invoices SET
                        invoice_number=?, invoice_date=?, vendor_name=?, seller_tax_id=?,
                        amount_before_tax=?, tax_amount=?, total_amount=?, status=?,
                        confidence_json=?, updated_at=?
                      WHERE id=?
                    """, (
                        f["invoice_number"], f["invoice_date"], f["vendor_name"], f["seller_tax_id"],
                        f["amount_before_tax"], f["tax_amount"], f["total_amount"], status,
                        json.dumps(extraction.confidence, ensure_ascii=False), updated, invoice_id,
                    ))
                    done = db.execute("""
                      SELECT i.*, d.sha256, d.original_filename
                      FROM invoices i JOIN documents d ON d.id=i.document_id
                      WHERE i.id=?
                    """, (invoice_id,)).fetchone()
                    return self._row_payload(done)
            except Exception:
                with self.connect() as db:
                    db.execute(
                        "UPDATE invoices SET status='error', updated_at=? WHERE id=?",
                        (utcnow(), invoice_id),
                    )
                raise

    def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("""
              SELECT i.*, d.sha256, d.original_filename
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.id=?
            """, (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            return self._row_payload(row)

    def get_original(self, invoice_id: str) -> dict[str, Any]:
        """Return validated metadata for the immutable original image."""
        with self.connect() as db:
            row = db.execute("""
              SELECT d.stored_path, d.mime_type, d.original_filename, d.sha256
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.id=?
            """, (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)

        path = Path(row["stored_path"]).resolve()
        originals_root = self.originals.resolve()
        try:
            path.relative_to(originals_root)
        except ValueError as exc:
            raise ValueError("original_path_outside_store") from exc
        if not path.is_file():
            raise FileNotFoundError(invoice_id)

        return {
            "path": path,
            "mime_type": row["mime_type"],
            "original_filename": row["original_filename"],
            "sha256": row["sha256"],
        }

    def _row_payload(self, row: sqlite3.Row, duplicate: bool = False) -> dict[str, Any]:
        return {
            "ok": True,
            "duplicate": duplicate,
            "archived": True,
            "document_id": row["document_id"] if "document_id" in row.keys() else None,
            "invoice_id": row["id"] if "id" in row.keys() else None,
            "status": row["status"] if "status" in row.keys() else "archived",
            "fields": {
                "invoice_number": row["invoice_number"] if "invoice_number" in row.keys() else None,
                "invoice_date": row["invoice_date"] if "invoice_date" in row.keys() else None,
                "vendor_name": row["vendor_name"] if "vendor_name" in row.keys() else None,
                "seller_tax_id": row["seller_tax_id"] if "seller_tax_id" in row.keys() else None,
                "amount_before_tax": row["amount_before_tax"] if "amount_before_tax" in row.keys() else None,
                "tax_amount": row["tax_amount"] if "tax_amount" in row.keys() else None,
                "total_amount": row["total_amount"] if "total_amount" in row.keys() else None,
            },
            "confidence": json.loads(row["confidence_json"]) if "confidence_json" in row.keys() and row["confidence_json"] else {},
            "sha256": row["sha256"] if "sha256" in row.keys() else None,
            "original_filename": row["original_filename"] if "original_filename" in row.keys() else None,
        }

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(100, limit))
        with self.connect() as db:
            rows = db.execute("""
              SELECT i.*, d.sha256, d.original_filename
              FROM invoices i JOIN documents d ON d.id=i.document_id
              ORDER BY i.created_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_payload(row) for row in rows]

    def review(self, invoice_id: str, actor: str, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {"invoice_number", "invoice_date", "vendor_name", "seller_tax_id", "amount_before_tax", "tax_amount", "total_amount"}
        cleaned = {k: fields.get(k) for k in allowed if k in fields}
        with self.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            before = dict(row)
            current = {k: before.get(k) for k in allowed}
            current.update(cleaned)
            if current.get("amount_before_tax") is not None and current.get("tax_amount") is not None and current.get("total_amount") is not None:
                if int(current["amount_before_tax"]) + int(current["tax_amount"]) != int(current["total_amount"]):
                    raise ValueError("amount_validation_failed")
            if current.get("invoice_number") and not re.fullmatch(r"[A-Z]{2}\d{8}", str(current["invoice_number"]).upper()):
                raise ValueError("invoice_number_validation_failed")
            now = utcnow()
            assignments = ",".join(f"{k}=?" for k in cleaned)
            values = list(cleaned.values())
            if assignments:
                db.execute(f"UPDATE invoices SET {assignments}, status='reviewed', updated_at=? WHERE id=?", (*values, now, invoice_id))
            else:
                db.execute("UPDATE invoices SET status='reviewed', updated_at=? WHERE id=?", (now, invoice_id))
            after = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), invoice_id, actor, json.dumps(before, ensure_ascii=False), json.dumps(dict(after), ensure_ascii=False), now),
            )
            doc = db.execute("SELECT sha256,original_filename FROM documents WHERE id=?", (after["document_id"],)).fetchone()
            merged = dict(after)
            merged["sha256"] = doc["sha256"]
            merged["original_filename"] = doc["original_filename"]
            return self._row_payload(sqlite3.Row if False else _DictRow(merged))


class _DictRow(dict):
    def keys(self):
        return super().keys()
