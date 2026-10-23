import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup", ROOT / "scripts/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = patch.object(setup, "STATE", self.root / "state")
        self.state.start()

    def tearDown(self):
        self.state.stop()
        self.temporary.cleanup()

    def test_backup_idempotence_and_restore(self):
        source, target = self.root / "new", self.root / "config"
        source.write_text("new")
        target.write_text("original")
        deploy = setup.Deployment()
        deploy.link(source, target)
        backup = Path(deploy.state["links"][str(target)]["backup"])
        self.assertEqual(backup.read_text(), "original")
        deploy.link(source, target)
        self.assertEqual(len(list(deploy.backup_dir.iterdir())), 1)
        deploy.restore()
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_text(), "original")

    def test_restore_preserves_later_user_changes(self):
        source, target = self.root / "new", self.root / "config"
        source.write_text("new")
        deploy = setup.Deployment()
        deploy.link(source, target)
        target.unlink()
        target.write_text("user change")
        deploy.restore()
        self.assertEqual(target.read_text(), "user change")

    def test_restore_dangling_original_symlink(self):
        source, target = self.root / "new", self.root / "config"
        source.write_text("new")
        target.symlink_to(self.root / "missing")
        deploy = setup.Deployment()
        deploy.link(source, target)
        deploy.restore()
        self.assertEqual(target.readlink(), self.root / "missing")

    def test_relocating_checkout_keeps_original_backup(self):
        old, new, target = (self.root / p for p in ["old", "new", "config"])
        old.write_text("old")
        new.write_text("new")
        target.write_text("original")
        deploy = setup.Deployment()
        deploy.link(old, target)
        backup = deploy.state["links"][str(target)]["backup"]
        deploy.link(new, target)
        self.assertEqual(target.read_text(), "new")
        self.assertEqual(deploy.state["links"][str(target)]["backup"], backup)
        deploy.restore()
        self.assertEqual(target.read_text(), "original")

    def test_checkout_can_live_at_config_destination(self):
        source = self.root / "checkout"
        source.mkdir()
        setup.Deployment().link(source, source)
        self.assertTrue(source.is_dir())
        self.assertFalse(source.is_symlink())


class ArchiveTests(unittest.TestCase):
    def test_executables_ignore_archive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tool.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                payload = b"#!/bin/sh\necho ok\n"
                member = tarfile.TarInfo("../../outside/tool")
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))
            setup.extract_executables(archive, root / "bin", ["tool"])
            self.assertEqual((root / "bin/tool").read_bytes(), payload)
            self.assertFalse((root / "outside").exists())

    def test_duplicate_binary_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(root / "tool.zip", "w") as bundle:
                bundle.writestr("a/tool", "first")
                bundle.writestr("b/tool", "second")
            with self.assertRaisesRegex(RuntimeError, "Duplicate executable"):
                setup.extract_executables(root / "tool.zip", root / "bin", ["tool"])

    def test_plugin_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with tarfile.open(root / "plugin.tar.gz", "w:gz") as bundle:
                member = tarfile.TarInfo("plugin/../../escape")
                member.size = 1
                bundle.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(RuntimeError, "Unsafe path"):
                setup.extract_plugin(root / "plugin.tar.gz", root / "plugin")

    def test_plugin_allows_internal_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with tarfile.open(root / "plugin.tar.gz", "w:gz") as bundle:
                member = tarfile.TarInfo("plugin/docs/readme")
                member.size = 1
                bundle.addfile(member, io.BytesIO(b"x"))
                link = tarfile.TarInfo("plugin/sub/readme")
                link.type, link.linkname = tarfile.SYMTYPE, "../docs/readme"
                bundle.addfile(link)
            setup.extract_plugin(root / "plugin.tar.gz", root / "plugin")
            self.assertEqual((root / "plugin/sub/readme").read_text(), "x")

    def test_plugin_rejects_escaping_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with tarfile.open(root / "plugin.tar.gz", "w:gz") as bundle:
                link = tarfile.TarInfo("plugin/link")
                link.type, link.linkname = tarfile.SYMTYPE, "../../escape"
                bundle.addfile(link)
            with self.assertRaisesRegex(RuntimeError, "Unsafe symlink"):
                setup.extract_plugin(root / "plugin.tar.gz", root / "plugin")

    def test_download_rejects_invalid_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "download"
            source.write_bytes(b"corrupt")
            with patch.object(setup, "CACHE", root / "cache"), patch.object(setup.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                    setup.download(source.as_uri(), "0" * 64, "tool")
                self.assertFalse(list((root / "cache/downloads").glob("*.part")))


class ManagerTests(unittest.TestCase):
    def test_existing_managers_are_not_reinstalled_or_reconfigured(self):
        lock = json.loads((ROOT / "tools.lock.json").read_text())
        managers = {"tools": {n: lock["tools"][n] for n in ["vp", "uv"]}, "plugins": {}}
        deploy = Mock()
        with patch.object(setup, "find_tool", side_effect=lambda n: "/existing/" + n), patch.object(setup, "download") as download, patch.object(setup, "run") as run:
            setup.install_tools(managers, "linux-x86_64", deploy)
        download.assert_not_called()
        deploy.link.assert_not_called()
        self.assertEqual(run.call_args_list, [unittest.mock.call(["/existing/vp", "--version"], capture_output=True, text=True), unittest.mock.call(["/existing/uv", "--version"], capture_output=True, text=True)])

    def test_absent_managers_install_uvx_and_prepare_vite_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = json.loads((ROOT / "tools.lock.json").read_text())
            managers = {"tools": {n: lock["tools"][n] for n in ["vp", "uv"]}, "plugins": {}}
            archives = {}
            for name, item in managers["tools"].items():
                archive = root / (name + ".tar.gz")
                with tarfile.open(archive, "w:gz") as bundle:
                    for executable in item["binaries"]:
                        content = b"#!/bin/sh\nexit 0\n"
                        member = tarfile.TarInfo(executable)
                        member.size = len(content)
                        bundle.addfile(member, io.BytesIO(content))
                    if name == "vp":
                        member = tarfile.TarInfo("sync-versions/bin.mjs")
                        member.size = 2
                        bundle.addfile(member, io.BytesIO(b"//"))
                archives[name] = archive
            deploy = Mock()
            def download(url, digest, filename):
                return archives["uv" if filename.startswith("uv-") else "vp"]
            with patch.object(setup, "DATA", root / "data"), patch.object(setup, "BIN", root / "bin"), patch.object(setup, "find_tool", return_value=None), patch.object(setup, "download", side_effect=download), patch.object(setup, "run") as run:
                setup.install_tools(managers, "linux-x86_64", deploy)
            self.assertEqual({call.args[1].name for call in deploy.link.call_args_list}, {"uv", "uvx", "vp"})
            self.assertEqual(len(run.call_args_list), 1)
            self.assertEqual(run.call_args.args[0][1:], ["env", "setup"])
            bundles = list((root / "data/tools/vp").glob("*/sync-versions/bin.mjs"))
            self.assertEqual(len(bundles), 1)
            self.assertEqual(bundles[0].read_text(), "//")
            self.assertEqual(run.call_args.kwargs["env"]["VP_SELF_SETUP_NO_MODIFY_PATH"], "1")

    def test_manager_discovery_before_shell_environment_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vp = root / "share/vite-plus/bin/vp"
            uv = root / ".cargo/bin/uv"
            for path in [vp, uv]:
                path.parent.mkdir(parents=True)
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            with patch.object(setup, "HOME", root), patch.object(setup, "DATA", root / "share/linux-setup"), patch.object(setup, "BIN", root / ".local/bin"), patch.object(setup.shutil, "which", return_value=None), patch.dict(os.environ, {n: "" for n in ["VP_HOME", "VP_BIN_DIR", "UV_INSTALL_DIR"]}):
                self.assertEqual(setup.find_tool("vp"), str(vp))
                self.assertEqual(setup.find_tool("uv"), str(uv))


class IntegrationTests(unittest.TestCase):
    def test_config_install_repeat_and_restore_in_fresh_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".zshrc").write_text("# original shell\n")
            (home / ".zshenv").write_text('. "$HOME/.config/vite-plus/env"\n')
            (home / ".zsh_history").write_text("previous-command\n")
            (home / ".config/bat").mkdir(parents=True)
            (home / ".config/bat/config").write_text("original bat")
            env = {**os.environ, "HOME": str(home), "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
            for kind, folder in [("CONFIG", ".config"), ("DATA", ".local/share"), ("CACHE", ".cache"), ("STATE", ".local/state")]:
                env[f"XDG_{kind}_HOME"] = str(home / folder)
            subprocess.run(["git", "config", "--global", "user.name", "Test User"], env=env, check=True)
            command = [sys.executable, str(ROOT / "scripts/setup.py")]
            for _ in range(2):
                result = subprocess.run(command + ["--config-only", "--skip-mcp"], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / ".zshrc").resolve(), ROOT / "config/zsh/zshrc")
            local = (home / ".config/linux-setup-local/zshenv").read_text()
            self.assertEqual(local.count('source "$XDG_CONFIG_HOME/vite-plus/env"'), 1)
            self.assertEqual((home / ".local/state/zsh/history").read_text(), "previous-command\n")
            includes = subprocess.check_output(["git", "config", "--global", "--get-all", "include.path"], env=env, text=True)
            self.assertEqual(len(includes.splitlines()), 1)
            result = subprocess.run(command + ["--restore"], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / ".zshrc").read_text(), "# original shell\n")
            self.assertEqual((home / ".config/bat/config").read_text(), "original bat")
            self.assertEqual(subprocess.check_output(["git", "config", "--global", "user.name"], env=env, text=True).strip(), "Test User")
            result = subprocess.run(["git", "config", "--global", "--get-all", "include.path"], env=env, capture_output=True)
            self.assertEqual(result.returncode, 1)

    def test_lock_has_pinned_assets_for_all_platforms(self):
        lock = json.loads((ROOT / "tools.lock.json").read_text())
        for arch in ["x86_64", "aarch64"]:
            self.assertIn("linux-gnu", lock["tools"]["vp"]["platforms"]["linux-" + arch]["name"])
        platforms = {"linux-x86_64", "linux-aarch64"}
        for name, item in lock["tools"].items():
            self.assertEqual(set(item["platforms"]), platforms, name)
            for asset in item["platforms"].values():
                self.assertRegex(asset["sha256"], r"^[a-f0-9]{64}$")
                self.assertIn("/releases/download/", asset["url"])
                self.assertNotIn("/latest/", asset["url"])
        for plugin in lock["plugins"].values():
            self.assertRegex(plugin["commit"], r"^[a-f0-9]{40}$")
            self.assertIn(plugin["commit"], plugin["url"])


if __name__ == "__main__":
    unittest.main()
