import json
import tempfile
import unittest
from pathlib import Path

from agent_core.capability_gate import resolve_before_build
from agent_core.credit_ledger import CreditLedger
from runtime_core.capability_resolution import (
    CapabilityCandidate,
    ResolutionMode,
    resolve_capabilities,
)


class CapabilityResolutionContractTests(unittest.TestCase):
    @staticmethod
    def candidate(candidate_id, capabilities, *, priority=0, available=True):
        return CapabilityCandidate.from_values(
            candidate_id,
            capabilities,
            priority=priority,
            available=available,
        )

    def test_reuse_blocks_build_by_default(self):
        result = resolve_capabilities(
            ["studio.static-route.release"],
            [self.candidate("studio-release", ["studio.static-route.release"])],
            allow_build_when_missing=True,
        )
        self.assertIs(result.mode, ResolutionMode.REUSE)
        self.assertEqual(result.selected_candidate_ids, ("studio-release",))

    def test_compose_precedes_build(self):
        result = resolve_capabilities(
            ["asset.build", "studio.static-route.release"],
            [
                self.candidate("release", ["studio.static-route.release"]),
                self.candidate("builder", ["asset.build"]),
            ],
            allow_build_when_missing=True,
        )
        self.assertIs(result.mode, ResolutionMode.COMPOSE)
        self.assertEqual(set(result.selected_candidate_ids), {"builder", "release"})

    def test_force_build_with_reuse_requires_reason(self):
        denied = resolve_capabilities(
            ["tarot.render"],
            [self.candidate("renderer", ["tarot.render"])],
            force_build=True,
        )
        allowed = resolve_capabilities(
            ["tarot.render"],
            [self.candidate("renderer", ["tarot.render"])],
            force_build=True,
            override_reason="isolation boundary requires a distinct implementation",
        )
        self.assertIs(denied.mode, ResolutionMode.DENY)
        self.assertIs(allowed.mode, ResolutionMode.BUILD)
        self.assertTrue(allowed.override_reason)

    def test_missing_capability_needs_build_authority(self):
        denied = resolve_capabilities(["credits.ledger"], [])
        allowed = resolve_capabilities(
            ["credits.ledger"], [], allow_build_when_missing=True
        )
        self.assertIs(denied.mode, ResolutionMode.DENY)
        self.assertIs(allowed.mode, ResolutionMode.BUILD)

    def test_resolution_is_deterministic(self):
        candidates = [
            self.candidate("z-provider", ["x"]),
            self.candidate("a-provider", ["x"]),
        ]
        first = resolve_capabilities(["x"], candidates)
        second = resolve_capabilities(["x"], list(reversed(candidates)))
        self.assertEqual(first, second)
        self.assertEqual(first.selected_candidate_ids, ("a-provider",))


class GovernanceGateContractTests(unittest.TestCase):
    def test_existing_governed_provider_is_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "directory.json"
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "updated_at": None,
                        "entities": {
                            "service://studio.release": {
                                "id": "service://studio.release",
                                "kind": "service",
                                "state": "verified",
                                "owns": [],
                                "provides": ["capability://studio.static-route.release"],
                                "authority": {"exclusive": False},
                                "implementation": {
                                    "path": ".github/workflows/reusable-studio-static-route-release.yml"
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = resolve_before_build(
                ["studio.static-route.release"],
                path=registry,
                allow_build_when_missing=True,
            )
            self.assertIs(result.mode, ResolutionMode.REUSE)
            self.assertEqual(
                result.selected_candidate_ids, ("service://studio.release",)
            )

    def test_stale_provider_does_not_block_missing_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "directory.json"
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "updated_at": None,
                        "entities": {
                            "service://old": {
                                "id": "service://old",
                                "kind": "service",
                                "state": "stale",
                                "owns": [],
                                "provides": ["capability://x"],
                                "authority": {},
                                "implementation": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = resolve_before_build(
                ["x"], path=registry, allow_build_when_missing=True
            )
            self.assertIs(result.mode, ResolutionMode.BUILD)


class CreditLedgerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = CreditLedger(Path(self.temp_dir.name) / "credits.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_lifecycle_and_accounting(self):
        self.ledger.grant("acct", 100, "grant-1")
        reserve = self.ledger.reserve(
            "acct", 60, "reserve-1", metadata={"execution_id": "job-1"}
        )
        self.assertEqual(self.ledger.summary("acct")["available"], 40)

        self.ledger.commit(reserve["entryId"], "commit-1", 45)
        self.ledger.release(reserve["entryId"], "release-1")
        self.assertEqual(
            self.ledger.summary("acct"),
            {"accountId": "acct", "balance": 55, "reserved": 0, "available": 55},
        )

        self.ledger.refund(reserve["entryId"], "refund-1", 20)
        self.assertEqual(self.ledger.summary("acct")["balance"], 75)

    def test_idempotency_does_not_double_post(self):
        first = self.ledger.grant("acct", 100, "same-key")
        second = self.ledger.grant("acct", 100, "same-key")
        self.assertEqual(first, second)
        self.assertEqual(self.ledger.summary("acct")["balance"], 100)
        self.assertEqual(len(self.ledger.entries("acct")), 1)

    def test_idempotency_conflict_is_rejected(self):
        self.ledger.grant("acct", 100, "same-key")
        with self.assertRaisesRegex(ValueError, "idempotency key"):
            self.ledger.grant("acct", 101, "same-key")

    def test_reservation_cannot_overdraw(self):
        self.ledger.grant("acct", 50, "grant")
        self.ledger.reserve("acct", 40, "reserve")
        with self.assertRaisesRegex(ValueError, "insufficient"):
            self.ledger.reserve("acct", 11, "reserve-too-much")

    def test_commit_release_and_refund_are_bounded(self):
        self.ledger.grant("acct", 100, "grant")
        reserve = self.ledger.reserve("acct", 40, "reserve")
        self.ledger.commit(reserve["entryId"], "commit", 25)
        with self.assertRaisesRegex(ValueError, "exceeds remaining"):
            self.ledger.release(reserve["entryId"], "release-too-much", 16)
        self.ledger.refund(reserve["entryId"], "refund", 20)
        with self.assertRaisesRegex(ValueError, "exceeds committed"):
            self.ledger.refund(reserve["entryId"], "refund-too-much", 6)

    def test_amounts_are_positive_integers(self):
        for invalid in (0, -1, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    self.ledger.grant("acct", invalid, f"invalid-{invalid}")


if __name__ == "__main__":
    unittest.main()
