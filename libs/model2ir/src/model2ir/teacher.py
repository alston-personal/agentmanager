from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Callable, Mapping

from .audit import audit_asset as _audit_asset
from .reversible import ir_digest
from .v06 import extract_ir, stabilize_external_ir

TEACHER_DATASET_SCHEMA = "model2ir-teacher-dataset/v0.7"
CANONICAL_VIEWS = ("front", "yaw45", "right", "back")

Renderer = Callable[[Path, Path], Mapping[str, str | Path]]


class TeacherDatasetError(ValueError):
    """Raised when a source or generated teacher dataset violates the contract."""


def _dump(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_source_asset(path: str | Path, *, repeats: int = 3) -> dict:
    return _audit_asset(path, extract_ir, stabilize_external_ir, repeats=repeats)


def _safe_case_id(case_id: str) -> str:
    if not case_id or case_id in {".", ".."} or Path(case_id).name != case_id:
        raise TeacherDatasetError("case_id must be one safe path segment")
    return case_id


def _inside(root: Path, candidate: Path) -> tuple[Path, Path]:
    root = root.resolve()
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise TeacherDatasetError(f"dataset path escapes output root: {candidate}") from exc
    return resolved, relative


def _resolve_render(case_dir: Path, value: str | Path, view: str) -> tuple[Path, Path]:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else case_dir / raw
    resolved, relative = _inside(case_dir, candidate)
    if not resolved.is_file():
        raise TeacherDatasetError(f"missing canonical render for {view}: {resolved}")
    return resolved, relative


def validate_teacher_dataset_manifest(manifest: Mapping, *, root: str | Path | None = None) -> None:
    if manifest.get("schema") != TEACHER_DATASET_SCHEMA:
        raise TeacherDatasetError("unsupported teacher dataset schema")

    policy = manifest.get("policy")
    if not isinstance(policy, Mapping):
        raise TeacherDatasetError("teacher dataset policy is required")
    if policy.get("unknowns_are_labels_not_errors") is not True:
        raise TeacherDatasetError("unknown/unresolved values must remain labels")
    if policy.get("external_first_import_claimed_lossless") is not False:
        raise TeacherDatasetError("external first import must not be claimed lossless")
    if tuple(policy.get("canonical_views") or ()) != CANONICAL_VIEWS:
        raise TeacherDatasetError("canonical view contract changed")

    cases = manifest.get("cases")
    examples = manifest.get("examples")
    if not isinstance(cases, list) or len(cases) != 1:
        raise TeacherDatasetError("v0.7 builder requires exactly one source case per manifest")
    if not isinstance(examples, list) or len(examples) != len(CANONICAL_VIEWS):
        raise TeacherDatasetError("teacher manifest must contain exactly four canonical examples")

    views = [item.get("view") for item in examples if isinstance(item, Mapping)]
    if set(views) != set(CANONICAL_VIEWS) or len(views) != len(CANONICAL_VIEWS):
        raise TeacherDatasetError("teacher examples must cover each canonical view exactly once")

    digests = {item.get("target_ir_digest") for item in examples if isinstance(item, Mapping)}
    if len(digests) != 1 or None in digests:
        raise TeacherDatasetError("all canonical views must target the exact same Character IR digest")
    if cases[0].get("target_ir_digest") not in digests:
        raise TeacherDatasetError("case and example target IR digests disagree")

    for item in examples:
        if not isinstance(item, Mapping) or "unresolved" not in item:
            raise TeacherDatasetError("every teacher example must preserve unresolved labels")

    if root is None:
        return

    dataset_root = Path(root).resolve()
    for item in examples:
        image, _ = _inside(dataset_root, dataset_root / str(item["image"]))
        target, _ = _inside(dataset_root, dataset_root / str(item["target_ir"]))
        if not image.is_file() or not target.is_file():
            raise TeacherDatasetError("teacher manifest references a missing artifact")
        if sha256_file(image) != item.get("image_sha256"):
            raise TeacherDatasetError(f"teacher image digest mismatch: {item['image']}")
        target_ir = json.loads(target.read_text(encoding="utf-8"))
        if ir_digest(target_ir) != item.get("target_ir_digest"):
            raise TeacherDatasetError(f"teacher IR digest mismatch: {item['target_ir']}")


def build_teacher_dataset(
    asset: str | Path,
    case_id: str,
    out: str | Path,
    *,
    renderer: Renderer,
    repeats: int = 3,
) -> dict:
    """Build one evidence-preserving multi-view teacher case from a real GLB.

    3D inspection, stabilization, truth policy, hashing, admission and manifest
    construction belong to model2ir. Rendering is deliberately injected so the
    library does not depend on a browser, Three.js, Playwright, or an AgentOS repo
    layout. The renderer must create the four canonical images under ``case_dir``
    and return a mapping from canonical view name to file path.
    """

    source = Path(asset).resolve()
    if not source.is_file():
        raise TeacherDatasetError(f"source asset not found: {source}")
    if source.suffix.lower() != ".glb":
        raise TeacherDatasetError(
            "teacher dataset v0.7 stages self-contained GLB only; core 3D→IR extraction may support additional formats"
        )
    case_id = _safe_case_id(case_id)
    dataset_root = Path(out).resolve()
    case_dir = dataset_root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_source_asset(source, repeats=repeats)
    stability = audit.get("status", "unstable")
    if stability == "unstable":
        raise TeacherDatasetError("asset audit is unstable; refusing teacher dataset admission")

    raw_ir = extract_ir(source)
    stable_ir = stabilize_external_ir(raw_ir)
    stable_digest = ir_digest(stable_ir)
    source_digest = sha256_file(source)

    local_asset = case_dir / "model.glb"
    shutil.copy2(source, local_asset)

    rendered = renderer(local_asset, case_dir)
    if not isinstance(rendered, Mapping):
        raise TeacherDatasetError("renderer must return a view-to-path mapping")

    render_paths: dict[str, tuple[Path, Path]] = {}
    for view in CANONICAL_VIEWS:
        if view not in rendered:
            raise TeacherDatasetError(f"renderer omitted canonical view: {view}")
        render_paths[view] = _resolve_render(case_dir, rendered[view], view)

    _dump(case_dir / "character-ir.json", stable_ir)
    _dump(case_dir / "audit.json", audit)
    unresolved = stable_ir.get("unresolved", [])

    examples = []
    for view in CANONICAL_VIEWS:
        image, image_rel = render_paths[view]
        examples.append(
            {
                "example_id": f"{case_id}:{view}",
                "view": view,
                "image": str(Path(case_id) / image_rel),
                "image_sha256": sha256_file(image),
                "target_ir": str(Path(case_id) / "character-ir.json"),
                "target_ir_digest": stable_digest,
                "truth_status": stable_ir.get("truth_status", "candidate"),
                "semantic_authority": audit.get("semantic_authority"),
                "unresolved": unresolved,
            }
        )

    manifest = {
        "schema": TEACHER_DATASET_SCHEMA,
        "policy": {
            "label_kind": "stabilized-evidence-preserving-character-ir",
            "unknowns_are_labels_not_errors": True,
            "external_first_import_claimed_lossless": False,
            "canonical_views": list(CANONICAL_VIEWS),
        },
        "cases": [
            {
                "case_id": case_id,
                "source_asset": str(Path(case_id) / "model.glb"),
                "source_sha256": source_digest,
                "audit": str(Path(case_id) / "audit.json"),
                "target_ir": str(Path(case_id) / "character-ir.json"),
                "target_ir_digest": stable_digest,
                "stability": stability,
                "semantic_authority": audit.get("semantic_authority"),
                "unresolved_count": len(unresolved),
            }
        ],
        "examples": examples,
    }
    _dump(dataset_root / "manifest.json", manifest)
    validate_teacher_dataset_manifest(manifest, root=dataset_root)
    return manifest
