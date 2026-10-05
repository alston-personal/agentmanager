from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
from services.invoice_intake.template_ocr import extract_template_invoice, valid_tax_id, seller_region_text
from services.invoice_intake import vision_ocr
from capabilities.stamp_recognition.runtime import StampStore, detect_stamp_regions, fingerprint_stamp

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


VENDOR_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9·・()（）&\-]{2,32}(?:股份有限公司|有限公司|企業社|商行|實業社|工作室|餐廳|飯店|旅店|商店|門市|分店|公司|行|店))"
)


def normalize_vendor_name(text: str) -> str | None:
    blocked = (
        "統一發票", "發票", "收執聯", "扣抵聯", "存根聯", "營業稅",
        "銷售額", "合計", "總計", "買受人", "銷售人", "統一編號",
    )
    candidates: list[str] = []
    for line in (text or "").splitlines():
        compact = re.sub(r"\s+", "", line).strip("：:-—")
        if not compact or any(token in compact for token in blocked):
            continue
        for m in VENDOR_SUFFIX_RE.finditer(compact):
            name = m.group(1).strip()
            if 2 <= len(name) <= 36 and name not in candidates:
                candidates.append(name)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (len(x), x.count("公司")), reverse=True)
    return candidates[0]


def money_values(text: str) -> list[int]:
    out: list[int] = []
    for raw in re.findall(r"(?<!\d)\d[\d,\.\s]{1,12}(?!\d)", text):
        cleaned = re.sub(r"[^0-9]", "", raw)
        if 2 <= len(cleaned) <= 9:
            value = int(cleaned)
            if 0 < value < 1_000_000_000:
                out.append(value)
    return out


def extract_line_items_from_text(text: str) -> list[dict[str, Any]]:
    """Best-effort line item candidates from OCR text; never invent values."""
    items: list[dict[str, Any]] = []
    blocked = ("發票", "銷售額", "營業稅", "總計", "合計", "統一編號", "日期", "買受人", "銷售人")
    for line in (text or "").splitlines():
        clean = re.sub(r"\s+", " ", line).strip()
        if not clean or any(token in clean for token in blocked):
            continue
        nums = []
        for raw in re.findall(r"(?<!\d)\d[\d,.]*(?!\d)", clean):
            digits = re.sub(r"[^0-9]", "", raw)
            value = int(digits) if digits else None
            if value is not None:
                nums.append((raw, value))
        if len(nums) < 3:
            continue
        quantity, unit_price, amount = [x[1] for x in nums[-3:]]
        if quantity <= 0 or unit_price < 0 or amount <= 0:
            continue
        tolerance = max(1, round(amount * 0.02))
        if abs(quantity * unit_price - amount) > tolerance:
            continue
        first_numeric = clean.find(nums[-3][0])
        description = clean[:first_numeric].strip(" :-—")
        if not description or len(description) > 80:
            continue
        items.append({
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
            "confidence": 0.72,
        })
    return items


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


def stamp_variants(image: Image.Image) -> list[Image.Image]:
    """Return OCR-friendly variants for red/blue/black stamps on white paper."""
    rgb = image.convert("RGB")
    r, g, b = rgb.split()
    variants = [
        ImageOps.autocontrast(ImageOps.grayscale(rgb)),
        ImageOps.autocontrast(r),
        ImageOps.autocontrast(g),
        ImageOps.autocontrast(b),
    ]
    # Red stamps are usually much darker in G/B than the white paper;
    # blue stamps are often strongest in R/G. Channel variants make those
    # strokes survive even when grayscale contrast is weak.
    return variants


def ocr_stamp_text(image: Image.Image, *, digits_only: bool = False) -> list[str]:
    texts: list[str] = []
    whitelist = "0123456789" if digits_only else None
    lang = "eng" if digits_only else "chi_tra+eng"
    for variant in stamp_variants(image):
        for psm in (6, 11, 12):
            text = ocr_image(variant, psm=psm, whitelist=whitelist, lang=lang)
            if text.strip() and text not in texts:
                texts.append(text)
    return texts


@dataclass
class Extraction:
    fields: dict[str, Any]
    confidence: dict[str, float]
    raw: dict[str, Any]
    review_required: bool


def extract_legacy_invoice(image_bytes: bytes, *, stamp_store: StampStore | None = None) -> Extraction:
    """Template-first production extraction with legacy Tesseract fallback.

    Known Taiwan invoice/receipt layouts use RapidOCR + semantic validation first.
    Tesseract only fills fields that remain unresolved; it never overwrites a
    higher-confidence template result.
    """
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")

    rapid = extract_template_invoice(image_bytes)
    fields = {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_name": None,
        "seller_tax_id": None,
        "amount_before_tax": None,
        "tax_amount": None,
        "total_amount": None,
    }
    confidence = {k: 0.0 for k in fields}
    local_line_items = extract_line_items_from_text(rapid.get("raw_text") or "")
    raw: dict[str, Any] = {
        "engine": "rapidocr-template-v1+tesseract-fallback",
        "template": rapid,
        "fallback_used": [],
        "image_size": list(image.size),
        "line_items": local_line_items,
    }

    if rapid.get("matched"):
        for key, value in (rapid.get("fields") or {}).items():
            if key in fields and value not in (None, ""):
                fields[key] = value
                confidence[key] = float((rapid.get("confidence") or {}).get(key) or 0.0)

    # Match a cropped/normalized stamp before expensive stamp OCR. A text/entity
    # agreement is never sufficient to claim the same physical stamp.
    stamp_started = time.perf_counter()
    stamp_regions = detect_stamp_regions(image_bytes)
    raw["stamp_recognition"] = {
        "status": "NO_STAMP_CANDIDATE" if not stamp_regions else "CANDIDATE",
        "regions": [
            {"box": list(region.box), "confidence": region.confidence, "color_hint": region.color_hint}
            for region in stamp_regions
        ],
    }
    if stamp_store is not None and stamp_regions:
        stamp_fp = fingerprint_stamp(image_bytes, stamp_regions[0])
        stamp_match = stamp_store.match(stamp_fp)
        raw["stamp_recognition"].update({
            "decision": stamp_match.decision,
            "score": stamp_match.score,
            "stamp_id": stamp_match.stamp_id,
            "entity_id": stamp_match.entity_id,
            "algorithm": stamp_fp.algorithm,
            "version": stamp_fp.version,
        })
        if stamp_match.decision == "same_stamp" and stamp_match.stamp_id:
            remembered = stamp_store.resolve_verified_attributes(stamp_match.stamp_id)
            if not fields["vendor_name"] and remembered.get("vendor_name"):
                fields["vendor_name"] = remembered["vendor_name"]
                confidence["vendor_name"] = 0.99
            if not fields["seller_tax_id"] and remembered.get("seller_tax_id"):
                fields["seller_tax_id"] = remembered["seller_tax_id"]
                confidence["seller_tax_id"] = 0.99
            raw["stamp_recognition"]["status"] = "MATCHED_CONFIRMED"
            raw["stamp_recognition"]["remembered_attributes"] = sorted(
                key for key in ("vendor_name", "seller_tax_id") if remembered.get(key)
            )
    raw["stamp_recognition"]["latency_ms"] = round((time.perf_counter() - stamp_started) * 1000, 1)

    # Legacy crops remain as a recovery path only.
    invoice_crop = crop_rel(image, (0.12, 0.02, 0.43, 0.22))
    date_crop = crop_rel(image, (0.43, 0.11, 0.79, 0.30))
    amount_crop = crop_rel(image, (0.46, 0.31, 0.73, 0.86))
    stamp_crop = crop_rel(image, (0.60, 0.38, 0.98, 0.96))

    if not fields["invoice_number"]:
        invoice_texts = [
            ocr_image(invoice_crop, psm=7, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            ocr_image(invoice_crop, psm=6, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            ocr_image(invoice_crop, psm=11, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        ]
        value = next((normalize_invoice_number(x) for x in invoice_texts if normalize_invoice_number(x)), None)
        if value:
            fields["invoice_number"] = value
            confidence["invoice_number"] = 0.95
        raw["invoice_texts"] = invoice_texts
        raw["fallback_used"].append("invoice_number")

    if not fields["invoice_date"]:
        date_texts = [
            ocr_image(date_crop, psm=6, whitelist="0123456789/-"),
            ocr_image(date_crop, psm=11, whitelist="0123456789/-"),
        ]
        value = next((normalize_roc_date(x) for x in date_texts if normalize_roc_date(x)), None)
        if value:
            fields["invoice_date"] = value
            confidence["invoice_date"] = 0.90
        raw["date_texts"] = date_texts
        raw["fallback_used"].append("invoice_date")

    if any(fields[k] is None for k in ("amount_before_tax", "tax_amount", "total_amount")):
        amount_regions = [
            amount_crop,
            crop_rel(image, (0.18, 0.24, 0.95, 0.90)),
            crop_rel(image, (0.04, 0.42, 0.96, 0.97)),
            image,
        ]
        amount_texts = []
        for region in amount_regions:
            amount_texts.extend([
                ocr_image(region, psm=6, whitelist="0123456789,.-"),
                ocr_image(region, psm=11, whitelist="0123456789,.-"),
            ])
        subtotal, tax, total, amount_conf = choose_amounts(amount_texts)
        fallback_amounts = {
            "amount_before_tax": subtotal,
            "tax_amount": tax,
            "total_amount": total,
        }
        for key, value in fallback_amounts.items():
            if fields[key] is None and value is not None:
                fields[key] = value
                confidence[key] = amount_conf
        raw["amount_texts"] = amount_texts
        raw["fallback_used"].append("amounts")

    if not fields["seller_tax_id"]:
        stamp_texts = ocr_stamp_text(stamp_crop, digits_only=True)
        tax_ids: list[str] = []
        for stamp_text in stamp_texts:
            for candidate in re.findall(r"(?<!\d)\d{8}(?!\d)", re.sub(r"\s+", "", stamp_text)):
                if candidate not in tax_ids:
                    tax_ids.append(candidate)
        valid = [x for x in tax_ids if valid_tax_id(x)]
        chosen = valid[0] if len(valid) == 1 else None
        if chosen:
            fields["seller_tax_id"] = chosen
            confidence["seller_tax_id"] = 0.88 if chosen in valid else 0.68
        raw["stamp_texts"] = stamp_texts
        raw["fallback_used"].append("seller_tax_id_stamp")

    if not fields["vendor_name"]:
        vendor_texts = [seller_region_text(rapid.get("raw_text") or "")]
        if rapid.get("document_type") != "three_part_uniform_invoice":
            vendor_texts.append(ocr_image(crop_rel(image, (0.02, 0.00, 0.98, 0.34)), psm=6, lang="chi_tra+eng"))
        vendor_texts.extend(ocr_stamp_text(crop_rel(image, (0.42, 0.42, 0.99, 0.99))))
        vendor = next((normalize_vendor_name(t) for t in vendor_texts if normalize_vendor_name(t)), None)
        if vendor:
            fields["vendor_name"] = vendor
            confidence["vendor_name"] = 0.78
        raw["vendor_texts"] = vendor_texts
        raw["fallback_used"].append("vendor_name_stamp_aware")

    # A mathematically derived 5% split is useful for assistance but is not enough
    # by itself for unattended posting; keep that case in review.
    derived_amounts = bool(
        rapid.get("matched")
        and rapid.get("document_type") == "three_part_uniform_invoice"
        and rapid.get("total_amount") is None
        and rapid.get("visual_amounts") is False
    )
    # Current template extractor exposes visual_amounts explicitly; if false while
    # all three amounts are present, they may include a tax-derived split.
    if rapid.get("matched") and rapid.get("document_type") == "three_part_uniform_invoice":
        derived_amounts = not bool(rapid.get("visual_amounts"))

    stamp_matched = (raw.get("stamp_recognition") or {}).get("status") == "MATCHED_CONFIRMED"
    raw["field_sources"] = {
        "invoice_number": "template_or_printed",
        "invoice_date": "template_or_handwritten",
        "vendor_name": ("stamp_registry" if stamp_matched and fields["vendor_name"] else
                        "stamp_or_printed" if fields["vendor_name"] else None),
        "seller_tax_id": ("stamp_registry" if stamp_matched and fields["seller_tax_id"] else
                          "stamp_or_printed" if fields["seller_tax_id"] else None),
        "amount_before_tax": "printed_or_handwritten_amount",
        "tax_amount": "printed_or_handwritten_amount",
        "total_amount": "printed_or_handwritten_amount",
    }

    review_required = (
        any(fields.get(k) in (None, "") for k in ESSENTIAL_FIELDS)
        or any(confidence.get(k, 0.0) < 0.80 for k in ESSENTIAL_FIELDS)
        or derived_amounts
        or not fields.get("seller_tax_id")
        or not fields.get("vendor_name")
        or confidence.get("vendor_name", 0) < 0.80
    )
    return Extraction(fields=fields, confidence=confidence, raw=raw, review_required=review_required)


def extract_invoice(image_bytes: bytes, *, stamp_store: StampStore | None = None) -> Extraction:
    """Compare whole-image vision with the existing reader on identical bytes.

    off: local OCR; shadow: local fields + comparison; primary: vision fields.
    Vision candidates always require review; no guessed confidence or auto posting.
    """
    config = vision_ocr.configuration()
    legacy_error = None
    try:
        legacy = extract_legacy_invoice(image_bytes, stamp_store=stamp_store)
    except Exception as exc:
        if config['mode'] != 'primary' or config['status'] != 'CONFIGURED':
            raise
        legacy_error = type(exc).__name__
        legacy = Extraction(dict.fromkeys(vision_ocr.CORE_FIELDS), {},
                            {'engine': 'legacy-error', 'error_type': legacy_error}, True)
    legacy.raw['image_sha256'] = hashlib.sha256(image_bytes).hexdigest()
    legacy.raw['vision'] = dict(config)
    if config['status'] != 'CONFIGURED':
        if config['mode'] != 'off':
            legacy.review_required = True
        return legacy
    try:
        result = vision_ocr.read_invoice(image_bytes,
            api_key=os.environ.get('GEMINI_API_KEY', ''), model=config['model'])
        fields, issues = vision_ocr.validated_fields(result['payload'])
    except Exception as exc:
        legacy.raw['vision']['status'] = str(exc) if isinstance(exc, vision_ocr.VisionError) else 'INVALID_RESPONSE'
        legacy.review_required = True
        return legacy
    result.update({'status': 'SUCCEEDED', 'mode': config['mode'], 'validation_issues': issues})
    comparison = {key: {'legacy': legacy.fields.get(key), 'vision': fields.get(key),
                        'equal': legacy.fields.get(key) == fields.get(key)} for key in vision_ocr.CORE_FIELDS}
    legacy.raw['vision'] = result
    legacy.raw['comparison'] = comparison
    if config['mode'] == 'shadow':
        # Disagreement must not silently pass as a successful extraction.
        legacy.review_required |= bool(issues or result['payload']['needs_review'] or
                                       any(not v['equal'] for v in comparison.values()))
        return legacy
    return Extraction(fields, {}, {
        'engine': 'gemini-whole-image-v1', 'image_sha256': result['image_sha256'],
        'vision': result, 'comparison': comparison,
        'legacy': {'fields': legacy.fields, 'confidence': legacy.confidence,
                   'raw': {k: v for k, v in legacy.raw.items() if k not in {'vision', 'comparison'}}},
        'field_sources': {k: 'whole_image_vision' if v is not None else None for k, v in fields.items()},
    }, True)


class InvoiceStore:
    def __init__(self, root: Path, *, data_scope: str = "production"):
        self.root = root
        self.data_scope = data_scope
        self.originals = root / "originals"
        self.db_path = root / "invoice-intake.sqlite3"
        self.processing_lock = threading.Lock()
        stamp_db = Path(os.environ.get("STAMP_REGISTRY_PATH", str(root / "stamp-recognition.sqlite3")))
        self.stamp_store = StampStore(stamp_db)
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
            CREATE TABLE IF NOT EXISTS intake_batches(
              id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              data_scope TEXT NOT NULL,
              status TEXT NOT NULL,
              item_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY,
              sha256 TEXT NOT NULL UNIQUE,
              original_filename TEXT NOT NULL,
              mime_type TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              stored_path TEXT NOT NULL,
              batch_id TEXT REFERENCES intake_batches(id),
              source_type TEXT NOT NULL DEFAULT 'unknown',
              data_scope TEXT NOT NULL DEFAULT 'production',
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
            CREATE TABLE IF NOT EXISTS invoice_line_items(
              id TEXT PRIMARY KEY,
              invoice_id TEXT NOT NULL REFERENCES invoices(id),
              line_no INTEGER NOT NULL,
              description TEXT,
              quantity TEXT,
              unit_price INTEGER,
              amount INTEGER,
              source TEXT NOT NULL,
              confidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(invoice_id,line_no)
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
            CREATE INDEX IF NOT EXISTS idx_invoice_line_items_invoice ON invoice_line_items(invoice_id,line_no);
            """)
            invoice_columns = {row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "deleted_at" not in invoice_columns:
                db.execute("ALTER TABLE invoices ADD COLUMN deleted_at TEXT")
            document_columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            if "batch_id" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN batch_id TEXT REFERENCES intake_batches(id)")
            if "source_type" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN source_type TEXT NOT NULL DEFAULT 'unknown'")
            if "data_scope" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'production'")
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_batch ON documents(batch_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_scope_source ON documents(data_scope, source_type)")

    def ingest(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        *,
        source_type: str = "unknown",
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist immutable original and provisional DB row quickly.

        OCR intentionally runs later so continuous scanning is not blocked
        by Tesseract latency.
        """
        source_type = source_type if source_type in {"camera", "upload", "api", "unknown"} else "unknown"
        batch_id = batch_id or str(uuid.uuid4())
        sha = hashlib.sha256(image_bytes).hexdigest()
        with self.connect() as db:
            found = db.execute("""
              SELECT i.*, d.sha256, d.original_filename, d.id AS matched_document_id,
                     d.batch_id, d.source_type, d.data_scope
              FROM documents d LEFT JOIN invoices i ON i.document_id=d.id
              WHERE d.sha256=?
            """, (sha,)).fetchone()
            if found:
                if "deleted_at" in found.keys() and found["deleted_at"]:
                    restored_at = utcnow()
                    db.execute(
                        """UPDATE invoices SET
                             deleted_at=NULL,
                             status='processing',
                             confidence_json='{}',
                             updated_at=?
                           WHERE id=?""",
                        (restored_at, found["id"]),
                    )
                    db.execute(
                        """INSERT OR IGNORE INTO intake_batches(
                             id,source_type,data_scope,status,item_count,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?)""",
                        (batch_id, source_type, self.data_scope, "open", 0, restored_at, restored_at),
                    )
                    db.execute(
                        """UPDATE documents SET batch_id=?, source_type=?, data_scope=?
                           WHERE id=?""",
                        (batch_id, source_type, self.data_scope, found["matched_document_id"]),
                    )
                    db.execute(
                        "UPDATE intake_batches SET item_count=item_count+1, updated_at=? WHERE id=?",
                        (restored_at, batch_id),
                    )
                    restored = db.execute("""
                      SELECT i.*, d.sha256, d.original_filename, d.batch_id, d.source_type, d.data_scope
                      FROM invoices i JOIN documents d ON d.id=i.document_id
                      WHERE i.id=?
                    """, (found["id"],)).fetchone()
                    payload = self._row_payload(restored, duplicate=False)
                    payload["restored"] = True
                    return payload
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
                """INSERT OR IGNORE INTO intake_batches(
                     id,source_type,data_scope,status,item_count,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (batch_id, source_type, self.data_scope, "open", 0, created, created),
            )
            db.execute(
                """INSERT INTO documents(
                     id,sha256,original_filename,mime_type,size_bytes,stored_path,
                     batch_id,source_type,data_scope,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id, sha, filename, mime_type, len(image_bytes), str(target),
                    batch_id, source_type, self.data_scope, created,
                ),
            )
            db.execute(
                "UPDATE intake_batches SET item_count=item_count+1, updated_at=? WHERE id=?",
                (created, batch_id),
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
            "batch_id": batch_id,
            "source_type": source_type,
            "data_scope": self.data_scope,
        }

    def process(self, invoice_id: str) -> dict[str, Any]:
        """Run OCR for one archived invoice and update its DB row."""
        with self.processing_lock:
            with self.connect() as db:
                row = db.execute("""
                  SELECT i.*, d.stored_path, d.sha256, d.original_filename
                  FROM invoices i JOIN documents d ON d.id=i.document_id
                  WHERE i.id=? AND i.deleted_at IS NULL
                """, (invoice_id,)).fetchone()
                if not row:
                    raise KeyError(invoice_id)
                if row["status"] != "processing":
                    return self._row_payload(row)
                image_path = Path(row["stored_path"])

            try:
                image_bytes = image_path.read_bytes()
                extraction = extract_invoice(image_bytes, stamp_store=self.stamp_store)
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
                    db.execute("DELETE FROM invoice_line_items WHERE invoice_id=?", (invoice_id,))
                    vision_payload = ((extraction.raw.get("vision") or {}).get("payload") or {})
                    line_items = vision_payload.get("line_items") or extraction.raw.get("line_items") or []
                    for idx, item in enumerate(line_items, start=1):
                        db.execute(
                            """INSERT INTO invoice_line_items(
                                 id,invoice_id,line_no,description,quantity,unit_price,amount,
                                 source,confidence_json,created_at,updated_at
                               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                str(uuid.uuid4()), invoice_id, idx,
                                item.get("description"),
                                None if item.get("quantity") is None else str(item.get("quantity")),
                                item.get("unit_price"),
                                item.get("amount"),
                                "whole_image_vision" if vision_payload else "ocr",
                                "{}",
                                updated, updated,
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
                    payload = self._row_payload(done)
                    payload["engine"] = extraction.raw["engine"]
                    return payload
            except Exception:
                with self.connect() as db:
                    db.execute(
                        "UPDATE invoices SET status='error', updated_at=? WHERE id=?",
                        (utcnow(), invoice_id),
                    )
                raise

    def reprocess(self, invoice_id: str) -> dict[str, Any]:
        """Re-run OCR for an existing immutable original without creating a new record."""
        with self.connect() as db:
            row = db.execute("SELECT id FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            db.execute(
                "UPDATE invoices SET status='processing', updated_at=? WHERE id=?",
                (utcnow(), invoice_id),
            )
        return self.process(invoice_id)

    def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("""
              SELECT i.*, d.sha256, d.original_filename, d.batch_id, d.source_type, d.data_scope,
                     (SELECT e.engine FROM extractions e WHERE e.document_id=i.document_id
                      ORDER BY e.rowid DESC LIMIT 1) AS extraction_engine
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.id=? AND i.deleted_at IS NULL
            """, (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            payload = self._row_payload(row)
            extraction = db.execute(
                "SELECT payload_json FROM extractions WHERE document_id=? ORDER BY rowid DESC LIMIT 1",
                (row['document_id'],),
            ).fetchone()
            payload['recognition'] = json.loads(extraction['payload_json']) if extraction else None
            items = db.execute(
                """SELECT line_no,description,quantity,unit_price,amount,source,confidence_json
                   FROM invoice_line_items WHERE invoice_id=? ORDER BY line_no""",
                (invoice_id,),
            ).fetchall()
            payload['line_items'] = [dict(item) for item in items]
            return payload

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
            "engine": row["extraction_engine"] if "extraction_engine" in row.keys() and row["extraction_engine"] else None,
            "sha256": row["sha256"] if "sha256" in row.keys() else None,
            "original_filename": row["original_filename"] if "original_filename" in row.keys() else None,
            "batch_id": row["batch_id"] if "batch_id" in row.keys() else None,
            "source_type": row["source_type"] if "source_type" in row.keys() else None,
            "data_scope": row["data_scope"] if "data_scope" in row.keys() else None,
        }

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(100, limit))
        with self.connect() as db:
            rows = db.execute("""
              SELECT i.*, d.sha256, d.original_filename, d.batch_id, d.source_type, d.data_scope,
                     (SELECT e.engine FROM extractions e WHERE e.document_id=i.document_id
                      ORDER BY e.rowid DESC LIMIT 1) AS extraction_engine
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.deleted_at IS NULL
              ORDER BY i.created_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_payload(row) for row in rows]

    def hard_delete(self, invoice_id: str, actor: str) -> dict[str, Any]:
        """Permanently delete one invoice, its derived data, document row and original file."""
        with self.connect() as db:
            row = db.execute(
                """SELECT i.id AS invoice_id, i.document_id, d.stored_path, d.batch_id
                   FROM invoices i JOIN documents d ON d.id=i.document_id
                   WHERE i.id=?""",
                (invoice_id,),
            ).fetchone()
            if not row:
                raise KeyError(invoice_id)
            stored_path = Path(row["stored_path"])
            document_id = row["document_id"]
            batch_id = row["batch_id"]

            db.execute("DELETE FROM reviews WHERE invoice_id=?", (invoice_id,))
            db.execute("DELETE FROM invoice_line_items WHERE invoice_id=?", (invoice_id,))
            db.execute("DELETE FROM extractions WHERE document_id=?", (document_id,))
            db.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
            if batch_id:
                db.execute(
                    """UPDATE intake_batches
                       SET item_count=CASE WHEN item_count>0 THEN item_count-1 ELSE 0 END,
                           updated_at=?
                       WHERE id=?""",
                    (utcnow(), batch_id),
                )

        try:
            stored_path.unlink(missing_ok=True)
        except OSError:
            # DB deletion is authoritative; orphan cleanup can be handled separately.
            pass
        return {"ok": True, "invoice_id": invoice_id, "permanent": True}

    def hard_delete_many(self, invoice_ids: list[str], actor: str) -> dict[str, Any]:
        deleted = []
        for invoice_id in invoice_ids:
            try:
                self.hard_delete(invoice_id, actor)
                deleted.append(invoice_id)
            except KeyError:
                continue
        return {"ok": True, "deleted": deleted, "count": len(deleted), "permanent": True}

    def soft_delete(self, invoice_id: str, actor: str) -> dict[str, Any]:
        now = utcnow()
        with self.connect() as db:
            row = db.execute(
                "SELECT id,deleted_at FROM invoices WHERE id=?",
                (invoice_id,),
            ).fetchone()
            if not row:
                raise KeyError(invoice_id)
            if row["deleted_at"] is None:
                db.execute(
                    "UPDATE invoices SET deleted_at=?, updated_at=? WHERE id=?",
                    (now, now, invoice_id),
                )
                db.execute(
                    "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), invoice_id, actor,
                        json.dumps({"deleted_at": None}, ensure_ascii=False),
                        json.dumps({"deleted_at": now}, ensure_ascii=False),
                        now,
                    ),
                )
        return {"ok": True, "invoice_id": invoice_id, "deleted_at": now}

    def soft_delete_many(self, invoice_ids: list[str], actor: str) -> dict[str, Any]:
        deleted = []
        for invoice_id in invoice_ids:
            try:
                self.soft_delete(invoice_id, actor)
                deleted.append(invoice_id)
            except KeyError:
                continue
        return {"ok": True, "deleted": deleted, "count": len(deleted)}

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
            doc = db.execute("SELECT sha256,original_filename,stored_path FROM documents WHERE id=?", (after["document_id"],)).fetchone()
            merged = dict(after)
            merged["sha256"] = doc["sha256"]
            merged["original_filename"] = doc["original_filename"]

        # Human review confirms business attributes. For an unknown visual stamp,
        # enroll the cropped fingerprint as a new physical stamp. A near/uncertain
        # visual match is deliberately not auto-enrolled as either old or new.
        try:
            image_bytes = Path(doc["stored_path"]).read_bytes()
            regions = detect_stamp_regions(image_bytes)
            if regions and current.get("vendor_name") and current.get("seller_tax_id"):
                fp = fingerprint_stamp(image_bytes, regions[0])
                match = self.stamp_store.match(fp)
                if match.decision == "unknown_stamp":
                    self.stamp_store.learn_confirmed(
                        fp,
                        entity_id=str(current.get("seller_tax_id")),
                        canonical_label=str(current.get("vendor_name")),
                        verified_attributes={
                            "vendor_name": current.get("vendor_name"),
                            "seller_tax_id": current.get("seller_tax_id"),
                        },
                    )
                elif match.decision == "same_stamp" and match.stamp_id:
                    self.stamp_store.learn_confirmed(
                        fp,
                        stamp_id=match.stamp_id,
                        entity_id=match.entity_id,
                        canonical_label=str(current.get("vendor_name")),
                        verified_attributes={
                            "vendor_name": current.get("vendor_name"),
                            "seller_tax_id": current.get("seller_tax_id"),
                        },
                    )
        except (OSError, ValueError, sqlite3.Error):
            # Review must remain authoritative even if optional stamp learning fails.
            pass
        return self._row_payload(sqlite3.Row if False else _DictRow(merged))


class _DictRow(dict):
    def keys(self):
        return super().keys()
