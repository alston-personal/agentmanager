"""LayoutLib Spatial IR export adapters.

The canonical artifact is Spatial IR, not the current browser preview. This
module demonstrates the intended boundary:

    Spatial IR -> neutral Mesh IR -> format exporter

OBJ is implemented as the first deterministic reference target. glTF/GLB, USD,
IFC, Unity or Blender adapters can reuse the same Mesh IR without changing the
LayoutLib parser.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any, Mapping, Sequence


Vec3 = tuple[float, float, float]
Face = tuple[int, int, int, int]


@dataclass(frozen=True)
class MeshObject:
    name: str
    vertices: tuple[Vec3, ...]
    faces: tuple[Face, ...]
    metadata: Mapping[str, Any]


def _wall_mesh(wall: Mapping[str, Any], index: int) -> MeshObject:
    start = wall["start"]
    end = wall["end"]
    x1, y1 = float(start["x"]), float(start["y"])
    x2, y2 = float(end["x"]), float(end["y"])
    height = float(wall.get("height", 2.7))
    thickness = float(wall.get("thickness", 0.12))
    dx, dy = x2 - x1, y2 - y1
    length = hypot(dx, dy)
    if length <= 1e-9:
        raise ValueError("zero-length wall cannot be exported")
    nx = -dy / length * thickness / 2.0
    ny = dx / length * thickness / 2.0
    # bottom ring followed by top ring
    v = (
        (x1 + nx, y1 + ny, 0.0),
        (x2 + nx, y2 + ny, 0.0),
        (x2 - nx, y2 - ny, 0.0),
        (x1 - nx, y1 - ny, 0.0),
        (x1 + nx, y1 + ny, height),
        (x2 + nx, y2 + ny, height),
        (x2 - nx, y2 - ny, height),
        (x1 - nx, y1 - ny, height),
    )
    f = (
        (0, 1, 2, 3),  # bottom
        (4, 7, 6, 5),  # top
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    )
    return MeshObject(
        name=str(wall.get("id") or f"wall_{index}"),
        vertices=v,
        faces=f,
        metadata={
            "kind": "wall",
            "source": wall.get("source"),
            "height": height,
            "thickness": thickness,
        },
    )


def spatial_ir_to_mesh_objects(ir: Mapping[str, Any]) -> list[MeshObject]:
    """Convert LayoutLib Spatial IR into renderer/exporter-neutral meshes."""
    objects: list[MeshObject] = []
    for i, wall in enumerate(ir.get("walls", ())):
        objects.append(_wall_mesh(wall, i))
    return objects


def mesh_objects_to_obj(objects: Sequence[MeshObject]) -> str:
    """Export neutral mesh objects as Wavefront OBJ text."""
    lines = ["# Generated from LayoutLib Spatial IR", "# units: meters"]
    offset = 1
    for obj in objects:
        safe_name = obj.name.replace(" ", "_")
        lines.append(f"o {safe_name}")
        for x, y, z in obj.vertices:
            lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
        for face in obj.faces:
            ids = " ".join(str(offset + i) for i in face)
            lines.append(f"f {ids}")
        offset += len(obj.vertices)
    return "\n".join(lines) + "\n"


def spatial_ir_to_obj(ir: Mapping[str, Any]) -> str:
    return mesh_objects_to_obj(spatial_ir_to_mesh_objects(ir))
