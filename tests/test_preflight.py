import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("preflight", ROOT / "scripts/preflight.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.destinations = [self.root / part for part in ("config", "data", "state", "cache", "bin")]
        self.patches = [patch.object(preflight.platform, "system", return_value="Linux"),
                        patch.object(preflight.platform, "machine", return_value="x86_64"),
                        patch.object(preflight, "_glibc", return_value=True),
                        patch.object(preflight.shutil, "which", side_effect=lambda name: "/usr/bin/" + name)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def check(self, **kwargs):
        return preflight.check(self.root, *self.destinations, **kwargs)

    def test_offline_config_check_is_read_only(self):
        with patch.object(preflight.urllib.request, "urlopen") as network, patch.object(preflight.subprocess, "run") as run:
            messages = self.check(config_only=True)
        network.assert_not_called()
        run.assert_not_called()
        self.assertTrue(any("skipped" in line for line in messages))
        self.assertFalse(any(path.exists() for path in self.destinations))

    def test_unsupported_os_fails_before_network(self):
        with patch.object(preflight.platform, "system", return_value="Darwin"), patch.object(preflight.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(RuntimeError, "Linux x86_64 and ARM64"):
                self.check()
        network.assert_not_called()

    def test_config_only_requires_git_without_installing_it(self):
        with patch.object(preflight.shutil, "which", side_effect=lambda name: None if name == "git" else "/usr/bin/" + name), patch.object(preflight.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Configuration-only installation requires Git"):
                self.check(config_only=True)
        run.assert_not_called()

    def test_old_python_and_broad_path_are_rejected(self):
        with patch.object(preflight.sys, "version_info", (3, 8)):
            with self.assertRaisesRegex(RuntimeError, "Python 3.9"):
                self.check(network=False)
        self.assertIn("too broad", preflight._writable_destination(Path("/")))
        self.assertIn("absolute", preflight._writable_destination(Path("relative")))

    def test_destination_file_or_dangling_link_is_rejected(self):
        blocked = self.root / "blocked"
        blocked.write_text("keep")
        self.assertIn("blocked by the file", preflight._writable_destination(blocked / "child"))
        link = self.root / "link"
        link.symlink_to(self.root / "absent")
        self.assertIn("dangling symlink", preflight._writable_destination(link / "child"))
        good = self.root / "good"
        good.symlink_to(self.root, target_is_directory=True)
        self.assertIsNone(preflight._writable_destination(good / "child"))

    def test_musl_requires_existing_vp(self):
        with patch.object(preflight, "_glibc", return_value=False), patch.object(preflight, "_existing_vp", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "matching Vite\\+ build"):
                self.check(network=False)
        with patch.object(preflight, "_glibc", return_value=False), patch.object(preflight, "_existing_vp", return_value=True):
            self.assertTrue(any("preserving" in line for line in self.check(network=False)))

    def test_missing_base_tools_use_apt_simulation_only(self):
        lookup = lambda name: None if name == "psql" else "/usr/bin/" + name
        with patch.object(preflight.shutil, "which", side_effect=lookup), patch.object(preflight.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.check(network=False)
        self.assertEqual(run.call_args.args[0], ["apt-get", "-s", "--no-install-recommends", "install", "postgresql-client"])
        with patch.object(preflight.shutil, "which", side_effect=lookup), patch.object(preflight.subprocess, "run", return_value=Mock(returncode=100)):
            with self.assertRaisesRegex(RuntimeError, "sudo apt-get update"):
                self.check(network=False)

    def test_missing_package_utilities_give_manual_remedy(self):
        with patch.object(preflight.shutil, "which", side_effect=lambda name: None if name in ("zsh", "dpkg-deb") else "/usr/bin/" + name):
            with self.assertRaisesRegex(RuntimeError, "apt-get and dpkg-deb"):
                self.check(network=False)

    def test_tls_failure_is_actionable(self):
        with patch.object(preflight.urllib.request, "urlopen", side_effect=urllib.error.URLError("certificate verify failed")):
            with self.assertRaisesRegex(RuntimeError, "CA certificates"):
                self.check()

    def test_bootstrap_dry_run_does_not_install_packages(self):
        # Run only the dry-run branch. The actual administrator commands must
        # never be exercised by this suite.
        result = subprocess.run(["bash", str(ROOT / "install.sh"), "--install-prerequisites", "--dry-run"], capture_output=True, text=True)
        if "Automatic prerequisite installation supports" in result.stderr:
            self.skipTest("bootstrap is specific to Debian/Ubuntu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("apt-get update", result.stdout)
        self.assertIn("apt-get install", result.stdout)


if __name__ == "__main__":
    unittest.main()
