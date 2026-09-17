from __future__ import annotations

import unittest

from agent_core.discovery_reuse import (
    DiscoveryRequirement,
    KnownFact,
    assess_requirement,
    build_discovery_receipt,
    sanitize_for_persistence,
)


class TestDiscoveryReuse(unittest.TestCase):
    def req(self, **overrides):
        base = {
            "fact_key": "project.repo",
            "scope": "project:leopardcat-tarot",
            "depth": "structural",
            "evidence_strength": "verified",
        }
        base.update(overrides)
        return DiscoveryRequirement(**base)

    def known(self, **overrides):
        base = {
            "fact_key": "project.repo",
            "value": "alston-personal/leopardcat-tarot",
            "scope": "project:leopardcat-tarot",
            "depth": "structural",
            "evidence_strength": "verified",
            "freshness": "fresh",
        }
        base.update(overrides)
        return KnownFact(**base)

    def test_equivalent_verified_fact_is_reused(self):
        result = assess_requirement(self.req(), self.known())
        self.assertTrue(result["reusable"])
        self.assertEqual(result["decision"], "reuse")
        self.assertEqual(result["rediscovery_reasons"], [])

    def test_missing_fact_requires_rediscovery(self):
        result = assess_requirement(self.req(), None)
        self.assertEqual(result["rediscovery_reasons"], ["missing"])

    def test_stale_fact_allows_targeted_revalidation(self):
        result = assess_requirement(self.req(), self.known(freshness="stale"))
        self.assertEqual(result["rediscovery_reasons"], ["stale"])

    def test_greater_depth_is_explicit(self):
        result = assess_requirement(
            self.req(depth="runtime"),
            self.known(depth="structural"),
        )
        self.assertEqual(result["rediscovery_reasons"], ["deeper"])

    def test_expanded_scope_is_explicit(self):
        result = assess_requirement(
            self.req(scope="environment:staging"),
            self.known(scope="environment:production"),
        )
        self.assertEqual(result["rediscovery_reasons"], ["expanded_scope"])

    def test_conflict_requires_reconciliation(self):
        result = assess_requirement(self.req(), self.known(conflicting=True))
        self.assertEqual(result["rediscovery_reasons"], ["conflict"])

    def test_stronger_evidence_is_explicit(self):
        result = assess_requirement(
            self.req(evidence_strength="receipt"),
            self.known(evidence_strength="documented"),
        )
        self.assertEqual(result["rediscovery_reasons"], ["stronger_evidence"])

    def test_credential_bearing_remote_is_sanitized(self):
        sanitized = sanitize_for_persistence(
            {
                "remote": "https://user:example-token@github.com/example/repo.git",
                "token": "example-token",
                "nested": ["https://oauth2:another-token@git.example.test/team/repo.git"],
            }
        )
        self.assertEqual(sanitized["remote"], "https://github.com/example/repo.git")
        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["nested"][0], "https://git.example.test/team/repo.git")

    def test_receipt_records_reuse_and_machine_readable_reasons(self):
        reused = assess_requirement(self.req(), self.known())
        stale = assess_requirement(
            self.req(fact_key="runtime.service"),
            self.known(fact_key="runtime.service", value="leopardcat-tarot.service", freshness="stale"),
        )
        receipt = build_discovery_receipt([reused, stale], project_id="leopardcat-tarot")
        self.assertEqual(receipt["protocol"], "agentos.discovery-receipt/v1")
        self.assertEqual(receipt["reused"], ["project.repo"])
        self.assertEqual(receipt["rediscovered"], ["runtime.service"])
        self.assertEqual(receipt["rediscovery_reasons"], ["stale"])
        self.assertTrue(receipt["performed"])


if __name__ == "__main__":
    unittest.main()
