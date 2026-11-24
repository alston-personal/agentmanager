"""Tests for agent_core.dual_agent_gate with dynamic ModelCatalogRegistry (DUAL-01)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.dual_agent_gate import (
    ConsensusVerdict,
    DualAgentConsensusGate,
    DualAgentProposal,
    DualAgentReview,
    ModelCatalogRegistry,
    ModelRoute,
    ReasoningIntensity,
    TaskComplexity,
)


class TestDualAgentGateDynamicCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_catalog = {
            "schema": "agentos.model-catalog/v1",
            "providers": {
                "chatgpt-web": {
                    "models": {
                        "critical": {
                            "model_id": "GPT-6.2",
                            "reasoning_intensity": "deep_thought",
                        },
                        "complex": {
                            "model_id": "GPT-6",
                            "reasoning_intensity": "high",
                        },
                        "standard": {
                            "model_id": "GPT-5.6 Sol",
                            "reasoning_intensity": "medium",
                        },
                    }
                },
                "gemini-web": {
                    "models": {
                        "critical": {
                            "model_id": "Thinking",
                            "reasoning_intensity": "deep_thought",
                        },
                        "complex": {
                            "model_id": "Pro",
                            "reasoning_intensity": "high",
                        },
                        "standard": {
                            "model_id": "Fast",
                            "reasoning_intensity": "medium",
                        },
                    }
                },
            },
        }

    def test_dynamic_catalog_loading_and_routing(self) -> None:
        registry = ModelCatalogRegistry(data=self.sample_catalog)

        # Dynamic routing for ChatGPT
        route_crit = registry.get_route("chatgpt-web", TaskComplexity.CRITICAL)
        self.assertEqual(route_crit.model_name, "GPT-6.2")
        self.assertEqual(route_crit.reasoning_intensity, ReasoningIntensity.DEEP_THOUGHT)

        route_comp = registry.get_route("chatgpt-web", TaskComplexity.COMPLEX)
        self.assertEqual(route_comp.model_name, "GPT-6")
        self.assertEqual(route_comp.reasoning_intensity, ReasoningIntensity.HIGH)

        route_std = registry.get_route("chatgpt-web", TaskComplexity.STANDARD)
        self.assertEqual(route_std.model_name, "GPT-5.6 Sol")
        self.assertEqual(route_std.reasoning_intensity, ReasoningIntensity.MEDIUM)

        # Dynamic routing for Gemini
        gem_crit = registry.get_route("gemini-web", TaskComplexity.CRITICAL)
        self.assertEqual(gem_crit.model_name, "Thinking")

        gem_comp = registry.get_route("gemini-web", TaskComplexity.COMPLEX)
        self.assertEqual(gem_comp.model_name, "Pro")

        gem_std = registry.get_route("gemini-web", TaskComplexity.STANDARD)
        self.assertEqual(gem_std.model_name, "Fast")

    def test_dual_agent_evaluation_with_dynamic_registry(self) -> None:
        registry = ModelCatalogRegistry(data=self.sample_catalog)

        def fake_proposer(prompt: str, route: ModelRoute) -> str:
            self.assertEqual(route.provider, "gemini-web")
            self.assertEqual(route.model_name, "Pro")
            return f"Solution: {prompt}"

        def fake_reviewer(prompt: str, proposal: DualAgentProposal, route: ModelRoute) -> DualAgentReview:
            self.assertEqual(route.provider, "chatgpt-web")
            # For complex tasks, reviewer dynamically routes to critical tier (GPT-6.2 / deep_thought)
            self.assertEqual(route.model_name, "GPT-6.2")
            self.assertEqual(route.reasoning_intensity, ReasoningIntensity.DEEP_THOUGHT)
            return DualAgentReview(
                proposal_task_id=proposal.task_id,
                reviewer_route=route,
                verdict=ConsensusVerdict.APPROVED,
                confidence=0.99,
            )

        gate = DualAgentConsensusGate(
            primary_caller=fake_proposer,
            reviewer_caller=fake_reviewer,
            catalog_registry=registry,
        )

        proposal, review = gate.evaluate(
            task_id="TASK-DYN-01",
            task_prompt="Implement distributed transaction lock",
            complexity=TaskComplexity.COMPLEX,
            primary_provider="gemini-web",
            reviewer_provider="chatgpt-web",
            strict_cross_model=True,
        )

        self.assertEqual(proposal.primary_route.model_name, "Pro")
        self.assertEqual(review.reviewer_route.model_name, "GPT-6.2")
        self.assertEqual(review.verdict, ConsensusVerdict.APPROVED)


if __name__ == "__main__":
    unittest.main()
