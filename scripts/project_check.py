"""Read-only checks for a project's local development prerequisites."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import ssl
import subprocess
import sys
import urllib.error
import urllib.request


COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
LOCKFILES = {
    "pnpm": ("pnpm-lock.yaml",),
    "npm": ("package-lock.json", "npm-shrinkwrap.json"),
    "yarn": ("yarn.lock",),
    "bun": ("bun.lock", "bun.lockb"),
}
PACKAGE_NAME = re.compile(r"^(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_][a-zA-Z0-9_.-]*$")


def clean(value):
    return "".join(character if character.isprintable() else "?" for character in str(value))


def result(check, status, message, hint=""):
    return {"check": check, "status": status, "message": message, "hint": hint}


def command_environment():
    """Preserve proxy/CA settings without loading dotenv or redirecting Git."""
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith("GIT_TRACE") or name in (
            "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
            "COMPOSE_ENV_FILES", "COMPOSE_FILE", "COMPOSE_PROJECT_NAME",
        ):
            environment.pop(name, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["COMPOSE_DISABLE_ENV_FILE"] = "true"
    return environment


def run_command(arguments, *, timeout=5, environment=None):
    """Return (code, bounded output, problem); never return raw stderr."""
    try:
        process = subprocess.Popen(
            arguments, cwd="/", env=environment or command_environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", start_new_session=True,
        )
    except OSError:
        return None, "", "unavailable"
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output[:4096], None
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # Kill the group, including a CLI plugin still holding the output pipe.
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            if process.stdout:
                process.stdout.close()
        if isinstance(error, KeyboardInterrupt):
            raise
        return None, "", "timeout"


def git_root(directory, checks):
    git = shutil.which("git")
    if not git:
        checks.append(result("git", "warn", "Git is not on PATH.", "Install Git or restore your shell PATH."))
        return None
    code, output, problem = run_command([git, "-c", "core.fsmonitor=false", "-C", str(directory), "rev-parse", "--show-toplevel"])
    if problem:
        checks.append(result("git", "fail", "Git inspection timed out or could not run.", "Check the Git executable and checkout permissions."))
        return None
    if code == 0:
        try:
            root = Path(output.strip()).resolve()
            if root == directory or root in directory.parents:
                checks.append(result("git", "pass", "Inside a Git checkout."))
                return root
        except (OSError, RuntimeError, ValueError):
            pass
    checks.append(result("git", "warn", "No Git checkout was identified.", "Run inside the intended checkout, or initialize version control when appropriate."))
    return None


def read_manifest(path):
    # A package.json symlink must not turn this check into an environment-file read.
    if path.resolve().name.startswith(".env"):
        raise ValueError("Environment-file manifest link")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Manifest too large")
    with path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    return manifest


def find_project(directory, boundary, checks):
    ancestors = []
    for candidate in (directory, *directory.parents):
        ancestors.append(candidate)
        if candidate == boundary:
            break
    package = next((parent / "package.json" for parent in ancestors if (parent / "package.json").is_file()), None)
    if package is None:
        checks.append(result("package", "warn", "No package.json found; JavaScript dependency checks are skipped.", "Pass a package or workspace directory if this is a JavaScript project."))
        return None, boundary or directory, {}
    try:
        manifest = read_manifest(package)
    except (OSError, ValueError, RuntimeError):
        checks.append(result("package", "fail", "The nearest package.json is unreadable, invalid or unsafe to inspect.", "Fix the JSON object or file permissions; environment-file links are not followed."))
        return package, package.parent, {}
    manifests = {package.parent: manifest}
    workspace = package.parent
    for parent in ancestors[ancestors.index(package.parent):]:
        candidate = parent / "package.json"
        data = manifests.get(parent)
        if data is None and candidate.is_file():
            try:
                data = read_manifest(candidate)
            except (OSError, ValueError, RuntimeError):
                checks.append(result("workspace", "fail", "An enclosing package.json could not be inspected.", "Fix its JSON or permissions before relying on workspace discovery."))
                break
        if (parent / "pnpm-workspace.yaml").is_file() or (isinstance(data, dict) and data.get("workspaces")):
            workspace = parent
            if data is not None:
                manifests[parent] = data
            break
    checks.append(result("package", "pass", "Selected the nearest package and enclosing workspace."))
    return package, workspace, manifests


def tool_check(name, required, checks, directories=()):
    available = shutil.which(name) or any(
        (directory / "node_modules" / ".bin" / name).is_file()
        and os.access(directory / "node_modules" / ".bin" / name, os.X_OK)
        for directory in directories
    )
    if available:
        checks.append(result(name, "pass", "Executable is available; no toolchain download or version command was attempted."))
    elif required:
        checks.append(result(name, "fail", "Required executable is unavailable.", "Install or activate " + name + " using the project's documented toolchain."))
    else:
        checks.append(result(name, "skip", "Not available and not required by the selected manifests."))


def dependency_checks(package, workspace, manifests, checks):
    if package is None or not manifests:
        for name in ("node", "pnpm", "vp"):
            tool_check(name, False, checks)
        return
    owner = manifests.get(workspace, manifests[package.parent])
    declaration = owner.get("packageManager", "")
    manager = declaration.split("@", 1)[0] if isinstance(declaration, str) else ""
    found = {name: [workspace / filename for filename in filenames if (workspace / filename).is_file()]
             for name, filenames in LOCKFILES.items()}
    if manager not in LOCKFILES:
        manager = "pnpm" if (workspace / "pnpm-workspace.yaml").is_file() else next((name for name, paths in found.items() if paths), "npm")
    locks = found[manager]
    if not locks or not any(path.stat().st_size for path in locks):
        checks.append(result("lockfile", "fail", "A nonempty " + manager + " lockfile is missing.", "Run the reviewed dependency install in the workspace and commit its generated lockfile."))
    else:
        checks.append(result("lockfile", "pass", "The selected package manager has a nonempty lockfile."))
    if sum(bool(paths) for paths in found.values()) > 1:
        checks.append(result("lockfile-selection", "warn", "Multiple package-manager lockfiles exist.", "Confirm the intended manager before installing or changing lockfiles."))

    dependencies = []
    for parent, manifest in manifests.items():
        for field in ("dependencies", "devDependencies"):
            values = manifest.get(field, {})
            if not isinstance(values, dict) or any(not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name) for name in values):
                checks.append(result("dependencies", "fail", "Dependency declarations are not valid package-name mappings.", "Correct dependencies/devDependencies in package.json."))
                return
            dependencies.extend((parent, name) for name in values)
    tool_check("node", True, checks)
    tool_check("pnpm", manager == "pnpm", checks)
    if manager not in ("pnpm",):
        tool_check(manager, True, checks)
    tool_check("vp", any(name == "vite-plus" for _, name in dependencies), checks, (package.parent, workspace))
    if (workspace / ".pnp.cjs").is_file() or (workspace / ".pnp.js").is_file():
        checks.append(result("dependencies", "skip", "Yarn PnP was detected; its loader was not executed.", "Use the project's own dependency verification separately."))
        return
    if not dependencies:
        checks.append(result("dependencies", "skip", "No direct dependencies are declared."))
        return
    missing = 0
    for parent, name in dependencies:
        candidates = []
        for directory in (parent, *parent.parents):
            candidates.append(directory / "node_modules" / name / "package.json")
            if directory == workspace:
                break
        if not any(candidate.is_file() for candidate in candidates):
            missing += 1
    if missing:
        checks.append(result("dependencies", "fail", str(missing) + " declared direct package(s) are absent from node_modules.", "Run the reviewed install in the workspace; an empty node_modules directory is insufficient."))
    else:
        checks.append(result("dependencies", "pass", "Declared direct packages are present; builds and transitive compatibility were not checked."))


def docker_checks(directory, workspace, checks, boundary=None):
    candidates = []
    for parent in (directory, *directory.parents):
        candidates.append(parent)
        if parent == (boundary or workspace):
            break
    compose = next((parent / name for parent in candidates
                    for name in COMPOSE_FILES if (parent / name).is_file()), None)
    if compose is None:
        checks.append(result("docker", "skip", "No standard Compose file detected at the project/workspace root."))
        return
    checks.append(result("compose-file", "pass", "Compose configuration detected; contents and environment files were not loaded."))
    docker = shutil.which("docker")
    if not docker:
        checks.append(result("docker", "fail", "Docker is unavailable for this Compose project.", "Install Docker/Compose, or use the project's documented external-service alternative."))
        return
    environment = command_environment()
    code, _, problem = run_command([docker, "compose", "version", "--short"], environment=environment)
    if code != 0 or problem:
        checks.append(result("compose", "fail", "Docker Compose could not be queried.", "Check the Compose plugin; no Compose configuration was evaluated."))
    else:
        checks.append(result("compose", "pass", "Docker Compose is available."))
    endpoint = environment.get("DOCKER_HOST")
    if environment.get("DOCKER_CONTEXT") or not endpoint:
        code, output, problem = run_command([docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], environment=environment)
        if code != 0 or problem:
            checks.append(result("docker-daemon", "fail", "Docker context inspection failed or timed out.", "Inspect your selected Docker context and local socket access."))
            return
        endpoint = output.strip()
    if not endpoint.startswith("unix:///") or any(character.isspace() for character in endpoint):
        checks.append(result("docker-daemon", "skip", "The selected Docker endpoint is not a local Unix socket; it was not contacted.", "Select a local Docker context to check it without remote access."))
        return
    for variable in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(variable, None)
    code, _, problem = run_command([docker, "--host=" + endpoint, "info", "--format", "{{.ServerVersion}}"], timeout=8, environment=environment)
    if code == 0 and not problem:
        checks.append(result("docker-daemon", "pass", "The selected local Docker daemon responds."))
    else:
        checks.append(result("docker-daemon", "fail", "The local Docker daemon is unavailable, inaccessible or timed out.", "Check socket permissions and daemon health; on WSL enable Docker Desktop integration for this distro."))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def registry_probe():
    """Runs in a separately bounded child so even DNS cannot hang the CLI."""
    try:
        context = ssl.create_default_context()
        for name in ("NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
            if os.environ.get(name):
                context.load_verify_locations(cafile=os.path.expanduser(os.environ[name]))
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(), urllib.request.HTTPSHandler(context=context), NoRedirect(),
        )
        request = urllib.request.Request("https://registry.npmjs.org/-/ping", headers={"User-Agent": "linux-setup/dev-check"})
        with opener.open(request, timeout=6) as response:
            return 0 if response.status == 200 else 1
    except (OSError, ValueError, urllib.error.URLError):
        return 1


def check_project(path=".", *, network=False):
    checks = []
    try:
        directory = Path(path).expanduser().resolve(strict=True)
        if directory.is_file():
            directory = directory.parent
        if not directory.is_dir():
            raise ValueError("Not a directory")
    except (OSError, RuntimeError, ValueError):
        return {"project": None, "package": None, "workspace": None, "ready": False,
                "checks": [result("path", "fail", "The requested project path is unavailable.", "Pass an existing readable project directory.")]}
    boundary = git_root(directory, checks)
    package, workspace, manifests = find_project(directory, boundary, checks)
    dependency_checks(package, workspace, manifests, checks)
    docker_checks(directory, workspace, checks, boundary)
    if shutil.which("psql"):
        checks.append(result("psql", "pass", "PostgreSQL client is available; no database connection was attempted."))
    else:
        checks.append(result("psql", "warn", "Optional PostgreSQL client is not on PATH.", "Install postgresql-client if you need host-side database inspection."))
    if network:
        code, _, problem = run_command([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--_registry-probe"], timeout=10)
        checks.append(result("registry", "pass" if code == 0 and not problem else "fail",
                             "npm registry HTTPS probe succeeded." if code == 0 and not problem else "npm registry HTTPS probe failed or timed out.",
                             "" if code == 0 and not problem else "Check DNS, proxy access and configured CA certificates; keep TLS verification enabled."))
    else:
        checks.append(result("registry", "skip", "External network probe disabled.", "Use --network to check npm registry HTTPS explicitly."))
    return {"project": str(directory), "package": str(package) if package else None,
            "workspace": str(workspace), "ready": not any(item["status"] == "fail" for item in checks), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", metavar="PATH")
    parser.add_argument("--network", action="store_true", help="Explicitly probe npm registry HTTPS using configured proxy/CA trust")
    parser.add_argument("--json", action="store_true", help="Print structured check results")
    arguments = parser.parse_args(argv)
    try:
        report = check_project(arguments.path, network=arguments.network)
    except (OSError, RuntimeError, ValueError):
        report = {"project": None, "package": None, "workspace": None, "ready": False,
                  "checks": [result("inspection", "fail", "Project inspection could not finish.", "Check file permissions and executable availability; no raw command output was printed.")]}
    except KeyboardInterrupt:
        print("dev-check: interrupted.", file=sys.stderr)
        return 130
    if arguments.json:
        print(json.dumps(report))
    else:
        if report["project"]:
            print("Project: " + clean(report["project"]))
            if report["workspace"] != report["project"]:
                print("Workspace: " + clean(report["workspace"]))
        for item in report["checks"]:
            print(f"{item['status'].upper():<4} {item['check']}: {item['message']}")
            if item["hint"]:
                print("     " + item["hint"])
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--_registry-probe"]:
        sys.exit(registry_probe())
    sys.exit(main())
