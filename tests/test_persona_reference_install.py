import base64
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/persona_reference_install.py"
spec = importlib.util.spec_from_file_location("mio_reference_install", SOURCE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ReferenceInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.image = self.data / "media/mio/references" / (installer.REFERENCE_ID + ".jpg")
        self.bytes = b"\xff\xd8\xff" + b"exact approved reference bytes" * 3
        self.pack = {"status": "approved", "approved_reference_ids": [installer.REFERENCE_ID],
                     "canonical_asset": {"reference_id": installer.REFERENCE_ID,
                                         "sha256": installer.digest(self.bytes), "mime_type": "image/jpeg"}}
        self.transfer = {"schema": "agentos.persona-reference-transfer/v1",
                         "reference_id": installer.REFERENCE_ID, "persona_path": installer.PERSONA,
                         "asset_path": installer.ASSET_PATH, "approval_source": installer.PACK_PATH,
                         "sha256": installer.digest(self.bytes), "byte_size": len(self.bytes),
                         "mime_type": "image/jpeg"}
        self.calls = []
        for name, value in (("DATA_ROOT", self.data), ("CONFIG_ROOT", self.config)):
            mock = patch.object(installer, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.uid = patch.object(installer.os, "getuid", return_value=1001).start()
        self.addCleanup(patch.stopall)

    def api(self, endpoint):
        self.calls.append(endpoint)
        if not endpoint:
            return {"private": True}
        path, ref = endpoint.removeprefix("contents/").split("?ref=")
        if path == installer.PACK_PATH:
            value = json.dumps(self.pack).encode()
            self.assertEqual(ref, "main")
        elif path == installer.TRANSFER_PATH:
            value = json.dumps(self.transfer).encode()
            self.assertEqual(ref, installer.SOURCE_COMMIT)
        else:
            self.assertEqual(path, installer.ASSET_PATH)
            self.assertEqual(ref, installer.SOURCE_COMMIT)
            value = self.bytes
        return {"path": path, "encoding": "base64", "size": len(value),
                "content": base64.b64encode(value).decode()}

    def run_install(self, api=None):
        with patch.object(installer, "github", side_effect=api or self.api):
            return installer.run("a" * 40)

    def test_exact_private_install_and_idempotent_retry(self):
        first = self.run_install()
        env = self.config / "mio-reference.env"
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["observed"]["reference_status"], "MATCHED")
        self.assertEqual(self.image.read_bytes(), self.bytes)
        self.assertIn(str(self.image), env.read_text())
        self.assertEqual(self.image.stat().st_mode & 0o777, 0o600)
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.image.parent.stat().st_mode & 0o777, 0o700)
        times = (self.image.stat().st_mtime_ns, env.stat().st_mtime_ns)
        second = self.run_install()
        self.assertFalse(second["observed"]["changed"])
        self.assertEqual(times, (self.image.stat().st_mtime_ns, env.stat().st_mtime_ns))
        self.assertFalse(second["publication_allowed"])
        receipt = self.data / "runtime/persona-media/reference-install.json"
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(receipt.read_text())["observed"]["asset_source_commit"], installer.SOURCE_COMMIT)

    def test_existing_private_media_configuration_is_preserved(self):
        self.config.mkdir()
        media = self.config / "mio-media.env"
        original = b'OTHER_PROVIDER_SETTING="private-original"\n'
        media.write_bytes(original)
        receipt = self.run_install()
        self.assertEqual(media.read_bytes(), original)
        self.assertNotIn("private-original", json.dumps(receipt))

    def test_unapproved_pack_leaves_existing_asset_and_configuration_intact(self):
        self.run_install()
        self.pack["status"] = "pending"
        before = self.image.stat().st_mtime_ns
        result = self.run_install()
        self.assertEqual(result["reason"], "REFERENCE_NOT_APPROVED")
        self.assertEqual(self.image.stat().st_mtime_ns, before)

    def test_rejected_reference_blocks_even_if_status_still_approved(self):
        self.pack["rejected_reference_ids"] = [installer.REFERENCE_ID]
        self.assertEqual(self.run_install()["reason"], "REFERENCE_NOT_APPROVED")
        self.assertFalse(self.image.exists())

    def test_changed_bytes_do_not_install(self):
        self.bytes += b"tampered"
        self.assertEqual(self.run_install()["reason"], "REFERENCE_DIGEST_MISMATCH")
        self.assertFalse(self.image.exists())

    def test_transfer_cannot_redirect_to_another_path(self):
        self.transfer["asset_path"] = "../../other.jpg"
        self.assertEqual(self.run_install()["reason"], "REFERENCE_TRANSFER_INVALID")
        self.assertFalse(self.image.exists())

    def test_missing_or_superseded_reference_cannot_be_substituted(self):
        self.pack["canonical_asset"]["reference_id"] = "mio-avatar"
        self.assertEqual(self.run_install()["reason"], "REFERENCE_NOT_APPROVED")

    def test_revocation_during_download_prevents_mutation(self):
        count = 0
        def revoked(endpoint):
            nonlocal count
            if endpoint == "contents/" + installer.PACK_PATH + "?ref=main":
                count += 1
                if count == 2:
                    self.pack["status"] = "revoked"
            return self.api(endpoint)
        self.assertEqual(self.run_install(revoked)["reason"], "REFERENCE_NOT_APPROVED")
        self.assertFalse(self.image.exists())
        self.assertFalse((self.config / "mio-reference.env").exists())

    def test_new_approved_digest_during_download_prevents_mutation(self):
        count = 0
        def superseded(endpoint):
            nonlocal count
            if endpoint == "contents/" + installer.PACK_PATH + "?ref=main":
                count += 1
                if count == 2:
                    self.pack["canonical_asset"]["sha256"] = "b" * 64
            return self.api(endpoint)
        self.assertEqual(self.run_install(superseded)["reason"], "REFERENCE_APPROVAL_CHANGED")
        self.assertFalse(self.image.exists())

    def test_public_repository_is_not_a_fallback(self):
        self.assertEqual(self.run_install(lambda _: {"private": False})["reason"], "REFERENCE_SOURCE_NOT_PRIVATE")

    def test_configuration_symlink_cannot_overwrite_another_file(self):
        self.config.mkdir()
        other = self.root / "other"
        other.write_text("unchanged")
        (self.config / "mio-reference.env").symlink_to(other)
        result = self.run_install()
        self.assertEqual(result["reason"], "REFERENCE_PRIVATE_PATH_INVALID")
        self.assertFalse(self.image.exists())
        self.assertEqual(other.read_text(), "unchanged")

    def test_parent_symlink_cannot_escape_private_store(self):
        self.data.mkdir()
        other = self.root / "other-directory"
        other.mkdir()
        (self.data / "media").symlink_to(other, target_is_directory=True)
        self.assertEqual(self.run_install()["reason"], "REFERENCE_PRIVATE_PATH_INVALID")
        self.assertEqual(list(other.iterdir()), [])

    def test_non_private_existing_modes_are_repaired(self):
        self.run_install()
        self.image.chmod(0o644)
        result = self.run_install()
        self.assertTrue(result["observed"]["changed"])
        self.assertEqual(self.image.stat().st_mode & 0o777, 0o600)

    def test_wrong_user_cannot_fetch_or_persist(self):
        self.uid.return_value = 0
        with patch.object(installer, "github") as fetch:
            receipt = installer.run("a" * 40)
        self.assertEqual(receipt["reason"], "REFERENCE_WRONG_USER")
        fetch.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_provider_error_is_sanitized(self):
        result = self.run_install(lambda _: (_ for _ in ()).throw(ValueError("secret diagnostic private-original")))
        self.assertEqual(result["reason"], "REFERENCE_INSTALL_INVALID")
        self.assertNotIn("secret", json.dumps(result))

    def test_github_preserves_existing_auth_without_workflow_token(self):
        with patch.dict(os.environ, {"GH_TOKEN": "workflow-token", "GITHUB_TOKEN": "another-token"}), \
                patch.object(installer.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b'{"private":true}')) as call:
            self.assertEqual(installer.github(""), {"private": True})
        kwargs = call.call_args.kwargs
        self.assertNotIn("GH_TOKEN", kwargs["env"])
        self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
        self.assertEqual(kwargs["timeout"], 20)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(call.call_args.args[0][-1], "repos/" + installer.REPOSITORY)

    def test_github_timeout_and_oversized_response_are_bounded(self):
        with patch.object(installer.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 20)):
            with self.assertRaisesRegex(ValueError, "REFERENCE_SOURCE_TIMEOUT"):
                installer.github("")
        with patch.object(installer.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"x" * (installer.MAX_RESPONSE + 1))):
            with self.assertRaisesRegex(ValueError, "REFERENCE_SOURCE_FETCH_FAILED"):
                installer.github("")

    def test_invalid_base64_source_is_rejected(self):
        with patch.object(installer, "github", return_value={"path": installer.ASSET_PATH, "encoding": "base64", "size": 4, "content": "!?"}):
            with self.assertRaisesRegex(ValueError, "REFERENCE_SOURCE_INVALID"):
                installer.content(installer.ASSET_PATH, installer.SOURCE_COMMIT)


if __name__ == "__main__":
    unittest.main()
