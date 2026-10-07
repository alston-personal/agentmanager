import unittest

from agentos_node.mobile_enrollment import (
    MobileEnrollmentLink,
    build_join_request_payload,
)
from agentos_node.mobile_node import MobileExecutor, build_mobile_manifest


class TestMobileEnrollment(unittest.TestCase):
    def test_join_link_round_trip(self):
        encoded = MobileEnrollmentLink("https://one.example.test").encode()
        self.assertTrue(encoded.startswith("agentos://join?"))
        decoded = MobileEnrollmentLink.parse(encoded)
        self.assertEqual(decoded.one_url, "https://one.example.test")
        self.assertEqual(decoded.version, "v1")

    def test_join_payload_reuses_existing_device_flow(self):
        manifest = build_mobile_manifest(
            node_id="iphone-alston",
            platform="ios",
            platform_release="26.6",
            presence="foreground",
            push_provider="apns",
            executors=[
                MobileExecutor("mobile.notification", ("notification.present",), "ready"),
            ],
        )
        payload = build_join_request_payload(manifest, expires_minutes=12)
        self.assertEqual(payload["manifest"]["schema"], "agentos.node-manifest/v0.1")
        self.assertEqual(payload["expires_minutes"], 12)

    def test_non_mobile_manifest_is_rejected(self):
        with self.assertRaises(ValueError):
            build_join_request_payload({
                "schema": "agentos.node-manifest/v0.1",
                "node_id": "desktop",
            })


if __name__ == "__main__":
    unittest.main()
