#!/usr/bin/env python3
"""Upgrade a generated LayoutLib tree with an explicit source-image coordinate frame.

This migration makes image ↔ Spatial IR alignment a library invariant instead of a
viewer convention. The canonical anchor is a source-image pixel bound to a world
coordinate. ROI parsing uses the ROI top-left as the anchor; full-image parsing uses
(0, 0). The transform is reversible and independent from browser/CSS scaling.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import textwrap

FILES = {
    "src/layoutlib/frames.py": r'''
from __future__ import annotations
from dataclasses import dataclass, asdict
import math

@dataclass(frozen=True)
class PixelPoint:
    x: float
    y: float

@dataclass(frozen=True)
class CoordinateFrame:
    """Reversible mapping between source-image pixels and Spatial IR world meters.

    `anchor_px` is a point in the ORIGINAL source image, never a CSS/display point.
    `anchor_world_m` is the world coordinate assigned to that exact source pixel.
    Current v0.3 plans use rotation_deg=0 and image_y_axis='down'.
    """
    anchor_px: PixelPoint
    anchor_world_m: PixelPoint
    meters_per_pixel: float
    rotation_deg: float = 0.0
    image_y_axis: str = "down"

    def __post_init__(self):
        if self.meters_per_pixel <= 0:
            raise ValueError("meters_per_pixel must be > 0")
        if self.image_y_axis not in {"down", "up"}:
            raise ValueError("image_y_axis must be 'down' or 'up'")

    def source_px_to_world(self, p: PixelPoint) -> PixelPoint:
        dx = (p.x - self.anchor_px.x) * self.meters_per_pixel
        dy_px = p.y - self.anchor_px.y
        dy = dy_px * self.meters_per_pixel * (1.0 if self.image_y_axis == "down" else -1.0)
        a = math.radians(self.rotation_deg)
        ca, sa = math.cos(a), math.sin(a)
        return PixelPoint(
            self.anchor_world_m.x + dx * ca - dy * sa,
            self.anchor_world_m.y + dx * sa + dy * ca,
        )

    def world_to_source_px(self, p: PixelPoint) -> PixelPoint:
        dx = p.x - self.anchor_world_m.x
        dy = p.y - self.anchor_world_m.y
        a = math.radians(-self.rotation_deg)
        ca, sa = math.cos(a), math.sin(a)
        rx = dx * ca - dy * sa
        ry = dx * sa + dy * ca
        if self.image_y_axis == "up":
            ry = -ry
        return PixelPoint(
            self.anchor_px.x + rx / self.meters_per_pixel,
            self.anchor_px.y + ry / self.meters_per_pixel,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CoordinateFrame":
        return cls(
            anchor_px=PixelPoint(**data["anchor_px"]),
            anchor_world_m=PixelPoint(**data.get("anchor_world_m", {"x": 0.0, "y": 0.0})),
            meters_per_pixel=float(data["meters_per_pixel"]),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            image_y_axis=str(data.get("image_y_axis", "down")),
        )
''',
    "src/layoutlib/models.py": r'''
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path
from .frames import CoordinateFrame, PixelPoint

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
    source: str = "auto"

@dataclass
class SpatialIR:
    version: str
    units: str
    image_width_px: int
    image_height_px: int
    meters_per_pixel: float
    walls: list[Wall]
    coordinate_frame: CoordinateFrame | None = None
    analysis_region_px: dict | None = None

    def __post_init__(self):
        # Backward-compatible default makes legacy v0.1 IR explicit on load/use.
        if self.coordinate_frame is None:
            self.coordinate_frame = CoordinateFrame(
                anchor_px=PixelPoint(0.0, 0.0),
                anchor_world_m=PixelPoint(0.0, 0.0),
                meters_per_pixel=self.meters_per_pixel,
            )
        if self.analysis_region_px is None:
            self.analysis_region_px = {
                "x": 0, "y": 0,
                "width": self.image_width_px,
                "height": self.image_height_px,
            }

    def source_px_to_world(self, x: float, y: float) -> Point:
        p = self.coordinate_frame.source_px_to_world(PixelPoint(x, y))
        return Point(p.x, p.y)

    def world_to_source_px(self, p: Point) -> PixelPoint:
        return self.coordinate_frame.world_to_source_px(PixelPoint(p.x, p.y))

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
            id=w["id"], start=Point(**w["start"]), end=Point(**w["end"]),
            thickness=float(w["thickness"]), height=float(w["height"]),
            confidence=float(w.get("confidence", 1.0)), source=str(w.get("source", "auto")),
        ) for w in data.get("walls", [])]
        frame_data = data.get("coordinate_frame")
        frame = CoordinateFrame.from_dict(frame_data) if frame_data else None
        return cls(
            version=str(data["version"]), units=str(data["units"]),
            image_width_px=int(data["image_width_px"]), image_height_px=int(data["image_height_px"]),
            meters_per_pixel=float(data["meters_per_pixel"]), walls=walls,
            coordinate_frame=frame, analysis_region_px=data.get("analysis_region_px"),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "SpatialIR":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
''',
    "src/layoutlib/parser.py": r'''
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .imageio import load_grayscale
from .frames import CoordinateFrame, PixelPoint
from .models import Point, Wall, SpatialIR

@dataclass
class _Run:
    axis: str
    coord: int
    a: int
    b: int

def _runs(bits, min_len: int):
    start = None
    seq = list(bits)
    for i, on in enumerate(seq + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_len:
                yield start, i - 1
            start = None

def _overlap_ratio(a0, a1, b0, b1):
    inter=max(0,min(a1,b1)-max(a0,b0)+1)
    return inter/max(1,min(a1-a0+1,b1-b0+1))

def _collapse(candidates, max_thickness_px):
    out=[]; used=[False]*len(candidates)
    for i,seed in enumerate(candidates):
        if used[i]: continue
        group=[seed]; used[i]=True; changed=True
        while changed:
            changed=False; coords=[g.coord for g in group]
            lo,hi=min(coords),max(coords); ga=min(g.a for g in group); gb=max(g.b for g in group)
            for j,c in enumerate(candidates):
                if used[j] or c.axis!=seed.axis: continue
                if c.coord<lo-1 or c.coord>hi+1: continue
                if max(hi,c.coord)-min(lo,c.coord)+1>max_thickness_px: continue
                if _overlap_ratio(ga,gb,c.a,c.b)>=.72:
                    group.append(c); used[j]=True; changed=True
        coords=[g.coord for g in group]
        out.append((seed.axis,sum(coords)/len(coords),min(g.a for g in group),max(g.b for g in group),len(set(coords))))
    return out

def _normalize_region(region, width, height):
    if region is None:
        return {"x":0,"y":0,"width":width,"height":height}
    x=max(0,min(int(region["x"]),width-1)); y=max(0,min(int(region["y"]),height-1))
    w=max(1,min(int(region["width"]),width-x)); h=max(1,min(int(region["height"]),height-y))
    return {"x":x,"y":y,"width":w,"height":h}

def parse_floorplan(path: str | Path, *, meters_per_pixel: float=.02, threshold: int=128,
                    min_wall_length_px: int=16, max_wall_thickness_px: int=16,
                    wall_height_m: float=2.7, default_thickness_m: float=.12,
                    analysis_region_px: dict | None=None) -> SpatialIR:
    """Parse raster to anchored Spatial IR.

    Geometry is expressed in world meters relative to an explicit source-image anchor.
    For ROI analysis, ROI top-left source pixel maps exactly to world (0,0).
    """
    if meters_per_pixel<=0: raise ValueError("meters_per_pixel must be > 0")
    width,height,pix=load_grayscale(path)
    region=_normalize_region(analysis_region_px,width,height)
    x0,y0,w,h=region["x"],region["y"],region["width"],region["height"]
    frame=CoordinateFrame(PixelPoint(x0,y0),PixelPoint(0.0,0.0),meters_per_pixel)
    dark=[[pix[y0+y][x0+x]<=threshold for x in range(w)] for y in range(h)]
    candidates=[]
    for y in range(h):
        for a,b in _runs(dark[y],min_wall_length_px): candidates.append(_Run("h",y,a,b))
    for x in range(w):
        for a,b in _runs([dark[y][x] for y in range(h)],min_wall_length_px): candidates.append(_Run("v",x,a,b))
    walls=[]
    for n,(axis,coord,a,b,thick_px) in enumerate(_collapse(candidates,max_wall_thickness_px),1):
        if axis=="h":
            s_px=PixelPoint(x0+a,y0+coord); e_px=PixelPoint(x0+b,y0+coord)
        else:
            s_px=PixelPoint(x0+coord,y0+a); e_px=PixelPoint(x0+coord,y0+b)
        s=frame.source_px_to_world(s_px); e=frame.source_px_to_world(e_px)
        thickness=thick_px*meters_per_pixel if thick_px>1 else default_thickness_m
        walls.append(Wall(f"wall-{n:04d}",Point(s.x,s.y),Point(e.x,e.y),thickness,wall_height_m,1.0,"auto"))
    return SpatialIR("0.3","m",width,height,meters_per_pixel,walls,frame,region)
''',
    "src/layoutlib/__init__.py": r'''
"""LayoutLib public API."""
from .frames import PixelPoint, CoordinateFrame
from .models import Point, Wall, SpatialIR
from .parser import parse_floorplan
from .obj import export_obj

__all__=["PixelPoint","CoordinateFrame","Point","Wall","SpatialIR","parse_floorplan","export_obj"]
__version__="0.3.0"
''',
    "tests/test_coordinate_frame.py": r'''
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from layoutlib import CoordinateFrame, PixelPoint, parse_floorplan

def make_pgm(path: Path, w=100, h=80):
    p=[[255]*w for _ in range(h)]
    # wall entirely inside ROI x=20..80, y=10..60
    for y in range(20,25):
        for x in range(30,71): p[y][x]=0
    path.write_text("P2\n%d %d\n255\n%s\n"%(w,h,"\n".join(" ".join(map(str,r)) for r in p)))

class CoordinateFrameTests(unittest.TestCase):
    def test_round_trip_source_world_source(self):
        f=CoordinateFrame(PixelPoint(123,45),PixelPoint(0,0),.02)
        p=PixelPoint(319.25,211.5)
        q=f.world_to_source_px(f.source_px_to_world(p))
        self.assertAlmostEqual(p.x,q.x,places=9); self.assertAlmostEqual(p.y,q.y,places=9)

    def test_roi_anchor_is_bound_to_world_origin(self):
        f=CoordinateFrame(PixelPoint(20,10),PixelPoint(0,0),.02)
        q=f.source_px_to_world(PixelPoint(20,10))
        self.assertEqual((q.x,q.y),(0,0))

    def test_detected_wall_maps_back_to_original_source_pixels(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"plan.pgm"; make_pgm(p)
            ir=parse_floorplan(p,meters_per_pixel=.02,min_wall_length_px=20,
                               analysis_region_px={"x":20,"y":10,"width":61,"height":51})
            self.assertTrue(ir.walls)
            wall=ir.walls[0]
            a=ir.world_to_source_px(wall.start); b=ir.world_to_source_px(wall.end)
            self.assertGreaterEqual(a.x,20); self.assertGreaterEqual(a.y,10)
            self.assertLessEqual(b.x,80); self.assertLessEqual(b.y,60)
            # World->source must be exact enough to draw on the original raster.
            for world in (wall.start,wall.end):
                px=ir.world_to_source_px(world)
                world2=ir.source_px_to_world(px.x,px.y)
                self.assertAlmostEqual(world.x,world2.x,places=9)
                self.assertAlmostEqual(world.y,world2.y,places=9)

if __name__=="__main__": unittest.main()
''',
}

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--target",default="/home/ubuntu/layoutlib")
    args=ap.parse_args(); root=Path(args.target)
    if not (root/"src/layoutlib").is_dir():
        raise SystemExit(f"not a LayoutLib tree: {root}")
    for rel,content in FILES.items():
        p=root/rel; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(textwrap.dedent(content).lstrip("\n"),encoding="utf-8")
    print(f"layoutlib_coordinate_frame_upgrade=ok target={root} files={len(FILES)}")
    return 0

if __name__=="__main__": raise SystemExit(main())
