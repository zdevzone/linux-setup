import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call, patch


SPEC = importlib.util.spec_from_file_location("browser", Path(__file__).resolve().parents[1] / "scripts/browser.py")
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)


def result(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class DependencyReportTests(unittest.TestCase):
    def test_exact_playwright_reports_accept_installed_and_missing_packages(self):
        self.assertEqual(browser.dependency_packages("All system dependencies are installed.\n", 0), [])
        self.assertEqual(browser.dependency_packages(
            "Missing system dependencies (3):\n  libasound2t64\n  libx11-6:amd64\n  fonts-liberation\n", 1),
            ["libasound2t64", "libx11-6:amd64", "fonts-liberation"])

    def test_changed_counts_packages_format_and_exit_codes_fail_closed(self):
        reports = [
            ("", 1),
            ("Missing system dependencies (0):", 1),
            ("Missing system dependencies (02):\n  liba\n  libb", 1),
            ("Missing system dependencies (2):\n  liba", 1),
            ("Missing system dependencies (1):\n  liba\n  libb", 1),
            ("Missing system dependencies (2):\n  liba\n  liba", 1),
            ("Missing system dependencies (1):\n  --unsafe-option", 1),
            ("Missing system dependencies (1):\n  liba;unexpected", 1),
            ("Missing system dependencies (1):\n  liba extra", 1),
            ("Missing system dependencies (1):\n liba", 1),
            ("Missing system dependencies (1):\n  liba\nunknown output", 1),
            ("sudo apt-get install liba", 0),
            ("All system dependencies are installed.", 1),
            ("Missing system dependencies (1):\n  liba", 0),
            ("Missing system dependencies (1):\n  liba", 2),
        ]
        for output, code in reports:
            with self.subTest(output=output, code=code):
                with self.assertRaisesRegex(browser.BrowserError, "Cannot interpret"):
                    browser.dependency_packages(output, code)

    def test_apt_fresh_and_upgrade_rows_produce_exact_deduplicated_specs(self):
        output = (
            "Reading package lists...\n"
            "Inst libnss3 [2:3.110-1] (2:3.112-1 Ubuntu:26.04 [amd64])\n"
            "Inst libatk1.0-0t64 (2.58.0-1 Ubuntu:26.04 [amd64])\n"
            "Inst libx11-6:amd64 (2:1.8.12-1 Ubuntu:26.04 [amd64])\n"
            "Inst libatk1.0-0t64 (2.58.0-1 Ubuntu:26.04 [amd64])\n"
            "Conf libnss3 (2:3.112-1 Ubuntu:26.04 [amd64])\n"
        )
        self.assertEqual(browser.apt_plan(output), [
            "libatk1.0-0t64=2.58.0-1", "libnss3=2:3.112-1", "libx11-6:amd64=2:1.8.12-1"])

    def test_apt_refuses_removal_malformed_rows_and_core_glibc_changes(self):
        for package in ["libc6", "libc6:amd64", "libc-bin", "libc6-dev", "libc-dev-bin"]:
            with self.subTest(package=package):
                with self.assertRaisesRegex(browser.BrowserError, "glibc"):
                    browser.apt_plan(f"Inst {package} [2.41-1] (2.42-1 Ubuntu [amd64])")
        for row in ["Remv libold [1.0]", "Inst liba", "Inst --unsafe (1.0 Ubuntu [amd64])", "Inst liba (../bad Ubuntu [amd64])"]:
            with self.subTest(row=row):
                with self.assertRaises(browser.BrowserError):
                    browser.apt_plan(row)


class BrowserFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "cache"
        self.info = {
            "project": self.root, "node": "/fixture/node", "cli": "/fixture/project/node_modules/playwright/cli.js",
            "api": "/fixture/project/node_modules/playwright/index.js", "version": "1.64.1", "executable": "/fixture/chromium",
        }
        # Mocked subprocess arguments must never contain the developer's real secrets.
        environment = patch.dict(os.environ, {"PATH": "/fixture/bin", "KEEP_ME": "original"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def ready_runtime(self, digest="a" * 64):
        runtime = self.directory / digest
        (runtime / "root/usr/lib").mkdir(parents=True)
        (runtime / "ready.json").write_text(json.dumps({"format": 1, "packages": ["libold=1.0"]}))
        (self.directory / "active.json").write_text(json.dumps({"runtime": digest}))
        return runtime


class CacheTests(BrowserFixture):
    def test_missing_selector_means_no_cached_runtime(self):
        self.assertIsNone(browser.active_runtime(self.directory))

    def test_active_selector_cannot_escape_cache_or_name_an_incomplete_runtime(self):
        runtime = self.ready_runtime()
        active = self.directory / "active.json"
        for entry in ["invalid json", "[]", "{}", '{"runtime":"../outside"}', '{"runtime":17}', json.dumps({"runtime": "b" * 64})]:
            with self.subTest(entry=entry):
                active.write_text(entry)
                with self.assertRaises(browser.BrowserError):
                    browser.active_runtime(self.directory)
        active.write_text(json.dumps({"runtime": runtime.name}))
        for marker in ["invalid json", "[]", "null", "{}", '{"format":2}']:
            with self.subTest(marker=marker):
                (runtime / "ready.json").write_text(marker)
                with self.assertRaises(browser.BrowserError):
                    browser.active_runtime(self.directory)

    def test_ready_marker_without_payload_is_incomplete(self):
        runtime = self.ready_runtime()
        shutil.rmtree(runtime / "root")
        with self.assertRaisesRegex(browser.BrowserError, "incomplete"):
            browser.active_runtime(self.directory)

    def test_symlinked_selector_runtime_and_cache_ancestor_are_rejected(self):
        runtime = self.ready_runtime()
        outside = self.root / "outside"
        outside.mkdir()
        selector = self.directory / "active.json"
        selector.unlink()
        selector.symlink_to(outside / "missing.json")
        with self.assertRaises(browser.BrowserError):
            browser.active_runtime(self.directory)
        selector.unlink()
        selector.write_text(json.dumps({"runtime": runtime.name}))
        shutil.rmtree(runtime)
        runtime.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(browser.BrowserError):
            browser.active_runtime(self.directory)
        linked_parent = self.root / "linked-cache"
        linked_parent.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(browser.BrowserError):
            browser.active_runtime(linked_parent / "child")

    def test_runtime_environment_is_a_scoped_copy_and_preserves_existing_libraries(self):
        runtime = self.ready_runtime()
        (runtime / "root/lib").mkdir()
        multiarch = runtime / "root/usr/lib/x86_64-linux-gnu"
        multiarch.mkdir()
        fonts = runtime / "fonts.conf"
        fonts.write_text("<fontconfig/>")
        original = {"KEEP_ME": "original", "LD_LIBRARY_PATH": "/existing/lib", "FONTCONFIG_FILE": "/existing/fonts.conf"}
        environment = browser.runtime_environment(runtime, original)
        self.assertIsNot(environment, original)
        self.assertEqual(environment["LD_LIBRARY_PATH"].split(":"), [
            str(runtime / "root/lib"), str(runtime / "root/usr/lib"), str(multiarch), "/existing/lib"])
        self.assertEqual(environment["FONTCONFIG_FILE"], str(fonts))
        self.assertEqual(environment["KEEP_ME"], "original")
        self.assertEqual(original["LD_LIBRARY_PATH"], "/existing/lib")
        self.assertEqual(original["FONTCONFIG_FILE"], "/existing/fonts.conf")
        self.assertNotIn("LD_LIBRARY_PATH", os.environ)
        self.assertNotIn("FONTCONFIG_FILE", os.environ)

    def test_symlinked_payload_library_is_not_added_to_child_environment(self):
        runtime = self.ready_runtime()
        outside = self.root / "outside-libraries"
        outside.mkdir()
        (runtime / "root/usr/lib/x86_64-linux-gnu").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(browser.BrowserError):
            browser.runtime_environment(runtime)


class InstallTests(BrowserFixture):
    def test_unrecognized_playwright_report_does_not_run_apt_or_create_cache(self):
        with patch.object(browser.shutil, "which", return_value="/fixture/tool"), patch.object(browser, "capture", return_value=result(0, "future format")) as capture:
            with self.assertRaises(browser.BrowserError):
                browser.install_user_dependencies(self.info, self.directory)
        self.assertEqual(capture.call_count, 1)
        self.assertFalse(self.directory.exists())

    def test_glibc_plan_does_not_download_or_create_cache(self):
        with patch.object(browser.shutil, "which", return_value="/fixture/tool"), patch.object(browser, "capture", side_effect=[
            result(1, "Missing system dependencies (1):\n  libc6"),
            result(0, "Inst libc6 [2.41-1] (2.42-1 Ubuntu [amd64])"),
        ]) as capture:
            with self.assertRaisesRegex(browser.BrowserError, "glibc"):
                browser.install_user_dependencies(self.info, self.directory)
        self.assertEqual(capture.call_count, 2)
        self.assertFalse(self.directory.exists())

    def test_extraction_failure_keeps_previous_runtime_and_selector(self):
        previous = self.ready_runtime()
        selector = (self.directory / "active.json").read_bytes()

        def capture(args, **kwargs):
            if "install-deps" in args:
                return result(1, "Missing system dependencies (1):\n  libfixture")
            if args[:2] == ["apt-get", "-s"]:
                return result(0, "Inst libfixture (1.0 Ubuntu [amd64])")
            if args[:2] == ["apt-get", "download"]:
                (kwargs["cwd"] / "libfixture_1.0_amd64.deb").write_bytes(b"synthetic archive")
                return result()
            self.assertEqual(args[:2], ["dpkg-deb", "-x"])
            return result(1, stderr="synthetic extraction failure")

        with patch.object(browser.shutil, "which", return_value="/fixture/tool"), patch.object(browser, "capture", side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(browser.BrowserError, "previous runtime was kept"):
                browser.install_user_dependencies(self.info, self.directory)
        self.assertEqual((self.directory / "active.json").read_bytes(), selector)
        self.assertEqual(browser.active_runtime(self.directory), previous)
        expected_digest = hashlib.sha256(b"libfixture=1.0").hexdigest()
        self.assertFalse((self.directory / expected_digest).exists())
        self.assertEqual(list(self.directory.glob(".prepare-*")), [])


class CommandTests(BrowserFixture):
    def main_patches(self, stack):
        stack.enter_context(patch.object(browser, "resolve_project", return_value=self.info))
        stack.enter_context(patch.object(browser, "cache_directory", return_value=self.directory))
        stack.enter_context(patch.object(browser, "active_runtime", return_value=None))

    def test_run_preserves_arguments_and_delegates_process_exit_to_exec(self):
        command = ["pnpm", "test:e2e", "--", "--project=chromium", "name with spaces"]
        child_environment = {"PATH": "/fixture/bin", "SCOPED": "browser-only"}
        with contextlib.ExitStack() as stack:
            self.main_patches(stack)
            stack.enter_context(patch.object(browser, "runtime_environment", return_value=child_environment))
            chdir = stack.enter_context(patch.object(browser.os, "chdir"))
            execute = stack.enter_context(patch.object(browser.os, "execvpe", side_effect=SystemExit(23)))
            with self.assertRaises(SystemExit) as exit_status:
                browser.main(["run", "--", *command])
        self.assertEqual(exit_status.exception.code, 23)
        chdir.assert_called_once_with(self.root)
        execute.assert_called_once_with("pnpm", command, child_environment)
        self.assertNotIn("SCOPED", os.environ)

    def test_empty_run_is_usage_error_and_cannot_execute(self):
        with contextlib.ExitStack() as stack:
            self.main_patches(stack)
            execute = stack.enter_context(patch.object(browser.os, "execvpe"))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            with self.assertRaises(SystemExit) as exit_status:
                browser.main(["run", "--"])
        self.assertEqual(exit_status.exception.code, 2)
        execute.assert_not_called()

    def test_failed_exec_reports_generic_error_and_interrupt_returns_130(self):
        for error, expected in [(OSError("synthetic-private-detail"), 1), (KeyboardInterrupt(), 130)]:
            with self.subTest(expected=expected), contextlib.ExitStack() as stack:
                self.main_patches(stack)
                stack.enter_context(patch.object(browser.os, "chdir"))
                stack.enter_context(patch.object(browser.os, "execvpe", side_effect=error))
                stderr = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                self.assertEqual(browser.main(["run", "--", "test-command"]), expected)
                self.assertNotIn("synthetic-private-detail", stderr.getvalue())

    def test_browser_install_preserves_failed_child_exit_and_signal_status(self):
        for code, expected in [(7, 7), (-15, 143)]:
            with self.subTest(code=code), contextlib.ExitStack() as stack:
                self.main_patches(stack)
                run = stack.enter_context(patch.object(browser.subprocess, "run", return_value=result(code)))
                doctor = stack.enter_context(patch.object(browser, "doctor"))
                self.assertEqual(browser.main(["install"]), expected)
                self.assertEqual(run.call_args.args[0], [self.info["node"], self.info["cli"], "install", "chromium"])
                doctor.assert_not_called()

    def test_doctor_distinguishes_missing_browser_and_launch_failure_without_raw_errors(self):
        for output, message in [("missing-browser", "Chromium is missing"), ("launch-failed", "Chromium could not launch")]:
            with self.subTest(output=output), patch.object(browser, "capture", return_value=result(1, output, "synthetic-private-detail")), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(browser.BrowserError, message) as error:
                    browser.doctor(self.info, {"SCOPED": "value"})
                self.assertNotIn("synthetic-private-detail", str(error.exception))

    def test_doctor_performs_headless_probe_with_scoped_environment(self):
        environment = {"SCOPED": "value"}
        with patch.object(browser, "capture", return_value=result()) as capture, contextlib.redirect_stdout(io.StringIO()) as output:
            browser.doctor(self.info, environment)
        self.assertIn("headless Chromium launched and closed", output.getvalue())
        self.assertEqual(capture.call_args.args[0], [self.info["node"], "-e", browser.PROBE, self.info["api"]])
        self.assertIs(capture.call_args.kwargs["env"], environment)
        self.assertEqual(capture.call_args.kwargs["cwd"], self.root)

    def test_project_resolution_failures_do_not_dump_subprocess_output(self):
        for stdout, code in [("synthetic-private-detail", 1), ("[]", 0), (json.dumps({**self.info, "project": str(self.root)}), 1)]:
            with self.subTest(stdout=stdout), patch.object(browser.shutil, "which", return_value="/fixture/node"), patch.object(browser, "capture", return_value=result(code, stdout, "synthetic-private-detail")):
                with self.assertRaisesRegex(browser.BrowserError, "project-local Playwright") as error:
                    browser.resolve_project(self.root)
                self.assertNotIn("synthetic-private-detail", str(error.exception))

    def test_capture_sanitizes_launch_errors(self):
        with patch.object(browser.subprocess, "Popen", side_effect=OSError("synthetic-private-detail")):
            with self.assertRaises(browser.BrowserError) as sanitized:
                browser.capture(["fixture"])
        self.assertNotIn("synthetic-private-detail", str(sanitized.exception))

    def test_capture_timeout_kills_process_group_and_bounds_cleanup(self):
        for cleanup_times_out in [False, True]:
            process = Mock(pid=12345)
            timeout = subprocess.TimeoutExpired("synthetic-private-detail", 5, output="synthetic-private-detail")
            cleanup = subprocess.TimeoutExpired("fixture", 1) if cleanup_times_out else ("", "")
            process.communicate.side_effect = [timeout, cleanup]
            with self.subTest(cleanup_times_out=cleanup_times_out), patch.object(browser.subprocess, "Popen", return_value=process) as popen, patch.object(browser.os, "killpg") as killpg:
                with self.assertRaisesRegex(browser.BrowserError, "timed out") as sanitized:
                    browser.capture(["fixture"], timeout=5)
            self.assertNotIn("synthetic-private-detail", str(sanitized.exception))
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            killpg.assert_called_once_with(12345, signal.SIGKILL)
            self.assertEqual(process.communicate.call_args_list, [call(timeout=5), call(timeout=1)])
            self.assertEqual(process.stdout.close.call_count, int(cleanup_times_out))
            self.assertEqual(process.stderr.close.call_count, int(cleanup_times_out))

    def test_capture_interrupt_cleans_group_before_propagating(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [KeyboardInterrupt(), ("", "")]
        with patch.object(browser.subprocess, "Popen", return_value=process), patch.object(browser.os, "killpg") as killpg:
            with self.assertRaises(KeyboardInterrupt):
                browser.capture(["fixture"], timeout=5)
        killpg.assert_called_once_with(12345, signal.SIGKILL)
        self.assertEqual(process.communicate.call_args_list, [call(timeout=5), call(timeout=1)])
