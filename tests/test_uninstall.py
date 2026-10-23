import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location("uninstall", Path(__file__).resolve().parents[1] / "scripts/uninstall.py")
uninstall = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uninstall)


class FakeDeployment:
    def __init__(self, state):
        self.state = state
        self.saved = 0

    def save(self):
        self.saved += 1

    def restore(self, targets=None):
        unresolved = []
        for target in list(targets if targets is not None else self.state["links"]):
            item = self.state["links"][target]
            path = Path(target)
            if uninstall.present(path) and (not path.is_symlink() or os.readlink(path) != item["source"]):
                unresolved.append(target)
                continue
            if path.is_symlink():
                path.unlink()
            if item.get("backup"):
                backup = Path(item["backup"])
                if uninstall.present(backup):
                    backup.rename(path)
            del self.state["links"][target]
        return unresolved


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patches = []
        locations = {"HOME": self.root, "DATA": self.root / "share/linux-setup", "STATE": self.root / "state/linux-setup", "CACHE": self.root / "cache/linux-setup", "CONFIG": self.root / "config", "BIN": self.root / "bin", "ROOT": self.root / "checkout"}
        for name, path in locations.items():
            path.mkdir(parents=True, exist_ok=True)
            self.patches.append(patch.object(uninstall.setup, name, path))
        self.patches += [patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache")}), patch.object(uninstall, "login_shell", return_value="/bin/bash")]
        for p in self.patches:
            p.start()
        self.deploy = FakeDeployment({"links": {}, "programs": {}})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temporary.cleanup()

    def program(self, name, shared=None):
        path = uninstall.setup.DATA / "tools" / name / "1"
        path.mkdir(parents=True)
        binary = path / name
        binary.write_text("executable")
        target = uninstall.setup.BIN / name
        target.symlink_to(binary)
        self.deploy.state["links"][str(target)] = {"source": str(binary), "backup": None, "program": name}
        item = {"owned": True, "kind": "tool", "version": "1", "binaries": [name], "paths": [str(path)], "shared": [str(shared)] if shared else []}
        self.deploy.state["programs"][name] = item
        if shared:
            self.deploy.state.setdefault("shared_fingerprints", {})[str(shared)] = uninstall.setup.fingerprint(shared)
        return path, target, item

    def configuration(self):
        source = uninstall.setup.ROOT / "zshrc"
        source.write_text("setup config")
        target = self.root / ".zshrc"
        target.symlink_to(source)
        backup = uninstall.setup.STATE / "original-zshrc"
        backup.write_text("original config")
        self.deploy.state["links"][str(target)] = {"source": str(source), "backup": str(backup)}
        return target

    def test_keep_programs_restores_config_and_preserves_cache(self):
        path, target, _ = self.program("fzf")
        config = self.configuration()
        cache = uninstall.setup.CACHE / "downloads"
        cache.mkdir()
        report = uninstall.apply_plan(self.deploy, set(), {})
        self.assertEqual(config.read_text(), "original config")
        self.assertTrue(path.exists())
        self.assertTrue(target.is_symlink())
        self.assertTrue(cache.exists())
        self.assertEqual(report["unresolved"], [])

    def test_selected_removal_keeps_other_program(self):
        removed, link, _ = self.program("fd")
        retained, retained_link, _ = self.program("fzf")
        report = uninstall.apply_plan(self.deploy, {"fd"}, {})
        self.assertFalse(removed.exists())
        self.assertFalse(uninstall.present(link))
        self.assertTrue(retained.exists())
        self.assertTrue(retained_link.exists())
        self.assertEqual(report["removed"], ["fd"])

    def test_shared_runtime_removed_only_after_last_consumer(self):
        runtime = uninstall.setup.DATA / "runtime"
        runtime.mkdir()
        (runtime / "library").write_text("dependency")
        self.program("psql", runtime)
        self.program("tmux", runtime)
        uninstall.apply_plan(self.deploy, {"psql"}, {})
        self.assertTrue(runtime.exists())
        uninstall.apply_plan(self.deploy, {"tmux"}, {})
        self.assertFalse(runtime.exists())

    def test_changed_link_preserves_program(self):
        path, target, _ = self.program("fd")
        target.unlink()
        target.write_text("user replacement")
        report = uninstall.apply_plan(self.deploy, {"fd"}, {})
        self.assertTrue(path.exists())
        self.assertEqual(target.read_text(), "user replacement")
        self.assertTrue(report["unresolved"])

    def test_external_program_and_unsafe_paths_are_preserved(self):
        external = self.root / "external-program"
        external.write_text("keep")
        self.deploy.state["programs"]["external"] = {"owned": False, "paths": [str(external)]}
        self.deploy.state["programs"]["bad"] = {"owned": True, "paths": [str(self.root)]}
        report = uninstall.apply_plan(self.deploy, {"external", "bad"}, {})
        self.assertEqual(external.read_text(), "keep")
        self.assertEqual(len(report["unresolved"]), 2)

    def test_cache_selection_is_independent_and_allowlisted(self):
        self.program("bat")
        cache = self.root / "cache/bat"
        cache.mkdir()
        other = self.root / "cache/unrelated"
        other.mkdir()
        report = uninstall.apply_plan(self.deploy, set(), {"bat": [str(cache)], "bad": [str(other)]})
        self.assertFalse(cache.exists())
        self.assertTrue(other.exists())
        self.assertIn("bat", self.deploy.state["programs"])
        self.assertTrue(report["unresolved"])

    def test_cache_symlink_and_parent_escape_are_refused(self):
        outside = self.root / "important"
        outside.mkdir()
        (outside / "value").write_text("keep")
        uv = self.root / "cache/uv"
        uv.symlink_to(outside, target_is_directory=True)
        report = uninstall.apply_plan(self.deploy, set(), {"uv": [str(uv)]})
        self.assertTrue((outside / "value").exists())
        self.assertTrue(uv.is_symlink())
        self.assertTrue(report["unresolved"])

    def test_login_shell_retained_if_switch_fails(self):
        path, target, _ = self.program("zsh")
        with patch.object(uninstall, "login_shell", return_value=str(target)), patch.object(uninstall, "switch_shell", return_value=False):
            report = uninstall.apply_plan(self.deploy, {"zsh"}, {})
        self.assertTrue(path.exists())
        self.assertTrue(target.exists())
        self.assertIn("login shell", report["unresolved"][0])

    def test_login_shell_removed_only_after_verified_switch(self):
        path, target, _ = self.program("zsh")
        with patch.object(uninstall, "login_shell", return_value=str(target)), patch.object(uninstall, "switch_shell", return_value=True) as switch:
            report = uninstall.apply_plan(self.deploy, {"zsh"}, {}, replacement="/bin/bash")
        switch.assert_called_once()
        self.assertFalse(path.exists())
        self.assertFalse(target.exists())
        self.assertEqual(report["unresolved"], [])

    def test_shared_dependency_does_not_misidentify_other_program_as_shell(self):
        runtime = uninstall.setup.DATA / "runtime"
        runtime.mkdir()
        zsh = runtime / "zsh"
        zsh.write_text("shell")
        _, _, item = self.program("psql", runtime)
        with patch.object(uninstall, "login_shell", return_value=str(zsh)):
            self.assertFalse(uninstall.program_is_login_shell("psql", item, self.deploy.state["links"]))

    def test_external_generated_files_restored(self):
        self.program("vp")
        original = uninstall.setup.STATE / "vp-backup"
        original.write_text("original")
        generated = uninstall.setup.CONFIG / "vp-env"
        generated.write_text("generated")
        self.deploy.state["programs"]["vp"]["external_files"] = {str(generated): {"sha256": hashlib.sha256(b"generated").hexdigest(), "backup": str(original)}}
        report = uninstall.apply_plan(self.deploy, {"vp"}, {})
        self.assertEqual(generated.read_text(), "original")
        self.assertFalse(original.exists())
        self.assertEqual(report["unresolved"], [])

    def test_changed_external_generated_file_preserves_program(self):
        path, _, item = self.program("vp")
        generated = uninstall.setup.CONFIG / "vp-env"
        generated.write_text("user change")
        item["external_files"] = {str(generated): {"sha256": hashlib.sha256(b"generated").hexdigest()}}
        report = uninstall.apply_plan(self.deploy, {"vp"}, {})
        self.assertEqual(generated.read_text(), "user change")
        self.assertTrue(path.exists())
        self.assertTrue(report["unresolved"])

    def test_cache_options_exclude_external_tools_and_history(self):
        (self.root / "cache/uv").mkdir()
        (self.root / "cache/zsh").mkdir()
        (self.root / "cache/zsh/history").write_text("history")
        (self.root / "cache/zsh/zcompdump-5.9").write_text("cache")
        options = uninstall.cache_options({"uv": {"owned": False}, "zsh": {"owned": True}})
        self.assertNotIn("uv", options)
        self.assertEqual(options["zsh"]["paths"], [self.root / "cache/zsh/zcompdump-5.9"])

    def test_dry_run_does_not_create_journal_or_remove_files(self):
        path, _, _ = self.program("fd")
        with patch.object(uninstall.setup, "Deployment", return_value=self.deploy), patch("sys.stdout", new_callable=io.StringIO):
            code = uninstall.main(["--all-tools", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(path.exists())
        self.assertFalse((uninstall.setup.STATE / "uninstall.json").exists())
        self.assertEqual(self.deploy.saved, 0)

    def test_repeated_removal_resumes_completed_programs(self):
        path, _, _ = self.program("fd")
        uninstall.apply_plan(self.deploy, {"fd"}, {})
        journal = json.loads((uninstall.setup.STATE / "uninstall.json").read_text())
        report = uninstall.apply_plan(self.deploy, {"fd"}, {}, journal=journal)
        self.assertFalse(path.exists())
        self.assertEqual(report["unresolved"], [])
        self.assertEqual(journal["status"], "complete")

    def test_selection_fallback_returns_checked_values(self):
        with patch.object(uninstall.shutil, "which", return_value=None), patch("builtins.input", side_effect=["1 2", "2", ""]), patch("sys.stdout", new_callable=io.StringIO):
            values = uninstall.choose("Remove", [("one", "a"), ("two", "b")], multi=True)
        self.assertEqual(values, ["a"])

    def test_fzf_enter_without_checks_keeps_everything(self):
        output = SimpleNamespace(returncode=0, stdout="__NONE__\0" + "0\tone\0")
        with patch.object(uninstall.shutil, "which", return_value="fzf"), patch.object(uninstall.subprocess, "run", return_value=output) as run:
            values = uninstall.choose("Remove", [("one", "a")], multi=True)
        self.assertEqual(values, [])
        self.assertIn("FZF_SELECT_COUNT", " ".join(run.call_args.args[0]))

    def test_modified_program_tree_is_retained(self):
        path, _, item = self.program("fd")
        item["fingerprints"] = {str(path): uninstall.setup.fingerprint(path)}
        (path / "fd").write_text("user modified binary")
        report = uninstall.apply_plan(self.deploy, {"fd"}, {})
        self.assertTrue(path.exists())
        self.assertTrue(report["unresolved"])

    def test_uv_cache_uses_manager_before_removing_executable(self):
        path, target, _ = self.program("uv")
        cache = self.root / "cache/uv"
        cache.mkdir()
        (cache / ".lock").write_text("lock")
        def run(args, **kwargs):
            self.assertTrue(target.exists())
            self.assertEqual(args, [str(target), "--cache-dir", str(cache), "cache", "clean"])
            return SimpleNamespace(returncode=0)
        with patch.object(uninstall.setup, "find_tool", return_value=str(target)), patch.object(uninstall.subprocess, "run", side_effect=run):
            report = uninstall.apply_plan(self.deploy, {"uv"}, {"uv": [str(cache)]})
        self.assertFalse(path.exists())
        self.assertTrue((cache / ".lock").exists())
        self.assertEqual(report["unresolved"], [])

    def test_yes_requires_explicit_mode(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(uninstall.main(["--yes"]), 1)
        self.assertFalse((uninstall.setup.STATE / "uninstall.json").exists())

    def test_legacy_zsh_prepared_before_configuration_restore(self):
        self.configuration()
        with patch.object(uninstall.setup, "prepare_retained_zsh") as prepare:
            uninstall.apply_plan(self.deploy, set(), {})
        prepare.assert_called_once_with(self.deploy)

    def test_resume_removes_runtime_after_program_record_is_gone(self):
        runtime = uninstall.setup.DATA / "runtime"
        runtime.mkdir()
        (runtime / "library").write_text("dependency")
        self.deploy.state["shared_fingerprints"] = {str(runtime): uninstall.setup.fingerprint(runtime)}
        journal = {"remove": ["psql"], "caches": {}, "shared": [str(runtime)], "completed": ["program:psql"]}
        uninstall.apply_plan(self.deploy, {"psql"}, {}, journal=journal)
        self.assertFalse(runtime.exists())

    def test_modified_shared_runtime_is_retained(self):
        runtime = uninstall.setup.DATA / "runtime"
        runtime.mkdir()
        self.program("psql", runtime)
        (runtime / "custom").write_text("keep")
        report = uninstall.apply_plan(self.deploy, {"psql"}, {})
        self.assertTrue((runtime / "custom").exists())
        self.assertTrue(report["unresolved"])

    def test_external_restore_checkpoint_recovers_completed_move(self):
        _, _, item = self.program("vp")
        generated = uninstall.setup.CONFIG / "vp-env"
        generated.write_text("original")
        backup = uninstall.setup.STATE / "already-moved-backup"
        item["external_files"] = {str(generated): {"sha256": hashlib.sha256(b"generated").hexdigest(), "backup": str(backup)}}
        item["restoring_external"] = {"path": str(generated), "backup_fingerprint": uninstall.setup.fingerprint(generated)}
        report = uninstall.apply_plan(self.deploy, {"vp"}, {})
        self.assertEqual(generated.read_text(), "original")
        self.assertEqual(report["unresolved"], [])

    def test_legacy_cache_preview_and_exact_remap_without_mutation(self):
        uninstall.setup.CACHE.rmdir()
        old_cache = uninstall.setup.CACHE.parent / "dev-setup"
        (old_cache / "downloads").mkdir(parents=True)
        old_state = uninstall.setup.STATE.parent / "dev-setup"
        old_state.mkdir()
        (old_state / "deployment.json").write_text('{"links":{}}')
        options = uninstall.cache_options({})
        self.assertEqual(options["setup-downloads"]["paths"], [old_cache / "downloads"])
        self.assertFalse(uninstall.setup.CACHE.exists())
        self.assertTrue(old_cache.is_dir())
        mapped = uninstall.canonical_cache_paths({"setup-downloads": [str(old_cache / "downloads")], "uv": [str(old_cache / "uv")]})
        self.assertEqual(mapped["setup-downloads"], [str(uninstall.setup.CACHE / "downloads")])
        self.assertEqual(mapped["uv"], [str(old_cache / "uv")])

    def test_retargeted_tools_root_cannot_escape_managed_data(self):
        external = self.root / "external-tools"
        (external / "fd").mkdir(parents=True)
        (uninstall.setup.DATA / "tools").symlink_to(external, target_is_directory=True)
        self.assertFalse(uninstall.safe_program_path(uninstall.setup.DATA / "tools/fd"))

    def test_retargeted_legacy_source_alias_preserves_owned_program(self):
        path, target, item = self.program("fd")
        external = self.root / "replacement"
        external.mkdir()
        (external / "fd").write_text("replacement binary")
        alias = self.root / "old-data-alias"
        alias.symlink_to(external, target_is_directory=True)
        target.unlink()
        target.symlink_to(alias / "fd")
        self.deploy.state["links"][str(target)]["source"] = str(alias / "fd")
        report = uninstall.apply_plan(self.deploy, {"fd"}, {})
        self.assertTrue(path.exists())
        self.assertTrue(target.exists())
        self.assertIn("changed source alias", report["unresolved"][0])


if __name__ == "__main__":
    unittest.main()
