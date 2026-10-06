import tempfile
import time
import unittest
from unittest.mock import patch
from io import BytesIO
from pathlib import Path

from PIL import Image

from services.invoice_intake.invoice_core import Extraction, InvoiceStore, deep_fallback_enrich, processing_is_stale


def jpeg_bytes() -> bytes:
    image = Image.new("RGB", (32, 24), "white")
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


class InvoiceProcessingStateTests(unittest.TestCase):
    def test_processing_stale_only_after_threshold(self):
        self.assertFalse(processing_is_stale("extracted", "2020-01-01T00:00:00Z"))
        self.assertFalse(processing_is_stale("processing", None))
        self.assertTrue(processing_is_stale("processing", "2020-01-01T00:00:00Z"))


class InvoiceIntakeDbBoundaryTests(unittest.TestCase):
    def test_batch_source_and_scope_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            payload = store.ingest(
                jpeg_bytes(),
                "scan-01.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-test-1",
            )
            self.assertEqual(payload["batch_id"], "batch-test-1")
            self.assertEqual(payload["source_type"], "upload")
            self.assertEqual(payload["data_scope"], "test")

            with store.connect() as db:
                batch = db.execute(
                    "SELECT * FROM intake_batches WHERE id=?",
                    ("batch-test-1",),
                ).fetchone()
                self.assertEqual(batch["source_type"], "upload")
                self.assertEqual(batch["data_scope"], "test")
                self.assertEqual(batch["item_count"], 1)

                document = db.execute(
                    "SELECT * FROM documents WHERE id=?",
                    (payload["document_id"],),
                ).fetchone()
                self.assertEqual(document["batch_id"], "batch-test-1")
                self.assertEqual(document["source_type"], "upload")
                self.assertEqual(document["data_scope"], "test")

    def test_rescan_restores_soft_deleted_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            image = jpeg_bytes()
            first = store.ingest(
                image,
                "same.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-a",
            )
            invoice_id = first["invoice_id"]
            store.soft_delete(invoice_id, "tester")

            second = store.ingest(
                image,
                "same.jpg",
                "image/jpeg",
                source_type="camera",
                batch_id="batch-b",
            )

            self.assertEqual(second["invoice_id"], invoice_id)
            self.assertFalse(second["duplicate"])
            self.assertTrue(second["restored"])
            self.assertEqual(second["status"], "processing")
            self.assertEqual(second["batch_id"], "batch-b")
            self.assertEqual(second["source_type"], "camera")
            self.assertEqual(store.get_invoice(invoice_id)["invoice_id"], invoice_id)

    def test_hard_delete_removes_sha_and_allows_fresh_rescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            image = jpeg_bytes()
            first = store.ingest(
                image,
                "delete-me.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-delete-a",
            )
            first_id = first["invoice_id"]
            original = store.get_original(first_id)["path"]
            self.assertTrue(Path(original).exists())

            deleted = store.hard_delete(first_id, "tester")
            self.assertTrue(deleted["permanent"])
            self.assertFalse(Path(original).exists())
            with self.assertRaises(KeyError):
                store.get_invoice(first_id)

            second = store.ingest(
                image,
                "delete-me.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-delete-b",
            )
            self.assertFalse(second["duplicate"])
            self.assertNotEqual(second["invoice_id"], first_id)

    def test_recent_and_get_invoice_expose_review_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            image = jpeg_bytes()
            created = store.ingest(
                image,
                "review-guidance.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-review-guidance",
            )
            invoice_id = created["invoice_id"]
            document_id = created["document_id"]
            payload = {
                "engine": "test-engine",
                "review": {
                    "status": "quick_confirm",
                    "required_fields": [],
                    "confirm_fields": ["vendor_name"],
                    "reasons": ["confirm:vendor_name"],
                },
            }
            with store.connect() as db:
                db.execute(
                    "INSERT INTO extractions VALUES(?,?,?,?,?)",
                    ("ex-review", document_id, "test-engine", __import__("json").dumps(payload), "2026-10-05T00:00:00Z"),
                )
                db.execute(
                    """UPDATE invoices SET
                         invoice_number='AB12345678',
                         invoice_date='2026-10-05',
                         vendor_name='測試公司',
                         seller_tax_id='16908319',
                         amount_before_tax=1000,
                         tax_amount=50,
                         total_amount=1050,
                         status='quick_confirm'
                       WHERE id=?""",
                    (invoice_id,),
                )

            one = store.get_invoice(invoice_id)
            self.assertEqual(one["review"]["status"], "quick_confirm")
            self.assertEqual(one["review"]["confirm_fields"], ["vendor_name"])

            recent = store.recent(10)
            found = next(item for item in recent if item["invoice_id"] == invoice_id)
            self.assertEqual(found["review"]["confirm_fields"], ["vendor_name"])

    def test_processing_payload_exposes_stale_recovery_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "processing.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-processing",
            )
            with store.connect() as db:
                db.execute(
                    "UPDATE invoices SET updated_at='2020-01-01T00:00:00Z' WHERE id=?",
                    (created["invoice_id"],),
                )
            item = store.get_invoice(created["invoice_id"])
            self.assertEqual(item["status"], "processing")
            self.assertTrue(item["processing_stale"])

    def test_stale_processing_ids_and_recovery_use_original_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "stale-recover.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-stale-recover",
            )
            invoice_id = created["invoice_id"]
            with store.connect() as db:
                db.execute(
                    "UPDATE invoices SET updated_at='2020-01-01T00:00:00Z' WHERE id=?",
                    (invoice_id,),
                )
            self.assertIn(invoice_id, store.stale_processing_ids())
            with patch.object(store, "process", return_value={"status": "extracted"}) as process:
                result = store.recover_stale_processing()
            process.assert_called_once_with(invoice_id)
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["recovered"], [invoice_id])
            self.assertEqual(result["failed"], [])

    def test_fast_result_returns_before_background_deep_fallback_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "two-stage.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-two-stage",
            )
            fast = Extraction(
                fields={
                    "invoice_number": None,
                    "invoice_date": None,
                    "vendor_name": None,
                    "seller_tax_id": None,
                    "amount_before_tax": None,
                    "tax_amount": None,
                    "total_amount": 1050,
                },
                confidence={"total_amount": 0.92},
                raw={
                    "engine": "fast-test",
                    "review": {
                        "status": "recognition_insufficient",
                        "required_fields": ["invoice_number"],
                        "confirm_fields": [],
                        "reasons": ["recognition:insufficient_fields"],
                    },
                    "line_items": [],
                },
                review_required=True,
            )

            def slow_deep(_invoice_id):
                time.sleep(0.4)

            started = time.perf_counter()
            with patch("services.invoice_intake.invoice_core.extract_legacy_invoice", return_value=fast), \
                 patch.object(store, "_deep_enrich_invoice", side_effect=slow_deep):
                result = store.process(created["invoice_id"])
            elapsed = time.perf_counter() - started

            self.assertLess(elapsed, 0.25)
            self.assertEqual(result["status"], "recognition_insufficient")
            self.assertFalse(result["deep_fallback_pending"])
            self.assertTrue(result["background_enrichment_pending"])


    def test_process_returns_terminal_fast_result_before_background_vision(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "vision-background.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-vision-background",
            )
            local = Extraction(
                fields={
                    "invoice_number": "EC55544057",
                    "invoice_date": None,
                    "vendor_name": "榮昌企業有限公司",
                    "buyer_tax_id": None,
                    "seller_tax_id": "16672215",
                    "amount_before_tax": None,
                    "tax_amount": None,
                    "total_amount": None,
                },
                confidence={
                    "invoice_number": 0.99,
                    "vendor_name": 0.95,
                    "seller_tax_id": 0.95,
                },
                raw={
                    "engine": "local-fast",
                    "review": {
                        "status": "needs_review",
                        "required_fields": ["invoice_date", "total_amount"],
                        "confirm_fields": [],
                        "reasons": ["missing:invoice_date", "missing:total_amount"],
                    },
                    "line_items": [],
                },
                review_required=True,
            )
            with patch.dict(
                __import__("os").environ,
                {
                    "INVOICE_VISION_MODE": "primary",
                    "GEMINI_INVOICE_MODEL": "test-model",
                    "GEMINI_API_KEY": "test-key",
                },
            ), patch(
                "services.invoice_intake.invoice_core.extract_legacy_invoice",
                return_value=local,
            ), patch("services.invoice_intake.invoice_core.threading.Thread") as thread_cls:
                result = store.process(created["invoice_id"])

            self.assertNotEqual(result["status"], "processing")
            self.assertEqual(result["status"], "needs_review")
            self.assertTrue(result["background_enrichment_pending"])
            self.assertTrue(result["vision_enrichment_pending"])
            target = thread_cls.call_args.kwargs["target"]
            self.assertEqual(target, store._vision_enrich_invoice)

    def test_prepare_reprocess_returns_immediately_in_processing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "queued-reprocess.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-reprocess",
            )
            queued = store.prepare_reprocess(created["invoice_id"])
            self.assertEqual(queued["status"], "processing")
            self.assertEqual(queued["invoice_id"], created["invoice_id"])

    def test_deep_fallback_only_fills_missing_fields(self):
        image = Image.new("RGB", (700, 1000), "white")
        buf = BytesIO()
        image.save(buf, format="JPEG")
        base = Extraction(
            fields={
                "invoice_number": "AB12345678",
                "invoice_date": "2026-10-05",
                "vendor_name": None,
                "seller_tax_id": None,
                "amount_before_tax": 1000,
                "tax_amount": 50,
                "total_amount": 1050,
            },
            confidence={
                "invoice_number": 0.99,
                "invoice_date": 0.99,
                "amount_before_tax": 0.99,
                "tax_amount": 0.99,
                "total_amount": 0.99,
            },
            raw={
                "engine": "fast-test",
                "template": {
                    "matched": True,
                    "document_type": "three_part_uniform_invoice",
                    "raw_text": "",
                    "visual_amounts": True,
                },
                "stamp_recognition": {"status": "TIMEOUT"},
                "review": {"status": "needs_review"},
            },
            review_required=True,
        )

        def fake_ocr(_crop, *, psm, whitelist=None, lang="eng", timeout_seconds=None):
            if whitelist == "0123456789":
                return "16908319"
            return "測試企業有限公司"

        with patch("services.invoice_intake.invoice_core.ocr_image", side_effect=fake_ocr), \
             patch("services.invoice_intake.invoice_core.ocr_stamp_text", return_value=["16908319", "測試企業有限公司"]) as stamp_ocr:
            result = deep_fallback_enrich(buf.getvalue(), base, budget_seconds=5)

        self.assertEqual(result.fields["invoice_number"], "AB12345678")
        self.assertEqual(result.fields["total_amount"], 1050)
        self.assertEqual(result.fields["seller_tax_id"], "16908319")
        self.assertEqual(result.fields["vendor_name"], "測試企業有限公司")
        self.assertFalse(result.raw["deep_fallback"].get("stamp_dependency", False))
        self.assertTrue(any(call.kwargs.get("fast") is False for call in stamp_ocr.call_args_list))
        self.assertTrue(any((call.kwargs.get("timeout_seconds") or 0) >= 10 for call in stamp_ocr.call_args_list))

    def test_deep_fallback_error_clears_pending_without_destroying_fast_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "deep-error.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-deep-error",
            )
            invoice_id = created["invoice_id"]
            document_id = created["document_id"]
            fast_raw = {
                "engine": "fast-test",
                "deep_fallback_pending": True,
                "review": {
                    "status": "needs_review",
                    "required_fields": ["vendor_name"],
                    "confirm_fields": [],
                    "reasons": ["missing:vendor_name"],
                },
            }
            with store.connect() as db:
                db.execute(
                    "INSERT INTO extractions VALUES(?,?,?,?,?)",
                    (
                        "fast-extraction",
                        document_id,
                        "fast-test",
                        __import__("json").dumps(fast_raw),
                        "2026-10-06T00:00:00Z",
                    ),
                )
                db.execute(
                    """UPDATE invoices SET
                         invoice_number='AB12345678',
                         invoice_date='2026-10-06',
                         vendor_name=NULL,
                         seller_tax_id='16908319',
                         amount_before_tax=1000,
                         tax_amount=50,
                         total_amount=1050,
                         status='needs_review',
                         confidence_json='{"invoice_number":0.99,"total_amount":0.99}'
                       WHERE id=?""",
                    (invoice_id,),
                )

            with patch(
                "services.invoice_intake.invoice_core.deep_fallback_enrich",
                side_effect=RuntimeError("synthetic deep failure"),
            ):
                store._deep_enrich_invoice(invoice_id)

            item = store.get_invoice(invoice_id)
            self.assertEqual(item["status"], "needs_review")
            self.assertFalse(item["deep_fallback_pending"])
            self.assertEqual(item["fields"]["invoice_number"], "AB12345678")
            self.assertEqual(item["fields"]["total_amount"], 1050)
            self.assertEqual(
                (item.get("recognition") or {}).get("deep_fallback", {}).get("status"),
                "error",
            )


    def test_process_error_persists_terminal_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            created = store.ingest(
                jpeg_bytes(),
                "error.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-error",
            )
            with patch(
                "services.invoice_intake.invoice_core.extract_legacy_invoice",
                side_effect=RuntimeError("synthetic provider/parser failure"),
            ):
                with self.assertRaises(RuntimeError):
                    store.process(created["invoice_id"])

            item = store.get_invoice(created["invoice_id"])
            self.assertEqual(item["status"], "error")
            recognition = item.get("recognition") or {}
            self.assertEqual(recognition.get("status"), "error")
            self.assertEqual((recognition.get("error") or {}).get("stage"), "process")
            self.assertEqual((recognition.get("error") or {}).get("type"), "RuntimeError")
            self.assertFalse(item["background_enrichment_pending"])

    def test_existing_schema_migrates_without_dropping_invoice_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            import sqlite3
            db_path = root / "invoice-intake.sqlite3"
            db = sqlite3.connect(db_path)
            db.executescript("""
              CREATE TABLE documents(
                id TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE,
                original_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                stored_path TEXT NOT NULL,
                created_at TEXT NOT NULL
              );
              CREATE TABLE extractions(
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id),
                engine TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
              );
              CREATE TABLE invoices(
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
                invoice_number TEXT,
                invoice_date TEXT,
                vendor_name TEXT,
                seller_tax_id TEXT,
                amount_before_tax INTEGER,
                tax_amount INTEGER,
                total_amount INTEGER,
                status TEXT NOT NULL,
                confidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
              );
              CREATE TABLE reviews(
                id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL REFERENCES invoices(id),
                actor TEXT NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                created_at TEXT NOT NULL
              );
            """)
            db.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                ("legacy-doc", "legacy-sha", "legacy.jpg", "image/jpeg", 4, "/tmp/legacy.jpg", "2026-01-01T00:00:00Z"),
            )
            db.commit()
            db.close()

            store = InvoiceStore(root, data_scope="production")
            with store.connect() as db:
                tables = {
                    row["name"]
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertTrue(
                    {"intake_batches", "documents", "invoices", "extractions", "reviews"}
                    <= tables
                )
                columns = {
                    row["name"] for row in db.execute("PRAGMA table_info(documents)")
                }
                self.assertTrue({"batch_id", "source_type", "data_scope"} <= columns)
                legacy = db.execute("SELECT * FROM documents WHERE id='legacy-doc'").fetchone()
                self.assertEqual(legacy["source_type"], "unknown")
                self.assertEqual(legacy["data_scope"], "production")


if __name__ == "__main__":
    unittest.main()
