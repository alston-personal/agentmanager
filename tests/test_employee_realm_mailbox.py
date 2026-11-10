from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_realm_mailbox import (
    CLAIM_SCHEMA,
    MESSAGE_SCHEMA,
    RECEIPT_SCHEMA,
    EmployeeRealmMailbox,
)
from agent_core.employee_runtime import EmployeeRuntime


T0 = datetime(2026, 9, 2, 7, 0, 0, tzinfo=timezone.utc)


class EmployeeRealmMailboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.runtime.create_employee("weaver", "Weaver")
        self.runtime.create_employee("spec-steward", "Spec Steward")
        self.runtime.create_assignment(
            "sender-a",
            "weaver",
            "Prepare bounded handoff",
            thread_head="thread:sender",
        )
        self.runtime.create_assignment(
            "recipient-a",
            "spec-steward",
            "Review handoff",
            thread_head="thread:recipient",
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.lifecycle.claim(
            "sender-a", "weaver", "lease-sender", lease_seconds=600, now=T0
        )
        self.lifecycle.claim(
            "recipient-a",
            "spec-steward",
            "lease-recipient",
            lease_seconds=600,
            now=T0,
        )
        self.mailbox = EmployeeRealmMailbox(self.lifecycle)

    def tearDown(self):
        self.tmp.cleanup()

    def _send(self, message_id="msg-1"):
        return self.mailbox.send(
            "weaver",
            "sender-a",
            "lease-sender",
            "spec-steward",
            message_id,
            kind="handoff",
            subject="Specification handoff",
            summary="Review the bounded closure finding.",
            assignment_ref="assignment:sender-a",
            thread_ref="thread:sender",
            artifact_refs=["issue:197", "spec:employee-operating-plane"],
            now=T0 + timedelta(seconds=10),
        )

    def test_send_persists_employee_addressed_message_in_one_mailbox(self):
        message = self._send()
        self.assertEqual(message.schema, MESSAGE_SCHEMA)
        self.assertEqual(message.sender_employee_id, "weaver")
        self.assertEqual(message.recipient_employee_id, "spec-steward")
        self.assertEqual(message.state, "queued")
        self.assertEqual(message.delivery_generation, 0)
        path = (
            self.root
            / "realm"
            / "employee-mailbox"
            / "messages"
            / "spec-steward"
            / "msg-1.json"
        )
        self.assertTrue(path.is_file())
        serialized = path.read_text(encoding="utf-8").casefold()
        for forbidden in (
            "node_id",
            "provider",
            "session_id",
            "github_actions",
            "workflow_dispatch",
            "executable",
            "argv",
            "authorization",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_same_message_id_and_content_is_idempotent_but_conflict_fails(self):
        first = self._send()
        second = self._send()
        self.assertEqual(first.digest, second.digest)
        with self.assertRaisesRegex(
            RuntimeError, "employee_message_idempotency_conflict"
        ):
            self.mailbox.send(
                "weaver",
                "sender-a",
                "lease-sender",
                "spec-steward",
                "msg-1",
                kind="handoff",
                subject="Changed subject",
                summary="Different body",
                now=T0 + timedelta(seconds=20),
            )

    def test_sender_must_own_live_assignment(self):
        with self.assertRaisesRegex(
            PermissionError, "sender_assignment_employee_mismatch"
        ):
            self.mailbox.send(
                "weaver",
                "recipient-a",
                "lease-recipient",
                "spec-steward",
                "msg-wrong-owner",
                kind="finding",
                subject="No",
                summary="This sender does not own the assignment.",
                now=T0 + timedelta(seconds=10),
            )
        with self.assertRaisesRegex(RuntimeError, "lease_expired"):
            self.mailbox.send(
                "weaver",
                "sender-a",
                "lease-sender",
                "spec-steward",
                "msg-expired",
                kind="finding",
                subject="Expired",
                summary="Lease is no longer current.",
                now=T0 + timedelta(seconds=601),
            )

    def test_payload_surface_is_bounded_and_rejects_urls_paths_and_secrets(self):
        unsafe = (
            {"artifact_refs": ["https://example.invalid/a"]},
            {"artifact_refs": ["/tmp/private"]},
            {"artifact_refs": ["file:../private"]},
            {"artifact_refs": ["token=TOPSECRET"]},
            {"summary": "Bearer TOPSECRET"},
        )
        for index, override in enumerate(unsafe):
            kwargs = {
                "kind": "finding",
                "subject": "Bounded",
                "summary": "Safe summary",
                "artifact_refs": ["issue:197"],
            }
            kwargs.update(override)
            with self.assertRaises(ValueError):
                self.mailbox.send(
                    "weaver",
                    "sender-a",
                    "lease-sender",
                    "spec-steward",
                    f"unsafe-{index}",
                    now=T0 + timedelta(seconds=10),
                    **kwargs,
                )

    def test_recipient_claim_requires_recipient_assignment_lease(self):
        self._send()
        with self.assertRaisesRegex(
            PermissionError, "recipient_assignment_employee_mismatch"
        ):
            self.mailbox.claim(
                "msg-1",
                "spec-steward",
                "sender-a",
                "lease-sender",
                "claim-wrong",
                now=T0 + timedelta(seconds=20),
            )
        claim = self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            now=T0 + timedelta(seconds=20),
        )
        self.assertEqual(claim.schema, CLAIM_SCHEMA)
        self.assertEqual(claim.delivery_generation, 1)
        self.assertFalse(claim.redelivery_required)
        self.assertEqual(claim.prior_delivery_state, "known")
        self.assertEqual(claim.transport, "one_resident_mailbox")
        self.assertEqual(claim.node_selection, "unbound")
        self.assertEqual(claim.executor_selection, "unbound")
        self.assertFalse(claim.credential_exposed)

    def test_live_claim_suppresses_other_claim_and_same_claim_is_idempotent(self):
        self._send()
        first = self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            now=T0 + timedelta(seconds=20),
        )
        same = self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            now=T0 + timedelta(seconds=30),
        )
        self.assertEqual(first.delivery_generation, same.delivery_generation)
        with self.assertRaisesRegex(RuntimeError, "employee_message_already_claimed"):
            self.mailbox.claim(
                "msg-1",
                "spec-steward",
                "recipient-a",
                "lease-recipient",
                "claim-2",
                now=T0 + timedelta(seconds=30),
            )

    def test_expired_claim_redelivery_marks_prior_delivery_unknown(self):
        self._send()
        self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            claim_seconds=30,
            now=T0 + timedelta(seconds=20),
        )
        claim = self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-2",
            now=T0 + timedelta(seconds=51),
        )
        self.assertEqual(claim.delivery_generation, 2)
        self.assertTrue(claim.redelivery_required)
        self.assertEqual(claim.prior_delivery_state, "unknown")

    def test_ack_receipt_is_persisted_before_terminal_message_and_idempotent(self):
        self._send()
        self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            now=T0 + timedelta(seconds=20),
        )
        receipt = self.mailbox.acknowledge(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            disposition="processed",
            now=T0 + timedelta(seconds=30),
        )
        self.assertEqual(receipt.schema, RECEIPT_SCHEMA)
        self.assertEqual(receipt.delivery_generation, 1)
        self.assertEqual(receipt.disposition, "processed")
        self.assertFalse(receipt.credential_exposed)
        self.assertEqual(self.mailbox.get("msg-1").state, "acknowledged")
        repeated = self.mailbox.acknowledge(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            disposition="processed",
            now=T0 + timedelta(seconds=40),
        )
        self.assertEqual(repeated.receipt_id, receipt.receipt_id)
        self.assertEqual(self.mailbox.pending("spec-steward"), [])

    def test_ack_requires_current_claim_and_live_employee_assignment(self):
        self._send()
        self.mailbox.claim(
            "msg-1",
            "spec-steward",
            "recipient-a",
            "lease-recipient",
            "claim-1",
            claim_seconds=30,
            now=T0 + timedelta(seconds=20),
        )
        with self.assertRaisesRegex(PermissionError, "employee_message_claim_not_owned"):
            self.mailbox.acknowledge(
                "msg-1",
                "spec-steward",
                "recipient-a",
                "lease-recipient",
                "claim-other",
                now=T0 + timedelta(seconds=25),
            )
        with self.assertRaisesRegex(RuntimeError, "employee_message_claim_expired"):
            self.mailbox.acknowledge(
                "msg-1",
                "spec-steward",
                "recipient-a",
                "lease-recipient",
                "claim-1",
                now=T0 + timedelta(seconds=51),
            )

    def test_mailbox_survives_runtime_restart_without_node_binding(self):
        self._send()
        restarted_runtime = EmployeeRuntime(self.root)
        restarted_lifecycle = EmployeeLifecycle(restarted_runtime)
        restarted = EmployeeRealmMailbox(restarted_lifecycle)
        pending = restarted.pending("spec-steward", now=T0 + timedelta(seconds=20))
        self.assertEqual([item.message_id for item in pending], ["msg-1"])
        serialized = json.dumps(
            [
                {
                    "message_id": item.message_id,
                    "sender_employee_id": item.sender_employee_id,
                    "recipient_employee_id": item.recipient_employee_id,
                }
                for item in pending
            ],
            ensure_ascii=False,
        )
        self.assertNotIn("node", serialized.casefold())
        self.assertNotIn("session", serialized.casefold())


if __name__ == "__main__":
    unittest.main()
