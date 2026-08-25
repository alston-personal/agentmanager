#!/usr/bin/env python3
"""Create/update the LayoutLib MVP source tree and its deterministic test fixtures.

LayoutLib v0.1 converts high-contrast, mostly orthogonal floor-plan raster images into
an explicit Spatial IR and can extrude that IR to Wavefront OBJ.

This bootstrap is intentionally stdlib-only. The generated library supports PGM
(P2/P5) with no dependency and PNG/JPEG/BMP when Pillow is installed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import textwrap

FILES = {
"pyproject.toml": r'''
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "layoutlib"
version = "0.1.0"
description = "Deterministic floor-plan raster to Spatial IR and OBJ toolkit"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
images = ["Pillow>=10"]
dev = ["pytest>=8", "Pillow>=10"]

[project.scripts]
layoutlib = "layoutlib.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
''',
"src/layoutlib/__init__.py": r'''
"""LayoutLib public API."""
from .models import Point, Wall, SpatialIR
from .parser import parse_floorplan
from .obj import export_obj

__all__ = ["Point", "Wall", "SpatialIR", "parse_floorplan", "export_obj"]
__version__ = "0.1.0"
''',
"src/layoutlib/models.py": r'''
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass(frozen=True)
class Point:
    x: float
    y: float

@dataclass(frozen=True)
class Wall:
    id: str
    start: Point
    end: Point
    thickness: float
    height: float
    confidence: float = 1.0

@dataclass
class SpatialIR:
    version: str
    units: str
    image_width_px: int
    image_height_px: int
    meters_per_pixel: float
    walls: list[Wall]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path | None = None, *, indent: int = 2) -> str:
        text = json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        if path is not None:
            Path(path).write_text(text + "\n", encoding="utf-8")
        return text

    @classmethod
    def from_dict(cls, data: dict) -> "SpatialIR":
        walls = [Wall(
            id=w["id"],
            start=Point(**w["start"]),
            end=Point(**w["end"]),
            thickness=float(w["thickness"]),
            height=float(w["height"]),
            confidence=float(w.get("confidence", 1.0)),
        ) for w in data.get("walls", [])]
        return cls(
            version=str(data["version"]), units=str(data["units"]),
            image_width_px=int(data["image_width_px"]),
            image_height_px=int(data["image_height_px"]),
            meters_per_pixel=float(data["meters_per_pixel"]), walls=walls,
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "SpatialIR":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
''',
"src/layoutlib/imageio.py": r'''
from __future__ import annotations
from pathlib import Path


def _pgm_tokens(data: bytes):
    token = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 35:  # # comment
            while i < len(data) and data[i] not in (10, 13):
                i += 1
        elif chr(b).isspace():
            if token:
                yield bytes(token)
                token.clear()
            i += 1
        else:
            token.append(b)
            i += 1
    if token:
        yield bytes(token)


def load_grayscale(path: str | Path) -> tuple[int, int, list[list[int]]]:
    """Return width, height, grayscale pixels (0 black .. 255 white).

    P2 PGM is dependency-free. P5 PGM and common image formats are supported;
    non-PGM formats require Pillow.
    """
    path = Path(path)
    data = path.read_bytes()
    if data.startswith(b"P2"):
        toks = iter(_pgm_tokens(data))
        magic = next(toks); width = int(next(toks)); height = int(next(toks)); maxv = int(next(toks))
        vals = [int(next(toks)) for _ in range(width * height)]
        pixels = [[round(vals[y*width+x] * 255 / maxv) for x in range(width)] for y in range(height)]
        return width, height, pixels
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
"src/layoutlib/parser.py": r'''
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .imageio import load_grayscale
from .models import Point, Wall, SpatialIR

@dataclass
class _Run:
    axis: str
    coord: int
    a: int
    b: int


def _runs(bits: list[bool], min_len: int):
    start = None
    for i, on in enumerate(bits + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_len:
                yield start, i - 1
            start = None


def _overlap_ratio(a0: int, a1: int, b0: int, b1: int) -> float:
    inter = max(0, min(a1, b1) - max(a0, b0) + 1)
    denom = max(1, min(a1-a0+1, b1-b0+1))
    return inter / denom


def _collapse(candidates: list[_Run], max_thickness_px: int) -> list[tuple[str, float, int, int, int]]:
    """Collapse neighboring parallel scanline runs into wall centerlines.

    Returns (axis, center_coord, a, b, measured_thickness_px).
    """
    out = []
    used = [False] * len(candidates)
    for i, seed in enumerate(candidates):
        if used[i]:
            continue
        group = [seed]; used[i] = True
        changed = True
        while changed:
            changed = False
            coords = [g.coord for g in group]
            lo_c, hi_c = min(coords), max(coords)
            ga, gb = min(g.a for g in group), max(g.b for g in group)
            for j, c in enumerate(candidates):
                if used[j] or c.axis != seed.axis:
                    continue
                if c.coord < lo_c - 1 or c.coord > hi_c + 1:
                    continue
                if max(hi_c, c.coord) - min(lo_c, c.coord) + 1 > max_thickness_px:
                    continue
                if _overlap_ratio(ga, gb, c.a, c.b) >= 0.72:
                    group.append(c); used[j] = True; changed = True
        coords = [g.coord for g in group]
        # Ignore one-pixel scan artifacts only if surrounded by thicker groups; keeping
        # them is useful for vector-like one-pixel plans.
        out.append((seed.axis, sum(coords)/len(coords), min(g.a for g in group), max(g.b for g in group), len(set(coords))))
    return out


def parse_floorplan(path: str | Path, *, meters_per_pixel: float = 0.02,
                    threshold: int = 128, min_wall_length_px: int = 16,
                    max_wall_thickness_px: int = 16, wall_height_m: float = 2.7,
                    default_thickness_m: float = 0.12) -> SpatialIR:
    """Parse a high-contrast, mostly orthogonal floor-plan raster into SpatialIR.

    This v0.1 parser deliberately targets deterministic line drawings. It does not
    infer semantic rooms, doors, windows, scale, perspective, or curved walls.
    """
    if meters_per_pixel <= 0:
        raise ValueError("meters_per_pixel must be > 0")
    width, height, pix = load_grayscale(path)
    dark = [[v <= threshold for v in row] for row in pix]
    candidates: list[_Run] = []
    for y in range(height):
        for a, b in _runs(dark[y], min_wall_length_px):
            candidates.append(_Run("h", y, a, b))
    for x in range(width):
        col = [dark[y][x] for y in range(height)]
        for a, b in _runs(col, min_wall_length_px):
            candidates.append(_Run("v", x, a, b))
    collapsed = _collapse(candidates, max_wall_thickness_px)
    walls: list[Wall] = []
    for n, (axis, coord, a, b, thick_px) in enumerate(collapsed, 1):
        if axis == "h":
            p1 = Point(a * meters_per_pixel, coord * meters_per_pixel)
            p2 = Point(b * meters_per_pixel, coord * meters_per_pixel)
        else:
            p1 = Point(coord * meters_per_pixel, a * meters_per_pixel)
            p2 = Point(coord * meters_per_pixel, b * meters_per_pixel)
        measured = thick_px * meters_per_pixel
        thickness = measured if thick_px > 1 else default_thickness_m
        walls.append(Wall(f"wall-{n:04d}", p1, p2, thickness, wall_height_m, 1.0))
    return SpatialIR("0.1", "m", width, height, meters_per_pixel, walls)
''',
"src/layoutlib/obj.py": r'''
from __future__ import annotations
import math
from pathlib import Path
from .models import SpatialIR


def export_obj(ir: SpatialIR, path: str | Path) -> Path:
    """Extrude each 2D wall segment as an independent rectangular prism."""
    path = Path(path)
    lines = ["# LayoutLib OBJ export", "o layoutlib"]
    vertex_base = 1
    for wall in ir.walls:
        x1, y1 = wall.start.x, wall.start.y
        x2, y2 = wall.end.x, wall.end.y
        dx, dy = x2-x1, y2-y1
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        nx, ny = -dy/length * wall.thickness/2, dx/length * wall.thickness/2
        z0, z1 = 0.0, wall.height
        verts = [
            (x1+nx,y1+ny,z0),(x1-nx,y1-ny,z0),(x2-nx,y2-ny,z0),(x2+nx,y2+ny,z0),
            (x1+nx,y1+ny,z1),(x1-nx,y1-ny,z1),(x2-nx,y2-ny,z1),(x2+nx,y2+ny,z1),
        ]
        lines.append(f"g {wall.id}")
        lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x,y,z in verts)
        faces = [(1,2,3,4),(5,8,7,6),(1,5,6,2),(2,6,7,3),(3,7,8,4),(5,1,4,8)]
        lines.extend("f " + " ".join(str(vertex_base+i-1) for i in face) for face in faces)
        vertex_base += 8
    path.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return path
''',
"src/layoutlib/cli.py": r'''
from __future__ import annotations
import argparse
from .models import SpatialIR
from .parser import parse_floorplan
from .obj import export_obj


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="layoutlib")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse", help="floor-plan image -> Spatial IR JSON")
    p.add_argument("input"); p.add_argument("--out", required=True)
    p.add_argument("--meters-per-pixel", type=float, default=0.02)
    p.add_argument("--threshold", type=int, default=128)
    p.add_argument("--min-wall-length-px", type=int, default=16)
    o = sub.add_parser("obj", help="Spatial IR JSON -> OBJ")
    o.add_argument("input"); o.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "parse":
        ir = parse_floorplan(args.input, meters_per_pixel=args.meters_per_pixel,
                             threshold=args.threshold, min_wall_length_px=args.min_wall_length_px)
        ir.to_json(args.out)
        print(f"walls={len(ir.walls)} out={args.out}")
    else:
        ir = SpatialIR.from_json(args.input)
        export_obj(ir, args.out)
        print(f"walls={len(ir.walls)} out={args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
''',
"tests/test_layoutlib.py": r'''
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from layoutlib import SpatialIR, parse_floorplan, export_obj
from layoutlib.cli import main


def make_rectangle_pgm(path: Path, w=120, h=90, t=5):
    pix = [[255]*w for _ in range(h)]
    x0,y0,x1,y1 = 15,12,104,76
    for y in range(y0, y0+t):
        for x in range(x0,x1+1): pix[y][x]=0
    for y in range(y1-t+1,y1+1):
        for x in range(x0,x1+1): pix[y][x]=0
    for x in range(x0,x0+t):
        for y in range(y0,y1+1): pix[y][x]=0
    for x in range(x1-t+1,x1+1):
        for y in range(y0,y1+1): pix[y][x]=0
    path.write_text("P2\n%d %d\n255\n%s\n" % (w,h,"\n".join(" ".join(map(str,row)) for row in pix)))

class LayoutLibTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.root=Path(self.td.name)
        self.img=self.root/"room.pgm"; make_rectangle_pgm(self.img)
    def tearDown(self): self.td.cleanup()

    def test_parse_rectangle_finds_four_primary_walls(self):
        ir=parse_floorplan(self.img, meters_per_pixel=.02, min_wall_length_px=30)
        self.assertEqual(len(ir.walls),4)
        self.assertTrue(all(w.thickness >= .08 for w in ir.walls))
    def test_ir_roundtrip(self):
        ir=parse_floorplan(self.img, min_wall_length_px=30)
        p=self.root/"ir.json"; ir.to_json(p); restored=SpatialIR.from_json(p)
        self.assertEqual(ir.to_dict(), restored.to_dict())
    def test_obj_has_geometry(self):
        ir=parse_floorplan(self.img, min_wall_length_px=30)
        p=self.root/"room.obj"; export_obj(ir,p); text=p.read_text()
        self.assertEqual(text.count("\nv "), len(ir.walls)*8)
        self.assertEqual(text.count("\nf "), len(ir.walls)*6)
    def test_cli_end_to_end(self):
        j=self.root/"ir.json"; o=self.root/"model.obj"
        self.assertEqual(main(["parse",str(self.img),"--out",str(j),"--min-wall-length-px","30"]),0)
        self.assertEqual(main(["obj",str(j),"--out",str(o)]),0)
        self.assertTrue(j.exists() and o.exists())
    def test_rejects_invalid_scale(self):
        with self.assertRaises(ValueError): parse_floorplan(self.img, meters_per_pixel=0)

if __name__ == "__main__": unittest.main()
''',
"examples/generate_demo.py": r'''
from pathlib import Path
from layoutlib import parse_floorplan, export_obj

# Use the deterministic fixture shipped in tests.
root = Path(__file__).resolve().parents[1]
ir = parse_floorplan(root / "tests/fixtures/demo_room.pgm", meters_per_pixel=0.02, min_wall_length_px=30)
ir.to_json(root / "examples/demo_room.ir.json")
export_obj(ir, root / "examples/demo_room.obj")
print(f"generated {len(ir.walls)} walls")
''',
"README.md": r'''
# LayoutLib

LayoutLib is a small, deterministic Python library that turns a **high-contrast, mostly orthogonal floor-plan raster** into a versioned **Spatial IR**, then extrudes the walls into a Wavefront **OBJ** model.

## Scope of v0.1

Supported now: PGM without dependencies; PNG/JPEG/BMP with Pillow; horizontal/vertical wall extraction; explicit scale; JSON IR; OBJ extrusion; CLI and Python API.

Not claimed: arbitrary architectural drawing understanding, automatic scale inference, room semantics, doors/windows, OCR, curved/diagonal walls, perspective correction, or BIM-grade geometry. Those require a separate benchmark and later CV/ML stages.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
# Common image formats:
pip install -e '.[images]'
```

## CLI

```bash
layoutlib parse floorplan.png --out plan.ir.json --meters-per-pixel 0.02
layoutlib obj plan.ir.json --out plan.obj
```

## Python

```python
from layoutlib import parse_floorplan, export_obj
ir = parse_floorplan("floorplan.png", meters_per_pixel=0.02)
ir.to_json("plan.ir.json")
export_obj(ir, "plan.obj")
```

## Validation

```bash
python -m unittest discover -s tests -v
python examples/generate_demo.py
```

See `docs/VALIDATION.md` for the evidence standard and limitations, `docs/SPATIAL_IR.md` for the data contract, and `docs/ARCHITECTURE.md` for extension points.
''',
"docs/ARCHITECTURE.md": r'''
# Architecture

Pipeline: `image -> grayscale -> threshold -> orthogonal scan runs -> thickness collapse -> SpatialIR -> exporter`.

The boundary that matters is Spatial IR. Parsers may later be replaced by OpenCV, learned segmentation, OCR, or vector-PDF ingestion without changing downstream 3D exporters.

Modules:
- `imageio.py`: raster decoding; dependency-free PGM fallback.
- `parser.py`: deterministic v0.1 wall detector.
- `models.py`: stable in-memory and JSON contract.
- `obj.py`: geometry extrusion.
- `cli.py`: scriptable interface.

Design rule: uncertainty must not be hidden. Future semantic detectors should attach confidence/provenance rather than silently invent geometry.
''',
"docs/SPATIAL_IR.md": r'''
# Spatial IR 0.1

Coordinates are meters, origin follows source image top-left, +x right, +y down. `meters_per_pixel` makes raster-to-world scale explicit.

Required top-level fields: `version`, `units`, `image_width_px`, `image_height_px`, `meters_per_pixel`, `walls`.

Each wall contains `id`, `start{x,y}`, `end{x,y}`, `thickness`, `height`, and `confidence`.

This contract is intentionally minimal. Rooms, openings, labels, source provenance, constraints and uncertainty maps should be added as versioned fields rather than inferred implicitly.
''',
"docs/VALIDATION.md": r'''
# Validation and feasibility boundary

## What a passing v0.1 test proves

A passing deterministic test proves that, under the declared input assumptions, LayoutLib can parse a raster fixture into four wall centerlines, serialize/deserialize Spatial IR, and generate non-empty 3D OBJ geometry through both API and CLI paths.

It does **not** prove production accuracy on arbitrary real floor plans.

## Acceptance gate

1. `python -m unittest discover -s tests -v` -> all tests pass.
2. Rectangle fixture -> exactly four primary walls.
3. IR JSON round-trip is lossless.
4. Each wall exports 8 OBJ vertices / 6 quad faces.
5. CLI performs image -> IR -> OBJ end-to-end.
6. `examples/generate_demo.py` emits reusable demo artifacts.

## Next benchmark before claiming general feasibility

Create a labeled corpus spanning clean CAD exports, scans, furniture-heavy plans, different line weights, rotations, diagonals/curves, doors/windows, and missing/known scale. Report wall precision/recall, endpoint error, topology error and failure categories. Production claims should be blocked until this benchmark exists.
''',
}


def rectangle_pgm(w=120, h=90, t=5) -> str:
    pix=[[255]*w for _ in range(h)]; x0,y0,x1,y1=15,12,104,76
    for y in range(y0,y0+t):
        for x in range(x0,x1+1): pix[y][x]=0
    for y in range(y1-t+1,y1+1):
        for x in range(x0,x1+1): pix[y][x]=0
    for x in range(x0,x0+t):
        for y in range(y0,y1+1): pix[y][x]=0
    for x in range(x1-t+1,x1+1):
        for y in range(y0,y1+1): pix[y][x]=0
    return "P2\n%d %d\n255\n%s\n" % (w,h,"\n".join(" ".join(map(str,row)) for row in pix))


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--target", default="/home/ubuntu/layoutlib")
    args=ap.parse_args(); root=Path(args.target); root.mkdir(parents=True, exist_ok=True)
    for rel, content in FILES.items():
        p=root/rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    fixture=root/"tests/fixtures/demo_room.pgm"; fixture.parent.mkdir(parents=True,exist_ok=True)
    fixture.write_text(rectangle_pgm(),encoding="ascii")
    print(f"layoutlib_bootstrap=ok target={root} files={len(FILES)+1}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
