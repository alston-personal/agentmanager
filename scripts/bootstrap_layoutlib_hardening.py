#!/usr/bin/env python3
"""Harden a bootstrapped LayoutLib tree with dependency-free P5 PGM support and benchmarks.

This is intentionally a second-stage bootstrap so the stable v0.1 core can remain
small while the real-world validation surface grows independently.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import textwrap

FILES = {
    "src/layoutlib/imageio.py": r'''
from __future__ import annotations
from pathlib import Path


def _next_token(data: bytes, pos: int) -> tuple[bytes, int]:
    n = len(data)
    while pos < n:
        b = data[pos]
        if b == 35:  # # comment
            while pos < n and data[pos] not in (10, 13):
                pos += 1
        elif chr(b).isspace():
            pos += 1
        else:
            break
    if pos >= n:
        raise ValueError("unexpected end of PGM header")
    start = pos
    while pos < n and not chr(data[pos]).isspace() and data[pos] != 35:
        pos += 1
    return data[start:pos], pos


def _read_pgm(data: bytes) -> tuple[int, int, list[list[int]]]:
    magic, pos = _next_token(data, 0)
    if magic not in (b"P2", b"P5"):
        raise ValueError("unsupported PGM magic")
    wt, pos = _next_token(data, pos)
    ht, pos = _next_token(data, pos)
    mt, pos = _next_token(data, pos)
    width, height, maxv = int(wt), int(ht), int(mt)
    if width <= 0 or height <= 0 or not (1 <= maxv <= 65535):
        raise ValueError("invalid PGM dimensions/max value")

    count = width * height
    if magic == b"P2":
        vals: list[int] = []
        for _ in range(count):
            tok, pos = _next_token(data, pos)
            vals.append(int(tok))
    else:
        if pos >= len(data) or not chr(data[pos]).isspace():
            raise ValueError("P5 header must be followed by whitespace")
        # Netpbm requires whitespace between maxval and raster. Treat CRLF as one
        # delimiter so a first pixel whose byte happens to be whitespace is preserved.
        if data[pos] == 13 and pos + 1 < len(data) and data[pos + 1] == 10:
            pos += 2
        else:
            pos += 1
        bytes_per_sample = 1 if maxv < 256 else 2
        needed = count * bytes_per_sample
        raster = data[pos:pos + needed]
        if len(raster) != needed:
            raise ValueError("truncated P5 raster")
        if bytes_per_sample == 1:
            vals = list(raster)
        else:
            vals = [int.from_bytes(raster[i:i+2], "big") for i in range(0, len(raster), 2)]

    if any(v < 0 or v > maxv for v in vals):
        raise ValueError("PGM sample outside max value")
    scaled = [round(v * 255 / maxv) for v in vals]
    return width, height, [scaled[y*width:(y+1)*width] for y in range(height)]


def load_grayscale(path: str | Path) -> tuple[int, int, list[list[int]]]:
    """Return width, height, grayscale pixels (0 black .. 255 white).

    P2 and P5 PGM are dependency-free. PNG/JPEG/BMP require Pillow.
    """
    path = Path(path)
    data = path.read_bytes()
    if data.startswith((b"P2", b"P5")):
        return _read_pgm(data)
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("PNG/JPEG/BMP input requires Pillow; install layoutlib[images]") from exc
    with Image.open(path) as im:
        im = im.convert("L")
        width, height = im.size
        flat = list(im.getdata())
    return width, height, [flat[y*width:(y+1)*width] for y in range(height)]
''',
    "src/layoutlib/benchmark.py": r'''
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from .models import SpatialIR, Wall


@dataclass(frozen=True)
class WallMetrics:
    predicted: int
    expected: int
    matched: int
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict:
        return asdict(self)


def _orientation(w: Wall) -> str:
    dx = abs(w.end.x - w.start.x)
    dy = abs(w.end.y - w.start.y)
    if dx == 0 and dy == 0:
        return "point"
    return "h" if dx >= dy else "v"


def _segment_interval(w: Wall, axis: str) -> tuple[float, float, float]:
    if axis == "h":
        lo, hi = sorted((w.start.x, w.end.x))
        fixed = (w.start.y + w.end.y) / 2
    else:
        lo, hi = sorted((w.start.y, w.end.y))
        fixed = (w.start.x + w.end.x) / 2
    return lo, hi, fixed


def _is_match(pred: Wall, truth: Wall, *, distance_tolerance_m: float,
              min_overlap_ratio: float) -> tuple[bool, float]:
    axis = _orientation(truth)
    if axis not in ("h", "v") or _orientation(pred) != axis:
        return False, math.inf
    pa, pb, pf = _segment_interval(pred, axis)
    ta, tb, tf = _segment_interval(truth, axis)
    distance = abs(pf - tf)
    if distance > distance_tolerance_m:
        return False, distance
    overlap = max(0.0, min(pb, tb) - max(pa, ta))
    truth_len = max(tb - ta, 1e-9)
    pred_len = max(pb - pa, 1e-9)
    overlap_ratio = overlap / min(truth_len, pred_len)
    return overlap_ratio >= min_overlap_ratio, distance


def evaluate_walls(predicted: SpatialIR, expected: SpatialIR, *,
                   distance_tolerance_m: float = 0.08,
                   min_overlap_ratio: float = 0.70) -> WallMetrics:
    """Greedy one-to-one wall matching for labeled orthogonal benchmark plans."""
    candidates: list[tuple[float, int, int]] = []
    for pi, pred in enumerate(predicted.walls):
        for ti, truth in enumerate(expected.walls):
            ok, distance = _is_match(pred, truth,
                                     distance_tolerance_m=distance_tolerance_m,
                                     min_overlap_ratio=min_overlap_ratio)
            if ok:
                candidates.append((distance, pi, ti))
    used_p: set[int] = set(); used_t: set[int] = set(); matched = 0
    for _, pi, ti in sorted(candidates):
        if pi in used_p or ti in used_t:
            continue
        used_p.add(pi); used_t.add(ti); matched += 1
    precision = matched / len(predicted.walls) if predicted.walls else (1.0 if not expected.walls else 0.0)
    recall = matched / len(expected.walls) if expected.walls else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return WallMetrics(len(predicted.walls), len(expected.walls), matched, precision, recall, f1)


def save_metrics(metrics: WallMetrics, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(metrics.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
''',
    "tests/test_imageio_formats.py": r'''
from __future__ import annotations
import tempfile
from pathlib import Path
import unittest
from layoutlib.imageio import load_grayscale


class ImageIOFormatTests(unittest.TestCase):
    def test_p2_dependency_free(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny.pgm"
            p.write_bytes(b"P2\n# demo\n3 2\n15\n0 15 7\n15 0 15\n")
            w, h, px = load_grayscale(p)
            self.assertEqual((w, h), (3, 2))
            self.assertEqual(px[0][0], 0)
            self.assertEqual(px[0][1], 255)

    def test_p5_dependency_free_preserves_whitespace_pixel(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny.pgm"
            # First raster byte is 10 (LF): loader must not strip it as header whitespace.
            p.write_bytes(b"P5\n3 2\n255\n" + bytes([10, 255, 0, 128, 64, 32]))
            w, h, px = load_grayscale(p)
            self.assertEqual((w, h), (3, 2))
            self.assertEqual(px[0], [10, 255, 0])
            self.assertEqual(px[1], [128, 64, 32])

    def test_p5_16bit_scales_to_8bit(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny16.pgm"
            p.write_bytes(b"P5\n2 1\n1023\n" + (0).to_bytes(2,"big") + (1023).to_bytes(2,"big"))
            w, h, px = load_grayscale(p)
            self.assertEqual((w, h), (2, 1))
            self.assertEqual(px[0], [0, 255])
''',
    "tests/test_benchmark.py": r'''
from __future__ import annotations
import unittest
from layoutlib import Point, Wall, SpatialIR
from layoutlib.benchmark import evaluate_walls


def ir(walls):
    return SpatialIR("0.1", "m", 100, 100, 0.02, walls)


def wall(i, x1, y1, x2, y2):
    return Wall(i, Point(x1,y1), Point(x2,y2), .12, 2.7, 1.0)


class BenchmarkTests(unittest.TestCase):
    def test_perfect_match(self):
        truth = ir([wall("a",0,0,2,0), wall("b",2,0,2,2)])
        pred = ir([wall("x",0,0.02,2,0.02), wall("y",2.03,0,2.03,2)])
        m = evaluate_walls(pred, truth)
        self.assertEqual(m.matched, 2)
        self.assertAlmostEqual(m.f1, 1.0)

    def test_false_positive_reduces_precision(self):
        truth = ir([wall("a",0,0,2,0)])
        pred = ir([wall("x",0,0,2,0), wall("extra",0,1,2,1)])
        m = evaluate_walls(pred, truth)
        self.assertEqual(m.matched, 1)
        self.assertAlmostEqual(m.precision, 0.5)
        self.assertAlmostEqual(m.recall, 1.0)
''',
    "docs/BENCHMARK.md": r'''
# LayoutLib Benchmark Protocol

LayoutLib must not claim general floor-plan support from synthetic smoke tests alone.
The real-world gate uses labeled plans and reports geometry metrics separately from
semantic metrics.

## Geometry gate (implemented)

For each plan, store the expected wall centerlines as Spatial IR JSON. Parse the
source raster and compare predicted vs expected walls with `layoutlib.benchmark`.
The current evaluator performs one-to-one matching of orthogonal walls using:

- orientation agreement;
- perpendicular centerline distance tolerance (default 0.08 m);
- minimum segment overlap ratio (default 0.70);
- precision / recall / F1.

A dataset-level report must include per-plan metrics and macro averages. Do not hide
failed samples by reporting only aggregate wall counts.

## Dataset manifest

Use a JSON manifest with entries like:

```json
{
  "schema": "layoutlib-benchmark/0.1",
  "plans": [
    {
      "id": "plan-001",
      "image": "images/plan-001.png",
      "truth_ir": "truth/plan-001.ir.json",
      "meters_per_pixel": 0.01,
      "source": "licensed-or-user-provided",
      "notes": "orthogonal apartment plan"
    }
  ]
}
```

Only include plans whose redistribution/license terms are known. User-provided plans
may be benchmarked privately without committing the source image to Git.

## Next semantic gates

Future benchmark versions add doors, windows and room topology. These must be scored
independently; a high wall F1 is not evidence that openings or rooms are correct.

## Claim levels

- `core_feasible`: deterministic synthetic fixtures pass.
- `format_hardened`: P2/P5 and supported common image ingestion paths are tested.
- `real_world_measured`: labeled real plans have published metrics.
- `semantic_measured`: openings/rooms are labeled and scored.

LayoutLib is not `real_world_measured` until an actual labeled corpus has run.
''',
    "benchmarks/manifest.example.json": r'''
{
  "schema": "layoutlib-benchmark/0.1",
  "plans": []
}
''',
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    args = p.parse_args()
    root = Path(args.target).resolve()
    if not (root / "src" / "layoutlib").exists():
        raise SystemExit("target is not a bootstrapped LayoutLib tree")
    for rel, body in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    print(f"layoutlib_hardening_bootstrap=ok target={root} files={len(FILES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
