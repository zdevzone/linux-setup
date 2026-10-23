#!/usr/bin/env python3
"""Use project-pinned Playwright with optional user-local Chromium libraries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape


class BrowserError(Exception):
    pass


PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?\Z")
VERSION = re.compile(r"[A-Za-z0-9.+:~_-]+\Z")
RESOLVE = r"""
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const local = createRequire(path.join(process.cwd(), 'package.json'));
const roots = [];
for (let p = process.cwd();; p = path.dirname(p)) {
  if (fs.existsSync(path.join(p, 'package.json')))
    roots.push(path.join(p, 'node_modules') + path.sep);
  if (p === path.dirname(p)) break;
}
for (const name of ['@playwright/test', 'playwright']) {
  try {
    const cli = local.resolve(name + '/cli');
    const api = local.resolve(name);
    if (![cli, api].every(p => roots.some(root => p.startsWith(root)))) continue;
    const version = local(name + '/package.json').version;
    const executable = local(name).chromium.executablePath();
    console.log(JSON.stringify({cli, api, version, executable}));
    process.exit(0);
  } catch {}
}
process.exit(1);
"""
PROBE = r"""
(async () => {
  let browser;
  try {
    browser = await require(process.argv[1]).chromium.launch({headless: true, timeout: 15000});
    await browser.close();
  } catch (e) {
    // Do not expose inherited environment or full browser command lines.
    console.log(/Executable doesn't exist/.test(String(e)) ? 'missing-browser' : 'launch-failed');
    process.exitCode = 1;
  }
})();
"""


def capture(args, cwd=None, env=None, timeout=60):
    try:
        process = subprocess.Popen(args, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        raise BrowserError("A required command could not start; check Node, APT, and file permissions.") from None
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            process.stdout.close()
            process.stderr.close()
        if isinstance(error, KeyboardInterrupt):
            raise
        raise BrowserError("A browser setup check timed out; retry or inspect the host tools.") from None


def resolve_project(project):
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise BrowserError("Project directory does not exist.")
    node = shutil.which("node")
    if not node:
        raise BrowserError("Node is unavailable. Activate the project's pinned Node runtime first.")
    result = capture([node, "-e", RESOLVE], cwd=project, timeout=20)
    try:
        info = json.loads(result.stdout)
        if result.returncode or not all(isinstance(info[k], str) and info[k] for k in ("cli", "api", "version", "executable")):
            raise ValueError
        if not VERSION.fullmatch(info["version"]):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BrowserError("No usable project-local Playwright found. Install this project's locked dependencies first.") from None
    return dict(info, node=node, project=project)


def dependency_packages(output, returncode):
    """Fail closed when Playwright changes its human-readable dry-run format."""
    if returncode == 0 and output.strip() == "All system dependencies are installed.":
        return []
    lines = output.strip().splitlines()
    match = re.fullmatch(r"Missing system dependencies \(([1-9][0-9]*)\):", lines[0]) if lines else None
    packages = [line[2:] for line in lines[1:] if line.startswith("  ")]
    if (returncode != 1 or not match or len(packages) != int(match[1]) or
            len(lines) != len(packages) + 1 or len(set(packages)) != len(packages) or
            not all(PACKAGE.fullmatch(p) for p in packages)):
        raise BrowserError("Cannot interpret this Playwright dependency report. Use the project's Playwright install-deps chromium with administrator support; no packages were installed.")
    return packages


def apt_plan(output):
    specs = []
    for line in output.splitlines():
        if line.startswith("Remv "):
            raise BrowserError("APT would remove packages. Repair the host package state before continuing.")
        if not line.startswith("Inst "):
            continue
        match = re.match(r"^Inst (\S+)(?: \[[^\]]+\])? \((\S+) ", line)
        if not match or not PACKAGE.fullmatch(match[1]) or not VERSION.fullmatch(match[2]):
            raise BrowserError("Cannot interpret the APT package plan.")
        if match[1].split(":")[0] in ("libc6", "libc-bin", "libc6-dev", "libc-dev-bin"):
            raise BrowserError("These dependencies require a host glibc update. Ask the host administrator to install the system dependencies.")
        specs.append(match[1] + "=" + match[2])
    return sorted(set(specs))


def cache_directory(info):
    try:
        distro = Path("/etc/os-release").read_bytes()
    except OSError:
        distro = b"unknown"
    identity = hashlib.sha256(distro + os.uname().machine.encode() + info["version"].encode()).hexdigest()[:20]
    root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))).expanduser().absolute()
    return root / "linux-setup" / "browser-deps" / identity


def checked_path(path):
    # Refuse redirected cache ancestors, including dangling symlinks.
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise BrowserError("Browser dependency cache contains a symlink; choose a regular XDG_CACHE_HOME directory.")


def active_runtime(directory):
    checked_path(directory)
    active = directory / "active.json"
    if not active.exists():
        if active.is_symlink():
            raise BrowserError("Invalid browser dependency cache selector.")
        return None
    checked_path(active)
    try:
        entry = json.loads(active.read_text())
        digest = entry["runtime"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError
        runtime = directory / digest
        checked_path(runtime)
        marker = runtime / "ready.json"
        checked_path(marker)
        manifest = json.loads(marker.read_text())
        payload = runtime / "root"
        checked_path(payload)
        if not isinstance(manifest, dict) or manifest.get("format") != 1 or not payload.is_dir():
            raise ValueError
        return runtime
    except (OSError, ValueError, TypeError, KeyError):
        raise BrowserError("Browser dependency cache is incomplete. Inspect it and rerun install --user-deps.") from None


def runtime_environment(runtime, original=None):
    environment = dict(os.environ if original is None else original)
    if runtime:
        checked_path(runtime)
        payload = runtime / "root"
        directories = [payload / "lib", payload / "usr/lib"]
        for base in list(directories):
            directories.extend(sorted(base.glob("*-linux-gnu*")))
        libraries = [str(p) for p in directories if p.is_dir()]
        for p in libraries:
            checked_path(Path(p))
        if libraries:
            if environment.get("LD_LIBRARY_PATH"):
                libraries.append(environment["LD_LIBRARY_PATH"])
            environment["LD_LIBRARY_PATH"] = ":".join(libraries)
        fonts = runtime / "fonts.conf"
        checked_path(fonts)
        if fonts.is_file():
            environment["FONTCONFIG_FILE"] = str(fonts)
    return environment


def install_user_dependencies(info, directory):
    if not all(shutil.which(name) for name in ("apt-get", "dpkg-deb")):
        raise BrowserError("User dependencies require Ubuntu/Debian APT and dpkg-deb. Use Playwright's system dependency installation on this host.")
    environment = dict(os.environ, LC_ALL="C")
    report = capture([info["node"], info["cli"], "install-deps", "--dry-run", "chromium"], cwd=info["project"], env=environment)
    packages = dependency_packages(report.stdout, report.returncode)
    if not packages:
        if active_runtime(directory):
            (directory / "active.json").unlink()
        print("System dependencies already installed.")
        return
    plan = capture(["apt-get", "-s", "--no-install-recommends", "install", *packages], env=environment)
    if plan.returncode:
        raise BrowserError("APT could not resolve dependencies. Ask the host administrator to check package indexes and repositories.")
    specs = apt_plan(plan.stdout)
    if not specs:
        raise BrowserError("APT returned no dependency packages; no cache was changed.")
    digest = hashlib.sha256("\n".join(specs).encode()).hexdigest()
    checked_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / digest
    checked_path(target)
    if target.exists():
        marker = target / "ready.json"
        checked_path(marker)
        try:
            manifest = json.loads(marker.read_text())
        except (OSError, ValueError):
            manifest = {}
        checked_path(target / "root")
        if manifest != {"format": 1, "packages": specs} or not (target / "root").is_dir():
            raise BrowserError("An unrecognized dependency cache already occupies this path; retained without changes.")
    else:
        print(f"Preparing {len(specs)} APT packages in the user cache…", flush=True)
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=directory) as temporary:
            staging = Path(temporary)
            downloads = staging / "downloads"
            downloads.mkdir()
            result = capture(["apt-get", "download", *specs], cwd=downloads, env=environment, timeout=600)
            archives = sorted(downloads.glob("*.deb"))
            if result.returncode or len(archives) != len(specs):
                raise BrowserError("APT download failed; the previous runtime was kept. Check repository access and package indexes.")
            prepared = staging / "runtime"
            payload = prepared / "root"
            payload.mkdir(parents=True)
            for archive in archives:
                if capture(["dpkg-deb", "-x", str(archive), str(payload)], timeout=60).returncode:
                    raise BrowserError("Package extraction failed; the previous runtime was kept.")
            # Debian /usr merge packages may contain absolute symlinks. Only use
            # real library directories in runtime_environment, never those aliases.
            for base in (payload / "lib", payload / "lib64"):
                if base.is_symlink():
                    base.unlink()
            fonts = target / "root/usr/share/fonts"
            (prepared / "fonts.conf").write_text(
                '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
                '<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                f'<dir>{escape(str(fonts))}</dir><cachedir>{escape(str(target / "font-cache"))}</cachedir></fontconfig>\n')
            (prepared / "ready.json").write_text(json.dumps({"format": 1, "packages": specs}) + "\n")
            prepared.rename(target)
    # Publish a complete runtime only. Unique temporary names also avoid clashes
    # between independent installs selecting their completed package set.
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".active-", delete=False) as stream:
        json.dump({"runtime": digest}, stream)
        temporary = Path(stream.name)
    temporary.replace(directory / "active.json")


def doctor(info, environment):
    print(f"Project: {info['project']}\nPlaywright: {info['version']}\nCLI: {info['cli']}\nChromium: {info['executable']}")
    probe = capture([info["node"], "-e", PROBE, info["api"]], cwd=info["project"], env=environment, timeout=25)
    if probe.returncode:
        if probe.stdout.strip() == "missing-browser":
            raise BrowserError("Chromium is missing. Run dev-browser install.")
        raise BrowserError("Chromium could not launch. Run dev-browser install --user-deps on Ubuntu/Debian, or inspect the host's browser dependencies and sandbox support.")
    print("PASS: headless Chromium launched and closed successfully.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="project directory (default: current directory)")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("doctor", help="check the pinned browser with a local headless launch")
    install = commands.add_parser("install", help="install project-pinned Chromium")
    install.add_argument("--user-deps", action="store_true", help="extract Ubuntu/Debian dependencies into the user cache")
    run = commands.add_parser("run", help="run a command with cached browser libraries")
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        info = resolve_project(args.project)
        directory = cache_directory(info)
        if args.action == "install":
            if args.user_deps:
                install_user_dependencies(info, directory)
            environment = runtime_environment(active_runtime(directory))
            result = subprocess.run([info["node"], info["cli"], "install", "chromium"], cwd=info["project"], env=environment, check=False)
            if result.returncode:
                return result.returncode if result.returncode > 0 else 128 - result.returncode
            doctor(info, environment)
        elif args.action == "doctor":
            doctor(info, runtime_environment(active_runtime(directory)))
        else:
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                parser.error("run requires a command, for example: run -- pnpm test:e2e")
            environment = runtime_environment(active_runtime(directory))
            os.chdir(info["project"])
            os.execvpe(command[0], command, environment)
        return 0
    except (BrowserError, OSError) as error:
        message = str(error) if isinstance(error, BrowserError) else "A command or cache file could not be accessed. Check installed tools and permissions."
        print("dev-browser: " + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
