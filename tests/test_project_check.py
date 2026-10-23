import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("project_check", ROOT / "scripts/project_check.py")
project_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project_check)


class ProjectCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.which = patch.object(project_check.shutil, "which", side_effect=lambda name: "/usr/bin/" + name)
        self.which.start()

    def tearDown(self):
        self.which.stop()
        self.temporary.cleanup()

    def write_package(self, directory=None, **values):
        directory = directory or self.root
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "package.json").write_text(json.dumps(values))
        return directory

    def commands(self, arguments, **kwargs):
        if "rev-parse" in arguments:
            return 0, str(self.root), None
        if "context" in arguments:
            return 0, "unix:///var/run/docker.sock", None
        return 0, "", None

    def check(self, path=None, **kwargs):
        with patch.object(project_check, "run_command", side_effect=self.commands):
            return project_check.check_project(path or self.root, **kwargs)

    def statuses(self, report):
        return {item["check"]: item["status"] for item in report["checks"]}

    def test_missing_lockfile_and_empty_node_modules_are_reported(self):
        self.write_package(packageManager="pnpm@12.15.0", dependencies={"react": "19.3.1"})
        (self.root / "node_modules").mkdir()
        report = self.check()
        self.assertFalse(report["ready"])
        self.assertEqual(self.statuses(report)["lockfile"], "fail")
        self.assertEqual(self.statuses(report)["dependencies"], "fail")

    def test_nested_package_selects_workspace_lock_and_installed_direct_dependencies(self):
        self.write_package(packageManager="pnpm@12.15.0")
        (self.root / "pnpm-workspace.yaml").write_text("packages: ['apps/*']\n")
        (self.root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
        app = self.write_package(self.root / "apps/web", dependencies={"react": "19.3.1"})
        dependency = self.root / "node_modules/react"
        dependency.mkdir(parents=True)
        (dependency / "package.json").write_text("{}")
        report = self.check(app)
        self.assertEqual(report["package"], str(app / "package.json"))
        self.assertEqual(report["workspace"], str(self.root))
        self.assertTrue(report["ready"])

    def test_nested_non_javascript_project_checks_compose_at_git_root(self):
        nested = self.root / "src" / "service"
        nested.mkdir(parents=True)
        (self.root / "compose.yaml").write_text("services: {}\n")
        with patch.object(project_check.shutil, "which", side_effect=lambda name: None if name == "docker" else "/usr/bin/" + name):
            report = self.check(nested)
        self.assertEqual(report["project"], str(nested))
        self.assertEqual(report["workspace"], str(self.root))
        self.assertEqual(self.statuses(report)["compose-file"], "pass")
        self.assertEqual(self.statuses(report)["docker"], "fail")
        self.assertFalse(report["ready"])

    def test_invalid_json_does_not_leak_contents_or_exception(self):
        (self.root / "package.json").write_text('{"token":"super-private-token", invalid')
        report = self.check()
        self.assertFalse(report["ready"])
        self.assertEqual(self.statuses(report)["package"], "fail")
        self.assertNotIn("super-private-token", json.dumps(report))

    def test_no_environment_file_reads_or_project_commands(self):
        self.write_package(scripts={"preinstall": "touch SHOULD_NOT_EXIST"})
        (self.root / "package-lock.json").write_text("{}")
        (self.root / ".env").write_text("TOKEN=super-private-token\n")
        (self.root / "compose.yaml").write_text("services: {}\n")
        original_open = Path.open
        opened = []

        def guarded_open(path, *args, **kwargs):
            self.assertFalse(path.name.startswith(".env"))
            opened.append(path)
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open), patch.object(project_check, "run_command", side_effect=self.commands) as execute:
            report = project_check.check_project(self.root)
        self.assertEqual(opened, [self.root / "package.json"])
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())
        self.assertNotIn("super-private-token", json.dumps(report))
        for call in execute.call_args_list:
            arguments = call.args[0]
            self.assertNotIn("install", arguments)
            self.assertNotIn("config", arguments)
            self.assertNotIn("--_registry-probe", arguments)
            self.assertNotEqual(Path(arguments[0]).name, "pnpm")
            self.assertNotEqual(Path(arguments[0]).name, "vp")

    def test_environment_file_manifest_symlink_is_not_read(self):
        environment = self.root / ".env"
        environment.write_text('{"private":"secret"}')
        (self.root / "package.json").symlink_to(environment)
        with patch.object(Path, "open", side_effect=AssertionError("No file should be opened")):
            report = self.check()
        self.assertEqual(self.statuses(report)["package"], "fail")

    def test_local_docker_failure_is_safe_and_actionable(self):
        (self.root / "compose.yaml").write_text("services: {}\n")

        def commands(arguments, **kwargs):
            if "info" in arguments:
                self.assertNotIn("DOCKER_CONTEXT", kwargs["environment"])
                self.assertEqual(kwargs["environment"]["COMPOSE_DISABLE_ENV_FILE"], "true")
                return 1, "password=super-private-token", None
            return self.commands(arguments, **kwargs)

        with patch.dict(os.environ, {"DOCKER_CONTEXT": "local-test", "COMPOSE_ENV_FILES": str(self.root / ".env")}), patch.object(project_check, "run_command", side_effect=commands):
            report = project_check.check_project(self.root)
        encoded = json.dumps(report)
        self.assertNotIn("super-private-token", encoded)
        self.assertIn("WSL", encoded)
        self.assertEqual(self.statuses(report)["docker-daemon"], "fail")

    def test_remote_docker_context_is_never_contacted(self):
        (self.root / "compose.yml").write_text("services: {}\n")

        def commands(arguments, **kwargs):
            self.assertNotIn("info", arguments)
            if "context" in arguments:
                return 0, "ssh://private-user@private-host", None
            return self.commands(arguments, **kwargs)

        with patch.dict(os.environ, {"DOCKER_CONTEXT": "remote"}), patch.object(project_check, "run_command", side_effect=commands):
            report = project_check.check_project(self.root)
        self.assertEqual(self.statuses(report)["docker-daemon"], "skip")
        self.assertNotIn("private-host", json.dumps(report))

    def test_network_is_opt_in_and_bounded(self):
        with patch.object(project_check, "run_command", side_effect=self.commands) as execute:
            project_check.check_project(self.root)
            self.assertFalse(any("--_registry-probe" in call.args[0] for call in execute.call_args_list))
            report = project_check.check_project(self.root, network=True)
        network = [call for call in execute.call_args_list if "--_registry-probe" in call.args[0]]
        self.assertEqual(len(network), 1)
        self.assertEqual(network[0].kwargs["timeout"], 10)
        self.assertEqual(self.statuses(report)["registry"], "pass")

    def test_registry_probe_uses_verified_https_and_does_not_expose_proxy_errors(self):
        context = Mock()
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError("https://user:super-private-token@proxy")
        with patch.object(project_check.ssl, "create_default_context", return_value=context), patch.object(project_check.urllib.request, "build_opener", return_value=opener), patch.dict(os.environ, {"NODE_EXTRA_CA_CERTS": "/tmp/public-ca.pem"}, clear=True), patch.object(project_check.sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(project_check.registry_probe(), 1)
        context.load_verify_locations.assert_called_once_with(cafile="/tmp/public-ca.pem")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://registry.npmjs.org/-/ping")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 6)
        self.assertEqual(output.getvalue(), "")

    def test_subprocess_timeout_kills_owned_group_and_discards_partial_output(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired(["docker"], 5, output="super-private-token"), ("", None)]
        with patch.object(project_check.subprocess, "Popen", return_value=process) as launch, patch.object(project_check.os, "killpg") as kill:
            self.assertEqual(project_check.run_command(["docker", "info"]), (None, "", "timeout"))
        kill.assert_called_once_with(12345, signal.SIGKILL)
        self.assertEqual(launch.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(launch.call_args.kwargs["start_new_session"])

    def test_tool_availability_does_not_execute_package_manager_shims(self):
        self.write_package(packageManager="pnpm@12.15.0", devDependencies={"vite-plus": "1.4.0"})
        with patch.object(project_check.shutil, "which", side_effect=lambda name: None if name in ("node", "pnpm", "vp") else "/usr/bin/" + name):
            report = self.check()
        statuses = self.statuses(report)
        self.assertEqual((statuses["node"], statuses["pnpm"], statuses["vp"]), ("fail", "fail", "fail"))

    def test_json_output_and_nonzero_status_for_failed_checks(self):
        (self.root / "package.json").write_text("invalid")
        with patch.object(project_check, "run_command", side_effect=self.commands), patch.object(project_check.sys, "stdout", new_callable=io.StringIO) as output:
            code = project_check.main(["--json", str(self.root)])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())["ready"])


if __name__ == "__main__":
    unittest.main()
