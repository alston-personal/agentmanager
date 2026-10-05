import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from services.invoice_intake.invoice_core import InvoiceStore


def jpeg_bytes() -> bytes:
    image = Image.new("RGB", (32, 24), "white")
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


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

    def test_legacy_complete_review_row_becomes_quick_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            image = jpeg_bytes()
            payload = store.ingest(image, "legacy-review.jpg", "image/jpeg", source_type="upload")
            invoice_id = payload["invoice_id"]
            with store.connect() as db:
                document_id = db.execute(
                    "SELECT document_id FROM invoices WHERE id=?", (invoice_id,)
                ).fetchone()["document_id"]
                db.execute(
                    """UPDATE invoices SET invoice_number=?,invoice_date=?,vendor_name=?,seller_tax_id=?,
                       amount_before_tax=?,tax_amount=?,total_amount=?,status=?,confidence_json=?
                       WHERE id=?""",
                    (
                        "AB12345678", "2026-10-05", "好日子食品有限公司", "16908319",
                        1000, 50, 1050, "needs_review",
                        '{"invoice_number":0.95,"invoice_date":0.90,"vendor_name":0.78,"seller_tax_id":0.88,"amount_before_tax":0.98,"tax_amount":0.98,"total_amount":0.98}',
                        invoice_id,
                    ),
                )
                db.execute(
                    "INSERT INTO extractions VALUES(?,?,?,?,?)",
                    (
                        "legacy-extraction", document_id, "legacy",
                        '{"engine":"legacy","template":{"matched":true,"document_type":"three_part_uniform_invoice","visual_amounts":true}}',
                        "2026-10-05T00:00:00Z",
                    ),
                )
            changed = store._reclassify_legacy_review_rows()
            self.assertEqual(changed, 1)
            self.assertEqual(store.get_invoice(invoice_id)["status"], "quick_confirm")

    def test_legacy_missing_core_field_stays_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            payload = store.ingest(jpeg_bytes(), "legacy-missing.jpg", "image/jpeg", source_type="upload")
            invoice_id = payload["invoice_id"]
            with store.connect() as db:
                document_id = db.execute(
                    "SELECT document_id FROM invoices WHERE id=?", (invoice_id,)
                ).fetchone()["document_id"]
                db.execute(
                    """UPDATE invoices SET invoice_number=NULL,invoice_date=?,vendor_name=?,seller_tax_id=?,
                       amount_before_tax=?,tax_amount=?,total_amount=?,status=?,confidence_json=?
                       WHERE id=?""",
                    (
                        "2026-10-05", "好日子食品有限公司", "16908319",
                        1000, 50, 1050, "needs_review",
                        '{"invoice_date":0.90,"vendor_name":0.78,"seller_tax_id":0.88,"amount_before_tax":0.98,"tax_amount":0.98,"total_amount":0.98}',
                        invoice_id,
                    ),
                )
                db.execute(
                    "INSERT INTO extractions VALUES(?,?,?,?,?)",
                    ("legacy-extraction-missing", document_id, "legacy", '{"engine":"legacy"}', "2026-10-05T00:00:00Z"),
                )
            changed = store._reclassify_legacy_review_rows()
            self.assertEqual(changed, 0)
            self.assertEqual(store.get_invoice(invoice_id)["status"], "needs_review")

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
