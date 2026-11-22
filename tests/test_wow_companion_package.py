import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.wow_companion_package import BundleError, build_bundle


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / "source" / "ExampleAddon"
        self.src.mkdir(parents=True)
        self.toc = self.src / "ExampleAddon.toc"
        self.toc.write_text("## Interface: 16001\nExample.lua\n", encoding="utf-8")
        self.lua = self.src / "Example.lua"
        self.lua.write_text("print('test')\n", encoding="utf-8")
        self.lock = self.root / "source-lock.json"
        self.out = self.root / "bundle.zip"
        self.lock_entries = [
            {"addon": "ExampleAddon", "path": p.name,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in (self.toc, self.lua)]
        self.write_lock()

    def write_lock(self):
        self.lock.write_text(json.dumps({"schema": "agentos.wow-suite-source-lock/v1",
                                         "files": self.lock_entries}), encoding="utf-8")

    def test_build_is_deterministic_and_manifest_present(self):
        a = build_bundle(self.lock, self.root / "source", self.out)
        first = self.out.read_bytes()
        b = build_bundle(self.lock, self.root / "source", self.out)
        self.assertEqual(first, self.out.read_bytes())
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["status"], "source-verified-not-game-validated")
        with zipfile.ZipFile(self.out) as z:
            self.assertEqual(z.namelist(), sorted(z.namelist()))
            self.assertIn("ExampleAddon/ExampleAddon.toc", z.namelist())
            self.assertIn("WOW_SUITE_BUILD_MANIFEST.json", z.namelist())

    def test_refuse_digest_mismatch_without_writing(self):
        self.lua.write_text("print('changed')\n")
        with self.assertRaisesRegex(BundleError, "SHA256 mismatch"):
            build_bundle(self.lock, self.root / "source", self.out)
        self.assertFalse(self.out.exists())

    def test_refuse_traversal(self):
        self.lock_entries[1]["path"] = "../secret"
        self.write_lock()
        with self.assertRaisesRegex(BundleError, "unsafe|invalid"):
            build_bundle(self.lock, self.root / "source", self.out)

    def test_refuse_missing_toc(self):
        self.lock_entries = [self.lock_entries[1]]
        self.write_lock()
        with self.assertRaisesRegex(BundleError, "missing top-level TOC"):
            build_bundle(self.lock, self.root / "source", self.out)

    def test_refuse_toc_reference_not_in_lock(self):
        self.lock_entries = [self.lock_entries[0]]
        self.write_lock()
        with self.assertRaisesRegex(BundleError, "TOC references an unlocked source"):
            build_bundle(self.lock, self.root / "source", self.out)

    def test_refuse_missing_file(self):
        self.lua.unlink()
        with self.assertRaises(FileNotFoundError):
            build_bundle(self.lock, self.root / "source", self.out)

    def test_refuse_duplicate_path(self):
        self.lock_entries.append(dict(self.lock_entries[0]))
        self.write_lock()
        with self.assertRaisesRegex(BundleError, "duplicate"):
            build_bundle(self.lock, self.root / "source", self.out)

    def test_refuse_symlink_escape(self):
        outer = self.root / "outer"
        outer.write_text("bad")
        self.lua.unlink()
        self.lua.symlink_to(outer)
        with self.assertRaises(BundleError):
            build_bundle(self.lock, self.root / "source", self.out)


if __name__ == "__main__":
    unittest.main()
