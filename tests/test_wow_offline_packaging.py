from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_wow_offline_installer import FILES, PACKAGE_ROOT, build


class OfflineInstallerPackageTests(unittest.TestCase):
    def test_reproducible_zip_and_complete_hash_manifest(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/"a.zip"
            b=Path(folder)/"b.zip"
            _,ha=build(root,a)
            _,hb=build(root,b)
            self.assertEqual(ha,hb)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            self.assertEqual(hashlib.sha256(a.read_bytes()).hexdigest(),ha)
            with zipfile.ZipFile(a) as z:
                expected={PACKAGE_ROOT+"/"+name for name in FILES}
                self.assertIn(PACKAGE_ROOT+"/Install-AgentOS-WoW.cmd", expected)
                expected.add(PACKAGE_ROOT+"/manifest.json")
                self.assertEqual(set(z.namelist()),expected)
                manifest=json.loads(z.read(PACKAGE_ROOT+"/manifest.json"))
                self.assertEqual(manifest["release_status"],"UNVERIFIED_PREVIEW_NOT_OFFICIAL")
                self.assertEqual(set(manifest["files_sha256"]),set(FILES))
                for relative,digest in manifest["files_sha256"].items():
                    self.assertEqual(hashlib.sha256(
                        z.read(PACKAGE_ROOT+"/"+relative)
                    ).hexdigest(),digest)


if __name__=="__main__":
    unittest.main()
