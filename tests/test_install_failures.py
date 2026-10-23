"""Preserve user edits and inventory installer side effects when installation fails."""
from contextlib import ExitStack
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("failure_setup_test", ROOT / "scripts/setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class InstallFailureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, path in {
            "HOME": self.root,
            "CONFIG": self.root / "config",
            "DATA": self.root / "data/linux-setup",
            "STATE": self.root / "state/linux-setup",
            "CACHE": self.root / "cache/linux-setup",
            "BIN": self.root / "bin",
        }.items():
            stack.enter_context(patch.object(setup, name, path))
        self.deploy = setup.Deployment()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_reinstall_does_not_adopt_modified_existing_tool_or_plugin(self):
        digest = "a" * 64
        tool = setup.DATA / "tools/fd/1-linux-x86_64"
        plugin = setup.DATA / "plugins/zsh-autosuggestions/commit"
        for name, path, kind in (("fd", tool, "tool"), ("zsh-autosuggestions", plugin, "plugin")):
            self.write(path / ".sha256", digest + "\n")
            self.write(path / name, "installed artifact")
            self.deploy.record_program(name, kind=kind, paths=[path])
        before = {name: dict(item["fingerprints"]) for name, item in self.deploy.state["programs"].items()}
        (tool / "fd").write_text("user modification")
        (plugin / "zsh-autosuggestions").write_text("user modification")
        lock = {
            "tools": {"fd": {"version": "1", "platforms": {"linux-x86_64": {"sha256": digest}}}},
            "plugins": {"zsh-autosuggestions": {"commit": "commit", "sha256": digest}},
        }
        with patch.object(setup, "download") as download:
            setup.install_tools(lock, "linux-x86_64", self.deploy)
        download.assert_not_called()
        for name, path in (("fd", tool), ("zsh-autosuggestions", plugin)):
            item = self.deploy.state["programs"][name]
            self.assertEqual(item["fingerprints"], before[name])
            self.assertNotEqual(item["fingerprints"][str(path)], setup.fingerprint(path))
            self.assertEqual((path / name).read_text(), "user modification")

    def test_modified_retained_zsh_bootstrap_is_not_rewritten(self):
        wrapper = self.write(setup.DATA / "wrappers/zsh", "installed wrapper")
        bootstrap = setup.DATA / "wrappers/zsh-bootstrap"
        startup = self.write(bootstrap / ".zshenv", "installed bootstrap")
        (setup.DATA / "runtime").mkdir()
        self.deploy.record_program("zsh", kind="base", paths=[wrapper, bootstrap], shared=[setup.DATA / "runtime"])
        expected = self.deploy.state["programs"]["zsh"]["fingerprints"][str(bootstrap)]
        startup.write_text("user customization")
        with patch.object(setup, "write_base_wrapper") as write_wrapper:
            setup.prepare_retained_zsh(self.deploy)
        write_wrapper.assert_not_called()
        self.assertEqual(startup.read_text(), "user customization")
        self.assertEqual(self.deploy.state["programs"]["zsh"]["fingerprints"][str(bootstrap)], expected)

    def test_failed_vp_setup_records_modified_environment_and_new_shim(self):
        executable = self.write(setup.DATA / "tools/vp/1/vp", "binary")
        environment = self.write(setup.CONFIG / "vite-plus/env", "original environment")
        shim = setup.DATA.parent / "vite-plus/bin/node"
        self.deploy.record_program("vp", paths=[executable.parent], binaries=["vp"])

        def failed_setup(*args, **kwargs):
            environment.write_text("generated environment")
            shim.parent.mkdir(parents=True)
            shim.symlink_to(executable)
            raise subprocess.CalledProcessError(1, args[0])

        with patch.object(setup, "run", side_effect=failed_setup):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.prepare_vp(executable, self.deploy)
        item = self.deploy.state["programs"]["vp"]
        self.assertNotIn("pending_external", item)
        self.assertEqual(item["external_files"][str(environment)]["sha256"], hashlib.sha256(environment.read_bytes()).hexdigest())
        self.assertEqual(Path(item["external_files"][str(environment)]["backup"]).read_text(), "original environment")
        self.assertEqual(item["external_files"][str(shim)]["symlink"], str(executable))
        self.assertIn(str(shim), setup.Deployment().state["programs"]["vp"]["external_files"])

    def test_interrupted_vp_inventory_is_reconciled_without_mutating_dry_run(self):
        executable = self.write(setup.DATA / "tools/vp/1/vp", "binary")
        environment = self.write(setup.CONFIG / "vite-plus/env", "original environment")
        backup = self.write(setup.STATE / "backups/vp-original", "original environment")
        self.deploy.record_program("vp", paths=[executable.parent], binaries=["vp"])
        self.deploy.state["programs"]["vp"]["pending_external"] = {
            "before": {str(environment): setup.fingerprint(environment)},
            "backups": {str(environment): str(backup)},
        }
        self.deploy.save()
        manifest_before = self.deploy.path.read_bytes()
        environment.write_text("created before process interruption")
        read_only = setup.Deployment(read_only=True)
        item = read_only.state["programs"]["vp"]
        self.assertNotIn("pending_external", item)
        self.assertIn(str(environment), item["external_files"])
        self.assertEqual(self.deploy.path.read_bytes(), manifest_before)
        self.assertEqual(environment.read_text(), "created before process interruption")
        writable = setup.Deployment()
        self.assertNotIn("pending_external", writable.state["programs"]["vp"])
        self.assertEqual(writable.state["programs"]["vp"]["external_files"][str(environment)]["backup"], str(backup))

    def test_partial_base_extraction_is_recorded_and_user_edits_block_retry(self):
        folder = setup.DATA / "base/psql"
        partial = folder / "runtime/usr/share/partial"

        def installation_step(command, **kwargs):
            if command[:2] == ["apt-get", "-s"]:
                return Mock(stdout="Inst postgresql-client (18.6 repo [amd64])\n")
            if command[:2] == ["apt-get", "download"]:
                self.write(Path(kwargs["cwd"]) / "client.deb", "fake package")
                return Mock()
            if command[:2] == ["dpkg-deb", "-x"]:
                self.write(partial, "partially extracted artifact")
                raise subprocess.CalledProcessError(2, command)
            self.fail("Unexpected command: " + repr(command))

        lookup = lambda name: None if name in ("psql", "zsh") else "/usr/bin/" + name
        with patch.object(setup, "BASE", ["psql"]), patch.object(setup.shutil, "which", side_effect=lookup), patch.object(setup, "run", side_effect=installation_step):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.install_base(self.deploy)
        item = self.deploy.state["programs"]["psql"]
        self.assertEqual(item["version"], "incomplete")
        self.assertEqual(item["fingerprints"][str(folder)], setup.fingerprint(folder))
        self.assertFalse((setup.BIN / "psql").exists())

        partial.write_text("user customization after failed install")
        with patch.object(setup, "BASE", ["psql"]), patch.object(setup.shutil, "which", side_effect=lookup), patch.object(setup, "run", side_effect=installation_step) as command:
            with self.assertRaises(RuntimeError):
                setup.install_base(self.deploy)
        self.assertTrue(all(call.args[0][:2] == ["apt-get", "-s"] for call in command.call_args_list))
        self.assertEqual(partial.read_text(), "user customization after failed install")


if __name__ == "__main__":
    unittest.main()
