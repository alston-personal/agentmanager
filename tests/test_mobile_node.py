import unittest

from agentos_node.mobile_node import (
    MobileExecutor,
    build_mobile_heartbeat,
    build_mobile_manifest,
    executor_readiness,
)


class TestMobileNode(unittest.TestCase):
    def test_ios_manifest_uses_canonical_node_schema(self):
        manifest = build_mobile_manifest(
            node_id="iphone-alston",
            platform="ios",
            platform_release="26.6",
            presence="foreground",
            push_provider="apns",
            executors=[
                MobileExecutor("mobile.notification", ("notification.present",), "ready"),
                MobileExecutor("mobile.camera", ("camera.capture",), "permission_required"),
            ],
        )

        self.assertEqual(manifest["schema"], "agentos.node-manifest/v0.1")
        self.assertEqual(manifest["mobile"]["profile"], "agentos.mobile-node/v0.1")
        self.assertEqual(manifest["capabilities"], ["notification.present"])
        self.assertEqual(
            executor_readiness(manifest),
            {
                "mobile.notification": "ready",
                "mobile.camera": "permission_required",
            },
        )

    def test_mobile_heartbeat_does_not_imply_executor_ready(self):
        manifest = build_mobile_manifest(
            node_id="pixel-test",
            platform="android",
            platform_release="16",
            presence="background",
            push_provider="fcm",
            executors=[
                MobileExecutor("android.accessibility", ("desktop.semantic_preview",), "permission_required"),
            ],
        )
        heartbeat = build_mobile_heartbeat(manifest)

        self.assertEqual(heartbeat["status"], "online")
        self.assertEqual(manifest["capabilities"], [])
        self.assertEqual(executor_readiness(manifest)["android.accessibility"], "permission_required")

    def test_suspended_mobile_node_is_not_online(self):
        manifest = build_mobile_manifest(
            node_id="iphone-suspended",
            platform="ios",
            platform_release="26.6",
            presence="suspended",
            push_provider="apns",
            executors=[
                MobileExecutor("mobile.notification", ("notification.present",), "suspended"),
            ],
        )
        heartbeat = build_mobile_heartbeat(manifest)
        self.assertEqual(heartbeat["status"], "offline")

    def test_platform_push_provider_must_match(self):
        with self.assertRaises(ValueError):
            build_mobile_manifest(
                node_id="iphone-bad",
                platform="ios",
                platform_release="26.6",
                presence="foreground",
                push_provider="fcm",
                executors=[],
            )


if __name__ == "__main__":
    unittest.main()
