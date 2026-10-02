import tempfile
import unittest
from pathlib import Path

from agent_core.participant_registry import ParticipantRegistry


def manifest(*, include_shutdown: bool = False):
    methods = {}
    for name in ("describe", "probe", "invoke", "status", "receipt"):
        methods[name] = {"implemented": True, "available": True, "verified": False}
    if include_shutdown:
        methods["shutdown"] = {"implemented": True, "available": True, "verified": False}
    return {
        "participant": {
            "id": "participant://agent/gemini-web",
            "instance_id": "gemini-web-session-test",
            "roles": ["agent", "model_provider"],
        },
        "adapter": {"name": "agentos-hosted-participant-adapter", "version": "0.1.0"},
        "protocol": {"name": "agentos-participant", "supported": ["1.0"], "negotiated": None},
        "methods": methods,
        "capabilities": {
            "llm.reason": {
                "supported_versions": ["v1"],
                "available": True,
                "verified": False,
            }
        },
        "features": {},
        "requirements": [],
        "relationships": [
            {
                "type": "hosted_by",
                "participant_id": "participant://host/browser-bridge",
            }
        ],
        "health": {"observable": True, "state": "available", "last_probe_at": None},
        "receipt": {"supported": True},
    }


class ParticipantRegistryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.registry = ParticipantRegistry(Path(self.td.name) / "participants.json")

    def tearDown(self):
        self.td.cleanup()

    def test_hosted_participant_request_negotiates_v1(self):
        result = self.registry.request_join(
            manifest=manifest(),
            host_runtime_id="participant://host/browser-bridge",
        )
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["negotiated_protocol"], "1.0")
        self.assertTrue(result["challenge"])
        self.assertTrue(result["claim_secret"])

    def test_claim_remains_pending_before_approval(self):
        req = self.registry.request_join(
            manifest=manifest(),
            host_runtime_id="participant://host/browser-bridge",
        )
        result = self.registry.claim_join(
            request_id=req["request_id"],
            claim_secret=req["claim_secret"],
        )
        self.assertEqual(result["status"], "pending")

    def test_approved_claim_reaches_a3_and_preserves_missing_shutdown(self):
        req = self.registry.request_join(
            manifest=manifest(),
            host_runtime_id="participant://host/browser-bridge",
        )
        self.registry.approve_join(req["user_code"])
        result = self.registry.claim_join(
            request_id=req["request_id"],
            claim_secret=req["claim_secret"],
        )
        self.assertEqual(result["status"], "enrolled")
        self.assertEqual(result["negotiated_protocol"], "1.0")
        self.assertEqual(result["acceptance_level"], "A3")
        self.assertIn("shutdown", result["missing_required_methods"])

    def test_full_method_manifest_still_requires_conformance_after_a3(self):
        req = self.registry.request_join(
            manifest=manifest(include_shutdown=True),
            host_runtime_id="participant://host/browser-bridge",
        )
        self.registry.approve_join(req["request_id"])
        result = self.registry.claim_join(
            request_id=req["request_id"],
            claim_secret=req["claim_secret"],
        )
        self.assertEqual(result["acceptance_level"], "A3")
        self.assertEqual(result["missing_required_methods"], [])
        record = self.registry.describe(
            result["participant_id"],
            result["participant_token"],
        )
        self.assertEqual(record["core_conformance"], "pending")
        self.assertEqual(record["capability_conformance"], "pending")

    def test_no_common_protocol_is_explicit(self):
        m = manifest()
        m["protocol"]["supported"] = ["9.9"]
        with self.assertRaisesRegex(ValueError, "NO_COMMON_PROTOCOL_VERSION"):
            self.registry.request_join(
                manifest=m,
                host_runtime_id="participant://host/browser-bridge",
            )


if __name__ == "__main__":
    unittest.main()
