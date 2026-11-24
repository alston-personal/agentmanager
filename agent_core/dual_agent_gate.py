"""Dual-Agent Consensus Gate with Dynamic Model Catalog (DUAL-01).

Design Principles:
- Zero Hardcoded Model Labels: Models and reasoning intensities are dynamically
  loaded from an external catalog ($AGENT_DATA_ROOT/knowledge/model_catalog.json)
  or injected at runtime via ModelCatalogRegistry.
- Live Alignment: Fully aligned with live UI menus (e.g. GPT-6.2, GPT-6, GPT-5.6 Sol,
  Gemini Thinking, Pro, Fast, 自動).
- Strict Cross-Model Consensus Gate: Proposer and Adversarial Reviewer must evaluate
  across distinct providers to eliminate single-model confirmation bias.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"
    STANDARD = "standard"
    COMPLEX = "complex"
    CRITICAL = "critical"


class ReasoningIntensity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DEEP_THOUGHT = "deep_thought"


class ConsensusVerdict(str, Enum):
    APPROVED = "APPROVED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model_name: str
    reasoning_intensity: ReasoningIntensity
    timeout_seconds: int = 60


class ModelCatalogRegistry:
    """Dynamically resolves model routes from JSON catalog or runtime configuration."""

    def __init__(self, catalog_path: Path | None = None, *, data: dict[str, Any] | None = None) -> None:
        self.catalog_path = Path(catalog_path).resolve() if catalog_path else None
        self._data = dict(data or {})

    def _load_data(self) -> dict[str, Any]:
        if self._data:
            return self._data
        if self.catalog_path and self.catalog_path.is_file():
            try:
                return json.loads(self.catalog_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def get_route(
        self,
        provider: str,
        complexity: TaskComplexity,
        *,
        fallback_model: str = "default",
    ) -> ModelRoute:
        """Dynamically resolve model_id and reasoning intensity for provider & complexity."""
        data = self._load_data()
        prov_data = (data.get("providers") or {}).get(provider, {})
        models = prov_data.get("models") or {}
        entry = models.get(complexity.value)

        if not entry and complexity in {TaskComplexity.COMPLEX, TaskComplexity.CRITICAL}:
            # Fallback to critical or standard if specific tier is omitted
            entry = models.get("critical") or models.get("standard")

        if entry:
            intensity_str = str(entry.get("reasoning_intensity") or "medium").lower()
            try:
                intensity = ReasoningIntensity(intensity_str)
            except ValueError:
                intensity = ReasoningIntensity.MEDIUM
            return ModelRoute(
                provider=provider,
                model_name=str(entry.get("model_id") or fallback_model),
                reasoning_intensity=intensity,
                timeout_seconds=int(entry.get("timeout_seconds") or 60),
            )

        # Graceful dynamic default if provider not in catalog
        intensity_map = {
            TaskComplexity.TRIVIAL: ReasoningIntensity.LOW,
            TaskComplexity.STANDARD: ReasoningIntensity.MEDIUM,
            TaskComplexity.COMPLEX: ReasoningIntensity.HIGH,
            TaskComplexity.CRITICAL: ReasoningIntensity.DEEP_THOUGHT,
        }
        return ModelRoute(
            provider=provider,
            model_name=fallback_model,
            reasoning_intensity=intensity_map[complexity],
            timeout_seconds=60,
        )


@dataclass(frozen=True)
class DualAgentProposal:
    task_id: str
    complexity: TaskComplexity
    content: str
    primary_route: ModelRoute
    proposer_notes: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class DualAgentReview:
    proposal_task_id: str
    reviewer_route: ModelRoute
    verdict: ConsensusVerdict
    confidence: float
    critique_points: list[str] = field(default_factory=list)
    suggested_edits: str = ""
    reviewed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


class DualAgentConsensusGate:
    """Orchestrates cross-model dual-agent collaboration and consensus gating."""

    def __init__(
        self,
        *,
        primary_caller: Callable[[str, ModelRoute], str],
        reviewer_caller: Callable[[str, DualAgentProposal, ModelRoute], DualAgentReview],
        catalog_registry: ModelCatalogRegistry | None = None,
    ) -> None:
        self.primary_caller = primary_caller
        self.reviewer_caller = reviewer_caller
        self.catalog_registry = catalog_registry or ModelCatalogRegistry(
            Path("/home/ubuntu/agent-data/knowledge/model_catalog.json")
        )

    def evaluate(
        self,
        task_id: str,
        task_prompt: str,
        complexity: TaskComplexity,
        *,
        primary_provider: str = "gemini-web",
        reviewer_provider: str = "chatgpt-web",
        strict_cross_model: bool = True,
    ) -> tuple[DualAgentProposal, DualAgentReview]:
        """Execute dual-agent generation and adversarial review with dynamic model loading."""
        if strict_cross_model and primary_provider == reviewer_provider:
            raise ValueError("strict_cross_model requires different primary and reviewer providers.")

        # 1. Dynamically route Primary Proposer
        primary_route = self.catalog_registry.get_route(primary_provider, complexity)
        proposal_content = self.primary_caller(task_prompt, primary_route)
        proposal = DualAgentProposal(
            task_id=task_id,
            complexity=complexity,
            content=proposal_content,
            primary_route=primary_route,
        )

        # 2. Dynamically route Adversarial Reviewer (escalate to critical tier for complex/critical tasks)
        reviewer_complexity = TaskComplexity.CRITICAL if complexity in {TaskComplexity.COMPLEX, TaskComplexity.CRITICAL} else complexity
        reviewer_route = self.catalog_registry.get_route(reviewer_provider, reviewer_complexity)

        review = self.reviewer_caller(task_prompt, proposal, reviewer_route)
        return proposal, review
