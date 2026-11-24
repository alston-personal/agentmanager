"""Dual-Agent Consensus Gate & Dynamic Model/Reasoning Router.

Implements DUAL-01:
- Dynamic Model & Reasoning Intensity Selection:
  * TaskComplexity: trivial, standard, complex, critical
  * ReasoningIntensity: low, medium, high, deep_thought
  * ProviderModelMap: dynamically routes tasks to the appropriate model variant
    (e.g., GPT-4o / GPT-o1 / GPT-o3-mini vs Gemini 1.5 Flash / Gemini Pro / Gemini Thinking).
- Cross-Model Dual-Agent Review (Consensus Gate):
  * Primary Agent (Proposer): Generates code/text/decision proposal.
  * Adversarial Agent (Reviewer): Conducts independent cross-model review.
  * Consensus Verdict: APPROVED, REVISION_REQUIRED, REJECTED.
- Fail-closed evaluation: high/critical tasks require dual cross-model sign-off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"          # Typo fixes, simple formatting
    STANDARD = "standard"        # Routine feature work, docs
    COMPLEX = "complex"          # Cross-module refactor, system architecture
    CRITICAL = "critical"        # Security boundary, governance, root consensus


class ReasoningIntensity(str, Enum):
    LOW = "low"                  # Direct response, high speed
    MEDIUM = "medium"            # Step-by-step reasoning
    HIGH = "high"                # Multi-angle verification
    DEEP_THOUGHT = "deep_thought" # Extended Chain-of-Thought (e.g. o1/o3 / Gemini Thinking)


class ConsensusVerdict(str, Enum):
    APPROVED = "APPROVED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ModelRoute:
    provider: str                # "gemini-web" | "chatgpt-web" | "antigravity"
    model_name: str              # e.g., "gemini-2.0-flash", "gemini-2.0-thinking", "gpt-4o", "o1"
    reasoning_intensity: ReasoningIntensity
    timeout_seconds: int = 60


def route_model_for_task(
    complexity: TaskComplexity,
    *,
    preferred_provider: str = "gemini-web",
    requires_extended_thinking: bool = False,
) -> ModelRoute:
    """Dynamically route task to optimal model and reasoning intensity based on complexity."""
    if complexity == TaskComplexity.CRITICAL or requires_extended_thinking:
        intensity = ReasoningIntensity.DEEP_THOUGHT
        model_name = "gemini-2.0-flash-thinking" if preferred_provider == "gemini-web" else "o1"
        timeout = 180
    elif complexity == TaskComplexity.COMPLEX:
        intensity = ReasoningIntensity.HIGH
        model_name = "gemini-2.0-pro" if preferred_provider == "gemini-web" else "gpt-4o"
        timeout = 90
    elif complexity == TaskComplexity.STANDARD:
        intensity = ReasoningIntensity.MEDIUM
        model_name = "gemini-2.0-flash" if preferred_provider == "gemini-web" else "gpt-4o-mini"
        timeout = 45
    else:  # TRIVIAL
        intensity = ReasoningIntensity.LOW
        model_name = "gemini-2.0-flash" if preferred_provider == "gemini-web" else "gpt-4o-mini"
        timeout = 25

    return ModelRoute(
        provider=preferred_provider,
        model_name=model_name,
        reasoning_intensity=intensity,
        timeout_seconds=timeout,
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
    confidence: float            # 0.0 to 1.0
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
    ) -> None:
        self.primary_caller = primary_caller
        self.reviewer_caller = reviewer_caller

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
        """Execute dual-agent generation and adversarial review with dynamic model routing."""
        if strict_cross_model and primary_provider == reviewer_provider:
            raise ValueError("strict_cross_model requires different primary and reviewer providers.")

        # 1. Route Primary Proposer
        primary_route = route_model_for_task(complexity, preferred_provider=primary_provider)
        proposal_content = self.primary_caller(task_prompt, primary_route)
        proposal = DualAgentProposal(
            task_id=task_id,
            complexity=complexity,
            content=proposal_content,
            primary_route=primary_route,
        )

        # 2. Route Adversarial Reviewer (Complexity escalates reviewer reasoning for Critical/Complex tasks)
        reviewer_complexity = TaskComplexity.CRITICAL if complexity == TaskComplexity.CRITICAL else complexity
        reviewer_route = route_model_for_task(
            reviewer_complexity,
            preferred_provider=reviewer_provider,
            requires_extended_thinking=(complexity in {TaskComplexity.COMPLEX, TaskComplexity.CRITICAL}),
        )

        review = self.reviewer_caller(task_prompt, proposal, reviewer_route)
        return proposal, review
