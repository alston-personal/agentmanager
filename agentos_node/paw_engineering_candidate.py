"""Bounded local Paw patch candidate and non-executing verification.

Not wired to ONE or model authority. Only fixed test artifacts may be edited.
This is an acceptance-candidate receipt, never Claw verification or DONE.
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentos_node.paw_engineering_worktree import (
    BRANCH_PREFIX, PreparedPawWorktree, PawWorktreeBoundaryError, _git, _SHA, _ID,
)

_ALLOWED = frozenset({"tests/test_paw_engineering_worktree.py"})
_MAX_BYTES = 32_768

# Test-only proof: no imports, calls, attributes, decorators, fixtures,
# assignments, comprehensions or access to builtins. NOT a general code runner.
_ALLOWED_AST = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.Assert, ast.Compare,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Eq, ast.NotEq, ast.Lt,
    ast.LtE, ast.Gt, ast.GtE, ast.Constant, ast.Load, ast.UnaryOp,
    ast.USub, ast.UAdd, ast.Pass,
)


def _require_pure_assertion_tests(replacement: str) -> None:
    try:
        tree = ast.parse(replacement)
    except SyntaxError as exc:
        raise PawWorktreeBoundaryError("paw_patch_syntax_invalid") from exc
    if not tree.body or len(tree.body) > 16:
        raise PawWorktreeBoundaryError("paw_patch_test_shape_invalid")
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_AST:
            raise PawWorktreeBoundaryError("paw_patch_executable_syntax_denied")
        if isinstance(node, ast.Constant) and type(node.value) not in {int, bool, str}:
            raise PawWorktreeBoundaryError("paw_patch_constant_denied")
    for node in tree.body:
        if (
            not isinstance(node, ast.FunctionDef)
            or not node.name.startswith("test_")
            or node.decorator_list or node.returns is not None
            or node.args.posonlyargs or node.args.args or node.args.kwonlyargs
            or node.args.vararg is not None or node.args.kwarg is not None
            or not node.body or len(node.body) > 16
            or not all(isinstance(expr, (ast.Assert, ast.Pass)) for expr in node.body)
        ):
            raise PawWorktreeBoundaryError("paw_patch_test_shape_invalid")


def _literal_value(node: ast.AST) -> object:
    """Interpret only safe literal arithmetic/comparisons, never Python bytecode."""
    if isinstance(node, ast.Constant) and type(node.value) in {int, bool, str}:
        if isinstance(node.value, str) and len(node.value) > 256:
            raise PawWorktreeBoundaryError("paw_patch_literal_too_large")
        if isinstance(node.value, int) and abs(node.value) > 1_000_000:
            raise PawWorktreeBoundaryError("paw_patch_integer_out_of_bounds")
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        n = _literal_value(node.operand)
        if type(n) is not int:
            raise PawWorktreeBoundaryError("paw_patch_arithmetic_not_allowed")
        result = -n if isinstance(node.op, ast.USub) else n
        if abs(result) > 1_000_000:
            raise PawWorktreeBoundaryError("paw_patch_integer_out_of_bounds")
        return result
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        left, right = _literal_value(node.left), _literal_value(node.right)
        if type(left) is not int or type(right) is not int:
            raise PawWorktreeBoundaryError("paw_patch_arithmetic_not_allowed")
        result = left + right if isinstance(node.op, ast.Add) else (
            left - right if isinstance(node.op, ast.Sub) else left * right
        )
        if abs(result) > 1_000_000:
            raise PawWorktreeBoundaryError("paw_patch_integer_out_of_bounds")
        return result
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = _literal_value(node.left), _literal_value(node.comparators[0])
        if type(left) is not type(right):
            raise PawWorktreeBoundaryError("paw_patch_comparison_type_mismatch")
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
    raise PawWorktreeBoundaryError("paw_patch_expression_not_allowed")


def _verify_pure_assertions(source: str) -> bool:
    tree = ast.parse(source)
    for function in tree.body:
        for statement in function.body:
            if isinstance(statement, ast.Assert) and _literal_value(statement.test) is not True:
                return False
    return True


@dataclass(frozen=True)
class PawCandidateReceipt:
    branch: str
    base_sha: str
    changed_file: str
    content_sha256: str
    test_exit_code: int
    test_pass: bool
    independent_acceptance_pass: bool = False


def apply_bounded_test_candidate(
    worktree: PreparedPawWorktree, *, relative_path: str,
    expected_sha256: str, replacement: str,
) -> PawCandidateReceipt:
    if relative_path not in _ALLOWED:
        raise PawWorktreeBoundaryError("paw_patch_path_not_authorized")
    if not isinstance(replacement, str) or len(replacement.encode("utf-8")) > _MAX_BYTES:
        raise PawWorktreeBoundaryError("paw_patch_size_invalid")
    if not _SHA.fullmatch(worktree.base_sha):
        raise PawWorktreeBoundaryError("paw_candidate_base_invalid")
    if not worktree.branch.startswith(BRANCH_PREFIX) or not _ID.fullmatch(worktree.branch[len(BRANCH_PREFIX):]):
        raise PawWorktreeBoundaryError("paw_candidate_branch_invalid")
    if worktree.path.is_symlink():
        raise PawWorktreeBoundaryError("paw_candidate_path_symlink")
    root = worktree.path.resolve(strict=True)
    if _git(root, "rev-parse", "--show-toplevel") != str(root):
        raise PawWorktreeBoundaryError("paw_candidate_repo_root_mismatch")
    if _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != worktree.branch:
        raise PawWorktreeBoundaryError("paw_candidate_branch_mismatch")
    if _git(root, "rev-parse", "--verify", "HEAD") != worktree.base_sha:
        raise PawWorktreeBoundaryError("paw_candidate_head_mismatch")
    target = root / relative_path
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
        raise PawWorktreeBoundaryError("paw_patch_target_invalid")
    before = target.read_bytes()
    if hashlib.sha256(before).hexdigest() != expected_sha256:
        raise PawWorktreeBoundaryError("paw_patch_base_mismatch")
    # Refuse modifying any worktree with pre-existing edits.
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                            capture_output=True, text=True, check=True, timeout=10)
    if status.stdout.strip():
        raise PawWorktreeBoundaryError("paw_patch_worktree_dirty")
    # Syntax check before making any candidate changes; no shell or model command.
    _require_pure_assertion_tests(replacement)
    target.write_text(replacement, encoding="utf-8")
    diff = subprocess.run(["git", "-C", str(root), "diff", "--check"],
                          capture_output=True, text=True, timeout=10)
    if diff.returncode:
        target.write_bytes(before)
        raise PawWorktreeBoundaryError("paw_patch_diff_check_failed")
    # Never invoke pytest on an untrusted checkout: conftest.py, plugins and
    # repository import hooks can execute code regardless of the AST allowlist.
    passed = _verify_pure_assertions(replacement)
    return PawCandidateReceipt(
        branch=worktree.branch, base_sha=worktree.base_sha,
        changed_file=relative_path,
        content_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        test_exit_code=0 if passed else 1, test_pass=passed,
    )
