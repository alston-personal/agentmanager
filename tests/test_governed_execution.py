from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from agent_core.governed_execution import (
    RECEIPT_SCHEMA,
    execute_bound_work_intent,
    resolve_authority,
    resolve_product_work_intent_ref,
)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _fixture(tmp_path: Path):
    repo = tmp_path / "zeus-writer"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "AgentOS Test")
    _git(repo, "remote", "add", "origin", "https://github.com/alston-personal/zeus-writer.git")

    selected = {
        "project": "AgentOS開發血淚史",
        "action": "review_existing_draft",
        "chapter": "Ch05",
        "draft_path": "scratch/Ch05_draft.tmp.md",
        "mutation_allowed": False,
        "publish_allowed": False,
        "publication_blocker": "publication_state_not_verified",
        "reason": "safe_review_available_while_publication_reconciliation_is_blocked",
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(selected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    work_ref = {
        "schema": "agentos.employee-work-intent-ref/v1",
        "product_id": "zeus-writer",
        "state_key": "current-work",
        "revision": 1,
        "digest": digest,
    }
    manifest = {
        "schema": "zeus.writer-work-intent/v1",
        "revision": 1,
        "selected_work": selected,
        "core_ref": work_ref,
    }
    manifest_path = repo / ".agentos" / "work-intents" / "current.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draft = repo / "scratch" / "Ch05_draft.tmp.md"
    draft.parent.mkdir()
    draft.write_text(
        "# 第05章：測試草稿\n\n"
        + "## 一、開始\n\n"
        + ("這是一段足夠長的既有草稿內容，用來驗證唯讀 review adapter。\n" * 80)
        + "\n## 二、收束\n\n"
        + ("不修改正文、不發布，只產生可驗證的 review receipt。\n" * 40),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture source")
    source_sha = _git(repo, "rev-parse", "HEAD")

    request = {
        "schema": "agentos.execution-request/v1",
        "request_id": "zeus-review-" + source_sha,
        "project_id": "zeus-writer",
        "repository": "alston-personal/zeus-writer",
        "source_ref": "master",
        "source_sha": source_sha,
        "capability": "zeus.writer.draft.review",
        "environment": "writing",
        "parameters": {
            "chapter": "Ch05",
            "work_intent_state_key": "current-work",
            "work_intent_revision": 1,
            "work_intent_digest": digest,
        },
        "replay_policy": "idempotent",
        "expected_result": "agentos.execution-receipt/v1",
    }
    request_path = repo / ".agentos" / "execution-requests" / "draft-review.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", ".agentos/execution-requests/draft-review.json")
    _git(repo, "commit", "-m", "product-owned request")
    request_commit = _git(repo, "rev-parse", "HEAD")

    cache = tmp_path / "zeus-writer-cache.git"
    clone = subprocess.run(
        ["git", "clone", "--bare", str(repo), str(cache)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert clone.returncode == 0, clone.stderr
    _git(cache, "update-ref", "refs/agentos/master", request_commit)
    _git(cache, "remote", "set-url", "origin", "https://github.com/alston-personal/zeus-writer.git")

    registry = {
        "schema": "agentos.execution-authority/v1",
        "projects": {
            "zeus-writer": {
                "repository": "alston-personal/zeus-writer",
                "request_path": ".agentos/execution-requests/draft-review.json",
                "allowed_source_refs": ["master"],
                "request_source": {
                    "repo_root": str(cache),
                    "source_ref": "master",
                    "cache_ref": "refs/agentos/master",
                },
            }
        },
        "capabilities": {
            "zeus.writer.draft.review": {
                "project_id": "zeus-writer",
                "environment": "writing",
                "adapter": "zeus_draft_review",
                "parameter_policy": {
                    "chapter": {"type": "string", "pattern": "^Ch[0-9]{2}$"},
                    "work_intent_state_key": {"type": "string", "enum": ["current-work"]},
                    "work_intent_revision": {"type": "integer", "minimum": 1},
                    "work_intent_digest": {"type": "sha256"},
                },
                "replay_policy": "idempotent",
                "runtime": {
                    "repo_root": str(cache),
                    "work_intent_path": ".agentos/work-intents/current.json",
                    "allowed_draft_prefix": "scratch/",
                },
            }
        },
    }
    registry_path = tmp_path / "execution-authority.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return work_ref, request, registry, registry_path


def test_bound_zeus_review_returns_sanitized_exact_source_receipt(tmp_path: Path) -> None:
    work_ref, request, _, registry_path = _fixture(tmp_path)
    receipt = execute_bound_work_intent(work_ref, authority_path=registry_path)
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["result_status"] == "success"
    assert receipt["source_sha"] == request["source_sha"]
    evidence = receipt["evidence"]
    assert evidence["chapter"] == "Ch05"
    assert evidence["substantial_existing_draft"] is True
    assert evidence["heading_matches_chapter"] is True
    assert evidence["mutation_performed"] is False
    assert evidence["publish_performed"] is False
    assert evidence["credential_exposed"] is False
    assert "draft_sha256" in evidence
    serialized = json.dumps(receipt, sort_keys=True).casefold()
    assert "authorization" not in serialized
    assert "github_pat_" not in serialized



def test_product_work_intent_ref_is_resolved_from_exact_release_cache(tmp_path: Path) -> None:
    work_ref, _, _, registry_path = _fixture(tmp_path)
    assert resolve_product_work_intent_ref("zeus-writer", authority_path=registry_path) == work_ref


def test_work_ref_mismatch_fails_closed(tmp_path: Path) -> None:
    work_ref, _, _, registry_path = _fixture(tmp_path)
    wrong = dict(work_ref)
    wrong["digest"] = "sha256:" + "f" * 64
    receipt = execute_bound_work_intent(wrong, authority_path=registry_path)
    assert receipt["result_status"] == "failed"
    assert receipt["error_code"] == "zeus_review_work_ref_mismatch"
    assert receipt["credential_exposed"] is False


def test_parameter_widening_and_command_tunneling_are_rejected(tmp_path: Path) -> None:
    _, request, registry, _ = _fixture(tmp_path)
    widened = json.loads(json.dumps(request))
    widened["parameters"]["chapter"] = "../../etc/passwd"
    with pytest.raises(RuntimeError, match="governed_execution_parameter_chapter_pattern"):
        resolve_authority(widened, registry)

    tunneled = dict(request)
    tunneled["command"] = "publish"
    with pytest.raises(RuntimeError, match="governed_execution_request_keys_mismatch"):
        resolve_authority(tunneled, registry)
