"""Tests for agent_core.dual_agent_gate (DUAL-01)."""

from __future__ import annotations

import unittest

from agent_core.dual_agent_gate import (
    ConsensusVerdict,
    DualAgentConsensusGate,
    DualAgentProposal,
    DualAgentReview,
    ModelRoute,
    ReasoningIntensity,
    TaskComplexity,
    route_model_for_task,
)


class TestDualAgentConsensusGate(unittest.TestCase):
    def test_dynamic_model_and_reasoning_intensity_routing(self) -> None:
        # Trivial -> Low reasoning, fast model
        t_route = route_model_for_task(TaskComplexity.TRIVIAL, preferred_provider="gemini-web")
        self.assertEqual(t_route.reasoning_intensity, ReasoningIntensity.LOW)
        self.assertEqual(t_route.model_name, "gemini-2.0-flash")

        # Standard -> Medium reasoning
        s_route = route_model_for_task(TaskComplexity.STANDARD, preferred_provider="chatgpt-web")
        self.assertEqual(s_route.reasoning_intensity, ReasoningIntensity.MEDIUM)
        self.assertEqual(s_route.model_name, "gpt-4o-mini")

        # Complex -> High reasoning
        c_route = route_model_for_task(TaskComplexity.COMPLEX, preferred_provider="gemini-web")
        self.assertEqual(c_route.reasoning_intensity, ReasoningIntensity.HIGH)
        self.assertEqual(c_route.model_name, "gemini-2.0-pro")

        # Critical -> Deep Thought (extended reasoning e.g. o1 / Thinking)
        crit_route = route_model_for_task(TaskComplexity.CRITICAL, preferred_provider="chatgpt-web")
        self.assertEqual(crit_route.reasoning_intensity, ReasoningIntensity.DEEP_THOUGHT)
        self.assertEqual(crit_route.model_name, "o1")

    def test_dual_agent_cross_model_evaluation_and_consensus(self) -> None:
        def fake_proposer(prompt: str, route: ModelRoute) -> str:
            self.assertEqual(route.provider, "gemini-web")
            return f"Proposed solution for: {prompt} via {route.model_name}"

        def fake_reviewer(prompt: str, proposal: DualAgentProposal, route: ModelRoute) -> DualAgentReview:
            self.assertEqual(route.provider, "chatgpt-web")
            # For COMPLEX tasks, reviewer must automatically escalate to DEEP_THOUGHT
            self.assertEqual(route.reasoning_intensity, ReasoningIntensity.DEEP_THOUGHT)
            self.assertIn("Proposed solution", proposal.content)
            return DualAgentReview(
                proposal_task_id=proposal.task_id,
                reviewer_route=route,
                verdict=ConsensusVerdict.APPROVED,
                confidence=0.98,
                critique_points=["Clear structure", "Verified edge conditions"],
            )

        gate = DualAgentConsensusGate(
            primary_caller=fake_proposer,
            reviewer_caller=fake_reviewer,
        )

        proposal, review = gate.evaluate(
            task_id="TASK-REF-001",
            task_prompt="Refactor authentication session guard",
            complexity=TaskComplexity.COMPLEX,
            primary_provider="gemini-web",
            reviewer_provider="chatgpt-web",
            strict_cross_model=True,
        )

        self.assertEqual(proposal.task_id, "TASK-REF-001")
        self.assertEqual(review.verdict, ConsensusVerdict.APPROVED)
        self.assertEqual(review.confidence, 0.98)

    def test_strict_cross_model_enforcement(self) -> None:
        gate = DualAgentConsensusGate(
            primary_caller=lambda p, r: "dummy",
            reviewer_caller=lambda p, pr, r: DualAgentReview(
                proposal_task_id=pr.task_id,
                reviewer_route=r,
                verdict=ConsensusVerdict.APPROVED,
                confidence=1.0,
            ),
        )

        # Fails closed if primary and reviewer are configured to the same provider under strict mode
        with self.assertRaises(ValueError):
            gate.evaluate(
                task_id="TASK-ERR",
                task_prompt="Test",
                complexity=TaskComplexity.STANDARD,
                primary_provider="gemini-web",
                reviewer_provider="gemini-web",
                strict_cross_model=True,
            )


if __name__ == "__main__":
    unittest.main()
