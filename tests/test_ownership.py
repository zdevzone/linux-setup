"""Verify migration and install metadata without changing the real installation."""
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ownership_setup_test", ROOT / "scripts/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, path in {"HOME": self.root, "CONFIG": self.root / "config", "DATA": self.root / "data/linux-setup",
                           "STATE": self.root / "state/linux-setup", "CACHE": self.root / "cache/linux-setup",
                           "BIN": self.root / "bin"}.items():
            self.stack.enter_context(patch.object(setup, name, path))

    def legacy(self):
        old = setup.DATA.parent / "dev-setup"
        binary = old / "tools/fd/1/fd"
        binary.parent.mkdir(parents=True)
        binary.write_text("installed binary")
        (binary.parent / ".sha256").write_text("verified download")
        setup.BIN.mkdir()
        target = setup.BIN / "fd"
        target.symlink_to(binary)
        state = setup.STATE.parent / "dev-setup"
        state.mkdir(parents=True)
        (state / "deployment.json").write_text(json.dumps({"links": {str(target): {"source": str(binary), "backup": None}}}))
        return old, binary, target, state

    def test_read_only_legacy_inventory_makes_no_directories(self):
        _, _, _, _ = self.legacy()
        deploy = setup.Deployment(read_only=True)
        self.assertTrue(deploy.state["programs"]["fd"]["owned"])
        self.assertFalse(setup.STATE.exists())
        with self.assertRaises(RuntimeError):
            deploy.save()

    def test_migration_is_repeatable_and_preserves_links_and_backups(self):
        old, binary, target, state = self.legacy()
        backup = state / "backups/original"
        backup.parent.mkdir()
        backup.write_text("original")
        setup.migrate_legacy()
        setup.migrate_legacy()
        self.assertTrue(old.is_symlink())
        self.assertEqual(target.read_text(), "installed binary")
        self.assertEqual(backup.read_text(), "original")
        deploy = setup.Deployment()
        self.assertEqual(deploy.state["programs"]["fd"]["paths"], [str(setup.DATA / "tools/fd/1")])

    def test_conflicting_destination_leaves_legacy_in_place(self):
        old, _, _, _ = self.legacy()
        setup.DATA.mkdir()
        with self.assertRaisesRegex(RuntimeError, "Both"):
            setup.migrate_legacy()
        self.assertFalse(old.is_symlink())
        self.assertTrue((old / "tools/fd/1/fd").is_file())

    def test_fresh_install_does_not_make_legacy_aliases(self):
        setup.Deployment().save()
        setup.migrate_legacy()
        self.assertFalse((setup.STATE.parent / "dev-setup").exists())

    def test_program_inventory_tracks_versions_and_changed_files(self):
        deploy = setup.Deployment()
        first = setup.DATA / "tools/fd/1"
        second = setup.DATA / "tools/fd/2"
        for path in (first, second):
            path.mkdir(parents=True)
            (path / "fd").write_text("binary")
            deploy.record_program("fd", paths=[path], version=path.name, binaries=["fd"])
        item = deploy.state["programs"]["fd"]
        self.assertEqual(item["paths"], [str(first), str(second)])
        (first / "fd").write_text("modified")
        self.assertNotEqual(item["fingerprints"][str(first)], setup.fingerprint(first))

    def test_directory_fingerprint_tracks_symlinks_without_following(self):
        folder = self.root / "managed"
        folder.mkdir()
        outside = self.root / "outside"
        outside.write_text("data")
        (folder / "link").symlink_to(outside)
        original = setup.fingerprint(folder)
        outside.write_text("new unrelated data")
        self.assertEqual(setup.fingerprint(folder), original)
        (folder / "link").unlink()
        (folder / "link").symlink_to(self.root / "different")
        self.assertNotEqual(setup.fingerprint(folder), original)

    def test_repoint_same_resolved_symlink_keeps_original_backup(self):
        old, new, target = [self.root / name for name in ("old", "new", "target")]
        new.write_text("config")
        old.symlink_to(new)
        target.write_text("original")
        deploy = setup.Deployment()
        deploy.link(old, target)
        backup = deploy.state["links"][str(target)]["backup"]
        deploy.link(new, target)
        self.assertEqual(os.readlink(target), str(new))
        self.assertEqual(deploy.state["links"][str(target)]["backup"], backup)


if __name__ == "__main__":
    unittest.main()
