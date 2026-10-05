"""Low-cost stamp ROI detection, normalization and visual fingerprint matching.

This module deliberately does not perform OCR. OCR/vision are expensive fallbacks for
unknown or uncertain stamps. A same-entity text match is never sufficient to claim the
same physical stamp.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .model import StampFingerprint, StampMatch, validate_match


@dataclass(frozen=True)
class StampRegion:
    box: tuple[int, int, int, int]
    confidence: float
    color_hint: str


def _ink_mask(image: Image.Image) -> tuple[Image.Image, str]:
    rgb = image.convert("RGB")
    px = rgb.load()
    mask = Image.new("1", rgb.size, 0)
    out = mask.load()
    red = blue = 0
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = px[x, y]
            is_red = r >= 85 and r >= g * 1.28 and r >= b * 1.18
            is_blue = b >= 70 and b >= r * 1.18 and b >= g * 1.05
            if is_red or is_blue:
                out[x, y] = 1
                red += int(is_red)
                blue += int(is_blue)
    return mask, ("red" if red >= blue else "blue")


def _components(mask: Image.Image) -> list[tuple[int, int, int, int, int]]:
    # Work on a bounded thumbnail so detection remains cheap for phone photos.
    src = mask.copy()
    src.thumbnail((512, 512))
    w, h = src.size
    pix = src.load()
    seen: set[tuple[int, int]] = set()
    comps: list[tuple[int, int, int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if not pix[x, y] or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            minx = maxx = x
            miny = maxy = y
            count = 0
            while stack:
                cx, cy = stack.pop()
                count += 1
                minx, maxx = min(minx, cx), max(maxx, cx)
                miny, maxy = min(miny, cy), max(maxy, cy)
                for nx in range(max(0, cx - 1), min(w, cx + 2)):
                    for ny in range(max(0, cy - 1), min(h, cy + 2)):
                        if pix[nx, ny] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            if count >= 8:
                comps.append((minx, miny, maxx + 1, maxy + 1, count))
    return comps


def detect_stamp_regions(image_bytes: bytes, *, max_regions: int = 3) -> list[StampRegion]:
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    thumb = image.copy()
    thumb.thumbnail((512, 512))
    mask, color = _ink_mask(thumb)
    comps = _components(mask)
    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    tw, th = thumb.size
    sx, sy = image.width / tw, image.height / th
    for l, t, r, b, count in comps:
        bw, bh = r - l, b - t
        area = bw * bh
        if bw < 12 or bh < 8 or area < 180:
            continue
        coverage = count / max(1, area)
        if coverage < 0.025:
            continue
        aspect = bw / max(1, bh)
        if not 0.30 <= aspect <= 4.5:
            continue
        # Prefer dense, stamp-sized colored components but do not overstate confidence.
        score = min(0.94, 0.45 + min(0.30, coverage * 1.4) + min(0.19, area / (tw * th) * 12))
        margin_x = max(4, int(bw * 0.15))
        margin_y = max(4, int(bh * 0.15))
        box = (
            max(0, int((l - margin_x) * sx)),
            max(0, int((t - margin_y) * sy)),
            min(image.width, int((r + margin_x) * sx)),
            min(image.height, int((b + margin_y) * sy)),
        )
        candidates.append((score, box))
    candidates.sort(reverse=True, key=lambda x: x[0])
    return [StampRegion(box=box, confidence=score, color_hint=color)
            for score, box in candidates[:max_regions]]


def crop_normalized_stamp(image_bytes: bytes, region: StampRegion, *, size: int = 128) -> Image.Image:
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    crop = image.crop(region.box)
    gray = ImageOps.autocontrast(ImageOps.grayscale(crop))
    # Crop residual white border, then center in a square canvas.
    inv = ImageOps.invert(gray)
    bbox = inv.point(lambda p: 255 if p > 30 else 0).getbbox()
    if bbox:
        gray = gray.crop(bbox)
    gray.thumbnail((size, size))
    canvas = Image.new("L", (size, size), 255)
    canvas.paste(gray, ((size - gray.width) // 2, (size - gray.height) // 2))
    return canvas


def _dhash(image: Image.Image, *, width: int = 16, height: int = 16) -> str:
    small = image.resize((width + 1, height))
    pixels = list(small.getdata())
    bits = []
    for y in range(height):
        row = y * (width + 1)
        for x in range(width):
            bits.append(1 if pixels[row + x] > pixels[row + x + 1] else 0)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:0{len(bits)//4}x}"


def fingerprint_stamp(image_bytes: bytes, region: StampRegion) -> StampFingerprint:
    normalized = crop_normalized_stamp(image_bytes, region)
    value = _dhash(normalized)
    # Keep only non-sensitive shape metadata; source images stay with the consumer/audit store.
    dark = sum(1 for p in normalized.getdata() if p < 180)
    features = {
        "dark_ratio": round(dark / (normalized.width * normalized.height), 4),
        "region_confidence": round(region.confidence, 4),
        "color_hint": region.color_hint,
    }
    return StampFingerprint("dhash", "1", value, features)


def fingerprint_similarity(a: StampFingerprint, b: StampFingerprint) -> float:
    if a.algorithm != b.algorithm or a.version != b.version or len(a.value) != len(b.value):
        return 0.0
    try:
        av, bv = int(a.value, 16), int(b.value, 16)
    except ValueError:
        return 0.0
    bits = len(a.value) * 4
    return 1.0 - ((av ^ bv).bit_count() / bits)


class StampStore:
    """Small reusable registry; consumers may place this DB in a shared governed data root."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS stamp_entities(
              stamp_id TEXT PRIMARY KEY,
              entity_id TEXT,
              canonical_label TEXT,
              verified_attributes_json TEXT NOT NULL,
              status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stamp_samples(
              id TEXT PRIMARY KEY,
              stamp_id TEXT NOT NULL,
              algorithm TEXT NOT NULL,
              version TEXT NOT NULL,
              fingerprint TEXT NOT NULL,
              features_json TEXT NOT NULL,
              confirmed INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY(stamp_id) REFERENCES stamp_entities(stamp_id)
            );
            CREATE INDEX IF NOT EXISTS idx_stamp_fp
              ON stamp_samples(algorithm,version,fingerprint);
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def learn_confirmed(self, fingerprint: StampFingerprint, *,
                        entity_id: str | None, canonical_label: str | None,
                        verified_attributes: dict[str, Any], stamp_id: str | None = None) -> str:
        stamp_id = stamp_id or f"stamp-{uuid.uuid4()}"
        with self.connect() as db:
            db.execute("""INSERT OR IGNORE INTO stamp_entities
                (stamp_id,entity_id,canonical_label,verified_attributes_json,status)
                VALUES(?,?,?,?,?)""",
                (stamp_id, entity_id, canonical_label,
                 json.dumps(verified_attributes, ensure_ascii=False, sort_keys=True), "confirmed"))
            db.execute("""INSERT INTO stamp_samples
                (id,stamp_id,algorithm,version,fingerprint,features_json,confirmed)
                VALUES(?,?,?,?,?,?,1)""",
                (str(uuid.uuid4()), stamp_id, fingerprint.algorithm, fingerprint.version,
                 fingerprint.value, json.dumps(dict(fingerprint.features), ensure_ascii=False)))
        return stamp_id

    def match(self, fingerprint: StampFingerprint, *,
              same_stamp_threshold: float = 0.965,
              uncertain_threshold: float = 0.88) -> StampMatch:
        best: tuple[float, sqlite3.Row] | None = None
        with self.connect() as db:
            rows = db.execute("""SELECT s.*,e.entity_id,e.status
                FROM stamp_samples s JOIN stamp_entities e ON e.stamp_id=s.stamp_id
                WHERE s.algorithm=? AND s.version=? AND s.confirmed=1 AND e.status='confirmed'""",
                (fingerprint.algorithm, fingerprint.version)).fetchall()
        for row in rows:
            candidate = StampFingerprint(row["algorithm"], row["version"], row["fingerprint"],
                                         json.loads(row["features_json"]))
            score = fingerprint_similarity(fingerprint, candidate)
            if best is None or score > best[0]:
                best = (score, row)
        if best is None:
            match = StampMatch("unknown_stamp", 0.0, reasons=("no confirmed samples",))
        elif best[0] >= same_stamp_threshold:
            match = StampMatch("same_stamp", best[0], stamp_id=best[1]["stamp_id"],
                               entity_id=best[1]["entity_id"], requires_confirmation=False,
                               reasons=("visual fingerprint matched confirmed sample",))
        elif best[0] >= uncertain_threshold:
            match = StampMatch("uncertain", best[0], stamp_id=best[1]["stamp_id"],
                               entity_id=best[1]["entity_id"],
                               reasons=("near visual match below same-stamp threshold",))
        else:
            match = StampMatch("unknown_stamp", best[0], reasons=("no sufficiently similar sample",))
        validate_match(match)
        return match

    def resolve_verified_attributes(self, stamp_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("""SELECT verified_attributes_json,status
                                FROM stamp_entities WHERE stamp_id=?""", (stamp_id,)).fetchone()
        if not row or row["status"] != "confirmed":
            return {}
        return json.loads(row["verified_attributes_json"])


def source_digest(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()
