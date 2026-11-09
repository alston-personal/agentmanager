from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "character_fusion_worker.py"


def _tree() -> ast.Module:
    return ast.parse(WORKER.read_text(encoding="utf-8"))


def test_hf_image_renderer_referenced_by_render_image_exists() -> None:
    tree = _tree()
    defs = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_render_image_hf" in defs
    assert "_render_image_flow" in defs
    assert "_render_image_gemini_web" in defs


def test_hf_credit_exhaustion_is_a_flow_fallback_reason() -> None:
    text = WORKER.read_text(encoding="utf-8")
    hf_call = text.index("return _render_image_hf(target_ir, strict=strict)")
    credit_marker = text.index('"Purchase pre-paid credits"', hf_call)
    flow_call = text.index("return _render_image_flow(target_ir, strict=strict)", hf_call)
    assert hf_call < credit_marker < flow_call
