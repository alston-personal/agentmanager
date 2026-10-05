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

    def test_existing_schema_migrates_without_dropping_invoice_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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


if __name__ == "__main__":
    unittest.main()
