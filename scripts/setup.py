#!/usr/bin/env python3
"""Install pinned terminal tools and link this checkout's configuration."""
import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ownership import atomic_json, fingerprint, infer_programs, migrate

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "linux-setup"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "linux-setup"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "linux-setup"
BIN = HOME / ".local/bin"
TOOLS = {"ripgrep": "rg", "oh-my-posh": "oh-my-posh"}
BASE = ["zsh", "tmux", "file", "git", "curl", "lsof", "psql"]


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def find_tool(name):
    """Find managers even before a fresh shell has sourced their environment."""
    executable = shutil.which(name)
    if executable:
        return executable
    candidates = []
    if name == "vp":
        for variable in ["VP_BIN_DIR", "VP_HOME"]:
            if os.environ.get(variable):
                base = Path(os.environ[variable]).expanduser()
                candidates.append(base / ("bin/vp" if variable == "VP_HOME" else "vp"))
        candidates += [DATA.parent / "vite-plus/bin/vp", HOME / ".vite-plus/bin/vp"]
    elif name in ["uv", "uvx"]:
        if os.environ.get("UV_INSTALL_DIR"):
            candidates.append(Path(os.environ["UV_INSTALL_DIR"]).expanduser() / name)
        candidates += [BIN / name, HOME / ".cargo/bin" / name]
    return next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def platform_key():
    arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(platform.machine(), platform.machine())
    key = f"{platform.system().lower()}-{arch}"
    if key not in ("linux-x86_64", "linux-aarch64"):
        raise RuntimeError(f"Unsupported platform: {key}. Use Linux on x86_64/ARM64; native Windows and macOS are not supported.")
    return key


def download(url, digest, name):
    """Cache downloads by content, and verify every artifact before using it."""
    target = CACHE / "downloads" / (digest[:16] + "-" + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return target
    for attempt in range(3):
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "linux-setup/1"})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out)
            actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if actual != digest:
                raise RuntimeError(f"Checksum mismatch for {name}: expected {digest}, got {actual}")
            temporary.replace(target)
            return target
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def extract_executables(archive, destination, names):
    """Read just the requested regular files; never extract archive paths/links."""
    found = set()
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = PurePosixPath(member.filename).name
                if name in names and not member.is_dir():
                    if name in found:
                        raise RuntimeError(f"Duplicate executable in archive: {name}")
                    (destination / name).write_bytes(bundle.read(member))
                    found.add(name)
    else:
        with tarfile.open(archive, "r:*") as bundle:
            for member in bundle:
                name = PurePosixPath(member.name).name
                if name in names and member.isfile():
                    if name in found:
                        raise RuntimeError(f"Duplicate executable in archive: {name}")
                    with bundle.extractfile(member) as source:
                        (destination / name).write_bytes(source.read())
                    found.add(name)
    if found != set(names):
        raise RuntimeError(f"Missing executables in {archive.name}: {set(names) - found}")
    for name in found:
        (destination / name).chmod(0o755)


def extract_plugin(archive, destination, strip_root=True):
    destination.mkdir(parents=True, exist_ok=True)
    links = []
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts[1:] if strip_root else PurePosixPath(member.name).parts
            if not parts:
                continue
            if ".." in parts or PurePosixPath(member.name).is_absolute():
                raise RuntimeError("Unsafe path in plugin archive")
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source:
                    target.write_bytes(source.read())
            elif member.issym():
                links.append((target, member.linkname))
            else:
                raise RuntimeError("Hard links and special files are not supported in plugin archives")
    for target, link in links:
        resolved = (target.parent / link).resolve()
        if not resolved.is_relative_to(destination.resolve()):
            raise RuntimeError("Unsafe symlink in plugin archive")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(link)


def migrate_legacy():
    migrate(sys.modules[__name__] if __name__ in sys.modules else type("Settings", (), globals()))


class Deployment:
    def __init__(self, read_only=False):
        self.read_only = read_only
        if not read_only:
            STATE.mkdir(parents=True, exist_ok=True)
        self.path = STATE / "deployment.json"
        legacy = STATE.parent / "dev-setup/deployment.json"
        source = self.path if self.path.exists() else legacy
        self.state = json.loads(source.read_text()) if source.exists() else {"links": {}}
        infer_programs(type("Settings", (), globals()), self.state)
        self.backup_dir = STATE / "backups" / time.strftime("%Y%m%d-%H%M%S")
        finalize_vp(self, save=False)

    def save(self):
        if self.read_only:
            raise RuntimeError("Cannot save a read-only deployment")
        atomic_json(self.path, self.state)

    def record_program(self, name, *, kind="tool", paths=(), shared=(), version="", binaries=(), owned=True, refresh=False, **metadata):
        previous = self.state["programs"].get(name, {})
        # A previously external program is never silently adopted.
        item = {**previous, "owned": owned, "kind": kind, "version": version, "binaries": list(binaries)}
        item["paths"] = sorted(set(previous.get("paths", []) + [str(p) for p in paths])) if owned else []
        item["shared"] = sorted(set(previous.get("shared", []) + [str(p) for p in shared])) if owned else []
        item["fingerprints"] = dict(previous.get("fingerprints", {}))
        for path in paths:
            if refresh or str(path) not in item["fingerprints"]:
                item["fingerprints"][str(path)] = fingerprint(path)
        item.update(metadata)
        self.state["programs"][name] = item
        self.save()

    def link(self, source, target, program=None):
        source, target = Path(source).absolute(), Path(target).absolute()
        if source == target:
            return
        if target.is_symlink() and os.readlink(target) == str(source):
            if str(target) in self.state["links"] and program:
                self.state["links"][str(target)]["program"] = program
                self.save()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = self.state["links"].get(str(target))
        # Repoint links installed by this repository when the checkout is moved.
        owned = previous and target.is_symlink() and os.readlink(target) == previous["source"]
        backup = previous.get("backup") if owned else None
        if target.exists() or target.is_symlink():
            if owned:
                target.unlink()
            else:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = self.backup_dir / (str(len(list(self.backup_dir.iterdir()))) + "-" + target.name)
                shutil.move(str(target), str(backup_path))
                backup = str(backup_path)
        target.symlink_to(source, target_is_directory=source.is_dir())
        self.state["links"][str(target)] = {"source": str(source), "backup": backup}
        if program:
            self.state["links"][str(target)]["program"] = program
        self.save()

    def restore(self, targets=None):
        unresolved = []
        for target_name, item in reversed(list(self.state["links"].items())):
            if targets is not None and target_name not in targets:
                continue
            target = Path(target_name)
            missing = not target.exists() and not target.is_symlink()
            if not missing and (not target.is_symlink() or os.readlink(target) != item["source"]):
                print(f"Keeping changed path: {target}")
                unresolved.append(target_name)
                continue
            if not missing:
                target.unlink()
            if item.get("backup") and (Path(item["backup"]).exists() or Path(item["backup"]).is_symlink()):
                shutil.move(item["backup"], str(target))
            del self.state["links"][target_name]
            self.save()
        return unresolved


def install_base(deploy):
    missing = [tool for tool in BASE if not shutil.which(tool)]
    # Replace the earlier rootless Zsh runtime with one managed by linux-setup.
    legacy = HOME / ".local/share/zsh-runtime"
    zsh = shutil.which("zsh")
    if zsh and legacy in Path(zsh).resolve().parents and not Path("/usr/bin/zsh").exists():
        missing.append("zsh")
    for name in BASE:
        if name not in missing and name not in deploy.state["programs"]:
            deploy.record_program(name, kind="base", owned=False, binaries=[name], executable=shutil.which(name))
    if not missing:
        prepare_retained_zsh(deploy)
        return
    if not shutil.which("apt-get"):
        raise RuntimeError(f"Install these with your package manager, then rerun: {' '.join(missing)}")
    print("Installing base dependencies without sudo:", ", ".join(missing), flush=True)
    # Keep each base tool's package set independent for selective removal.
    for name in missing:
        requested = "postgresql-client" if name == "psql" else name
        simulation = run(["apt-get", "-s", "--no-install-recommends", "install", requested], capture_output=True, text=True)
        packages = re.findall(r"^Inst (\S+) \((\S+)", simulation.stdout, re.MULTILINE)
        if not packages:
            raise RuntimeError(f"APT found no downloadable packages for {name}; check PATH and refresh APT indexes")
        folder = DATA / "base" / name
        runtime = folder / "runtime"
        previous = deploy.state["programs"].get(name, {})
        expected = previous.get("fingerprints", {}).get(str(folder))
        if folder.exists() and (not expected or fingerprint(folder) != expected):
            raise RuntimeError(f"Keeping modified or untracked base installation: {folder}")
        runtime.mkdir(parents=True, exist_ok=True)
        deploy.record_program(name, kind="base", paths=[folder], binaries=[name], version="installing", packages=dict(packages))
        try:
            with tempfile.TemporaryDirectory(prefix="linux-setup-apt-") as temporary:
                run(["apt-get", "download", *(f"{package}={version}" for package, version in packages)], cwd=temporary)
                for package in sorted(Path(temporary).glob("*.deb")):
                    run(["dpkg-deb", "-x", package, runtime])
            wrapper = write_base_wrapper(name, runtime, folder / "bin")
            deploy.link(wrapper, BIN / name, program=name)
        except BaseException:
            deploy.record_program(name, kind="base", paths=[folder], binaries=[name], version="incomplete", packages=dict(packages), refresh=True)
            raise
        deploy.record_program(name, kind="base", paths=[folder], binaries=[name], version="distro", packages=dict(packages), refresh=True)
    prepare_retained_zsh(deploy)


def write_base_wrapper(name, runtime, wrappers):
    libraries = [p for p in (runtime / "usr/lib").glob("*-linux-gnu") if p.is_dir()]
    wrappers.mkdir(parents=True, exist_ok=True)
    if name == "psql":
        # Debian's cluster wrapper assumes a system installation.
        choices = sorted((runtime / "usr/lib/postgresql").glob("*/bin/psql"), key=lambda p: int(p.parents[1].name), reverse=True)
    else:
        choices = [runtime / "usr/bin" / name, runtime / "bin" / name, runtime / "usr/sbin" / name]
    binary = next((p for p in choices if p.exists()), None)
    if not binary:
        raise RuntimeError(f"No executable installed for {name}")
    script = "#!/bin/sh\n"
    if libraries:
        prefix = ":".join(map(str, libraries))
        script += f"export LD_LIBRARY_PATH={shlex.quote(prefix)}${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}\n"
    if name == "file":
        magic = next((p for p in [runtime / "usr/lib/file/magic.mgc", runtime / "usr/share/misc/magic.mgc"] if p.is_file() and not p.is_symlink()), None)
        if magic:
            script += f"export MAGIC={shlex.quote(str(magic))}\n"
    if name == "git":
        script += f"export GIT_EXEC_PATH={shlex.quote(str(runtime / 'usr/lib/git-core'))}\n"
        script += f"export GIT_TEMPLATE_DIR={shlex.quote(str(runtime / 'usr/share/git-core/templates'))}\n"
    if name == "zsh":
        bootstrap = wrappers / "zsh-bootstrap"
        bootstrap.mkdir(exist_ok=True)
        modules = [p for p in (runtime / "usr/lib").glob("*/zsh/*") if p.is_dir()]
        modules += [p for p in (runtime / "usr/lib/zsh").glob("*") if p.is_dir()]
        functions = [p for p in (runtime / "usr/share/zsh/functions").glob("*") if p.is_dir()]
        vendor = Path("/usr/share/zsh/vendor-completions")
        completion_fix = ""
        if vendor.is_dir() and any(p.is_symlink() and not p.exists() for p in vendor.iterdir()):
            clean = bootstrap / "vendor-completions"
            clean.mkdir(exist_ok=True)
            for source in vendor.iterdir():
                target = clean / source.name
                if source.is_file() and not target.exists() and not target.is_symlink():
                    target.symlink_to(source)
            completion_fix = f"fpath=({shlex.quote(str(clean))} ${{fpath:#/usr/share/zsh/vendor-completions}})\n"
        (bootstrap / ".zshenv").write_text(
            "# Runtime support, independent of linux-setup's interactive configuration.\n"
            + "module_path=(" + " ".join(shlex.quote(str(p)) for p in modules) + " $module_path)\n"
            + "fpath=(" + " ".join(shlex.quote(str(p)) for p in functions) + " $fpath)\n"
            + completion_fix
            + 'ZDOTDIR="${_LINUX_SETUP_USER_ZDOTDIR:-$HOME}"\nunset _LINUX_SETUP_USER_ZDOTDIR\n'
            + '[[ -r "$ZDOTDIR/.zshenv" ]] && source "$ZDOTDIR/.zshenv"\nreturn 0\n')
        script += 'export _LINUX_SETUP_USER_ZDOTDIR="${ZDOTDIR:-$HOME}"\n'
        script += f"export ZDOTDIR={shlex.quote(str(bootstrap))}\n"
    script += f'exec {shlex.quote(str(binary))} "$@"\n'
    wrapper = wrappers / name
    wrapper.write_text(script)
    wrapper.chmod(0o755)
    return wrapper


def prepare_retained_zsh(deploy):
    item = deploy.state["programs"].get("zsh", {})
    wrapper = DATA / "wrappers/zsh"
    if item.get("owned") and wrapper.is_file() and (DATA / "runtime").is_dir():
        checked = [wrapper, DATA / "wrappers/zsh-bootstrap"]
        if any(item.get("fingerprints", {}).get(str(path)) and fingerprint(path) != item["fingerprints"][str(path)] for path in checked):
            print("Keeping modified Zsh wrapper; review standalone runtime support before uninstall.")
            return
        write_base_wrapper("zsh", DATA / "runtime", DATA / "wrappers")
        deploy.record_program("zsh", kind="base", paths=[wrapper, DATA / "wrappers/zsh-bootstrap"],
                              shared=[DATA / "runtime"], binaries=["zsh"], version=item.get("version", "legacy"), refresh=True)


def install_tools(lock, key, deploy):
    for name, item in lock["tools"].items():
        if item.get("install_if_missing"):
            existing = find_tool(TOOLS.get(name, name))
            if existing:
                run([existing, "--version"], capture_output=True, text=True)
                print(f"{name}: keeping existing installation ({existing})", flush=True)
                # Finish a previously interrupted first-time Vite+ setup.
                if name == "vp" and Path(existing).resolve().is_relative_to(DATA / "tools/vp"):
                    if not (CONFIG / "vite-plus/env").is_file():
                        prepare_vp(Path(existing), deploy)
                if isinstance(deploy.state, dict) and name not in deploy.state["programs"]:
                    deploy.record_program(name, owned=False, binaries=item.get("binaries", [name]), executable=existing)
                continue
        asset = item["platforms"].get(key)
        if not asset:
            raise RuntimeError(f"No {name} build for {key}")
        binaries = item.get("binaries", [TOOLS.get(name, name)])
        destination = DATA / "tools" / name / (item["version"] + "-" + key)
        stamp = destination / ".sha256"
        changed = not stamp.exists() or stamp.read_text().strip() != asset["sha256"] or not all((destination / n).exists() for n in binaries)
        if changed:
            print(f"Downloading {name} {item['version']} ...", flush=True)
            archive = download(asset["url"], asset["sha256"], asset["name"])
            with tempfile.TemporaryDirectory(prefix="linux-setup-tool-") as temporary:
                stage = Path(temporary)
                if item.get("preserve_bundle"):
                    extract_plugin(archive, stage, strip_root=False)
                    for binary in binaries:
                        (stage / binary).chmod(0o755)
                elif asset["name"].endswith((".tar.gz", ".zip", ".tgz")):
                    extract_executables(archive, stage, binaries)
                else:
                    shutil.copy2(archive, stage / binaries[0])
                    (stage / binaries[0]).chmod(0o755)
                destination.mkdir(parents=True, exist_ok=True)
                if item.get("preserve_bundle"):
                    shutil.copytree(stage, destination, dirs_exist_ok=True, symlinks=True)
                else:
                    for binary in binaries:
                        shutil.copy2(stage / binary, destination / binary)
                stamp.write_text(asset["sha256"] + "\n")
        deploy.record_program(name, paths=[destination], version=item["version"], binaries=binaries, refresh=changed)
        if name == "vp":
            # Generate the official shell environment and runtime/PM shims.
            # Point them at the durable binary store, not a removable config link.
            prepare_vp(destination / "vp", deploy)
            if changed:
                deploy.record_program(name, paths=[destination], version=item["version"], binaries=binaries, refresh=True)
        for binary in binaries:
            deploy.link(destination / binary, BIN / binary, program=name)
        print(f"{name}: {item['version']}", flush=True)
    for name, item in lock["plugins"].items():
        destination = DATA / "plugins" / name / item["commit"]
        stamp = destination / ".sha256"
        changed = not stamp.exists() or stamp.read_text().strip() != item["sha256"]
        if changed:
            print(f"Downloading {name} {item['version']} ...", flush=True)
            archive = download(item["url"], item["sha256"], name + ".tar.gz")
            with tempfile.TemporaryDirectory(prefix="linux-setup-plugin-") as temporary:
                stage = Path(temporary)
                extract_plugin(archive, stage)
                shutil.copytree(stage, destination, dirs_exist_ok=True, symlinks=True)
            stamp.write_text(item["sha256"] + "\n")
        deploy.record_program(name, kind="plugin", paths=[destination], version=item["commit"], refresh=changed)
        deploy.link(destination, DATA / "plugins" / name / "current", program=name)


def prepare_vp(executable, deploy):
    """Track only changed environment/shim files, never downloaded runtimes."""
    roots = [CONFIG / "vite-plus", DATA.parent / "vite-plus/bin"]
    before = {}
    for root in roots:
        if root.is_dir() and not root.is_symlink():
            for path in root.rglob("*"):
                if path.is_file() or path.is_symlink():
                    before[str(path)] = fingerprint(path)
    # Mock deployments in download tests have no persistent inventory.
    real = isinstance(deploy.state, dict)
    backups = {}
    if real:
        for name, value in before.items():
            path = Path(name)
            backup = deploy.backup_dir / ("vp-" + hashlib.sha256(name.encode()).hexdigest()[:16])
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists() and not backup.is_symlink():
                if path.is_symlink():
                    backup.symlink_to(os.readlink(path))
                else:
                    shutil.copy2(path, backup)
            backups[name] = str(backup)
        deploy.state["programs"]["vp"]["pending_external"] = {"before": before, "backups": backups}
        deploy.save()
    try:
        run([executable, "env", "setup"], env={**os.environ, "VP_SELF_SETUP_NO_MODIFY_PATH": "1", "CI": "1"})
    finally:
        if real:
            finalize_vp(deploy)


def finalize_vp(deploy, save=True):
    """Account for Vite+ side effects even after failure or a killed installer."""
    item = deploy.state.get("programs", {}).get("vp", {})
    pending = item.get("pending_external")
    if not pending:
        return
    before, backups = pending["before"], pending["backups"]
    current = {}
    for root in [CONFIG / "vite-plus", DATA.parent / "vite-plus/bin"]:
        if root.is_dir() and not root.is_symlink():
            for path in root.rglob("*"):
                if path.is_file() or path.is_symlink():
                    current[str(path)] = fingerprint(path)
    files = item.setdefault("external_files", {})
    for name in sorted(set(before) | set(current)):
        if before.get(name) == current.get(name):
            continue
        path = Path(name)
        backup = files.get(name, {}).get("backup", backups.get(name))
        expected = {"backup": backup}
        if path.is_symlink():
            expected["symlink"] = os.readlink(path)
        elif name in current:
            expected["sha256"] = current[name].removeprefix("file:")
        files[name] = expected
    item.pop("pending_external", None)
    if save:
        deploy.save()


def install_config(deploy):
    # Migrate the known addition from the earlier setup without executing or
    # copying arbitrary shell startup files into a public repository.
    previous_env = HOME / ".zshenv"
    migrate_vite = previous_env.exists() and "vite-plus/env" in previous_env.read_text()
    deploy.link(ROOT, CONFIG / "linux-setup")
    for source, target in [
        ("config/zsh/zshenv", HOME / ".zshenv"),
        ("config/zsh/zshrc", HOME / ".zshrc"),
        ("config/tmux/tmux.conf", HOME / ".tmux.conf"),
        ("config/oh-my-posh", CONFIG / "oh-my-posh"),
        ("config/bat", CONFIG / "bat"),
        ("config/yazi", CONFIG / "yazi"),
        ("config/lazygit", CONFIG / "lazygit"),
    ]:
        deploy.link(ROOT / source, target)
    for script in sorted((ROOT / "bin").iterdir()):
        if script.is_file():
            deploy.link(script, BIN / script.name)
    includes = subprocess.run(["git", "config", "--global", "--get-all", "include.path"], capture_output=True, text=True)
    include = str(CONFIG / "linux-setup/config/git/gitconfig")
    previous_includes = {deploy.state.get("git_include")}
    if str(CONFIG / "dev-setup") in deploy.state["links"]:
        previous_includes.add(str(CONFIG / "dev-setup/config/git/gitconfig"))
    for previous in previous_includes - {None, include}:
        if previous in includes.stdout.splitlines():
            run(["git", "config", "--global", "--fixed-value", "--unset-all", "include.path", previous])
    if include not in includes.stdout.splitlines():
        run(["git", "config", "--global", "--add", "include.path", include])
        deploy.state["git_include"] = include
        deploy.save()
    # Keep local tool initialization outside the portable repository.
    local = CONFIG / "linux-setup-local"
    local.mkdir(parents=True, exist_ok=True)
    for name in ["zshenv", "zshrc"]:
        target = local / name
        if not target.exists():
            target.write_text("# Machine-specific shell additions; never committed to linux-setup.\n")
    if migrate_vite:
        target = local / "zshenv"
        if "vite-plus/env" not in target.read_text():
            with target.open("a") as stream:
                stream.write('\nif [[ -r "$XDG_CONFIG_HOME/vite-plus/env" ]]; then\n  source "$XDG_CONFIG_HOME/vite-plus/env"\nfi\n')
    legacy_history = HOME / ".zsh_history"
    history = STATE.parent / "zsh/history"
    history_marker = STATE / ".history-migrated"
    if legacy_history.is_file() and not history_marker.exists():
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("ab") as stream:
            if history.stat().st_size:
                stream.write(b"\n")
            stream.write(legacy_history.read_bytes())
        history_marker.touch()
    # Filter dangling host completions without modifying system directories.
    vendor = Path("/usr/share/zsh/vendor-completions")
    if vendor.is_dir() and any(p.is_symlink() and not p.exists() for p in vendor.iterdir()):
        clean = DATA / "completions/vendor"
        clean.mkdir(parents=True, exist_ok=True)
        for source in vendor.iterdir():
            target = clean / source.name
            if source.is_file() and not target.exists() and not target.is_symlink():
                target.symlink_to(source)


def install_mcp(deploy=None):
    codex = shutil.which("codex")
    if codex:
        deploy = deploy or Deployment()
        existing = subprocess.run([codex, "mcp", "get", "oh-my-posh", "--json"], capture_output=True, text=True)
        if existing.returncode == 0:
            print("Keeping existing Oh My Posh MCP registration.")
            if "mcp" not in deploy.state:
                deploy.state["mcp"] = {"name": "oh-my-posh", "owned": False}
                deploy.save()
            return
        if "No MCP server named" not in existing.stderr and "No MCP server named" not in existing.stdout:
            raise RuntimeError("Could not inspect existing MCP configuration; leaving it unchanged. Use --skip-mcp to continue.")
        run([codex, "mcp", "add", "oh-my-posh", "--url", "https://ohmyposh.dev/api/mcp"])
        created = run([codex, "mcp", "get", "oh-my-posh", "--json"], capture_output=True, text=True)
        digest = hashlib.sha256(json.dumps(json.loads(created.stdout), sort_keys=True).encode()).hexdigest()
        deploy.state["mcp"] = {"name": "oh-my-posh", "url": "https://ohmyposh.dev/api/mcp", "owned": True, "fingerprint": digest}
        deploy.save()
    else:
        print("Codex is not installed; MCP setup skipped. Run ./install.sh --mcp-only after installing Codex.")


def doctor():
    failed = []
    commands = {**{TOOLS.get(n, n): "--version" for n in json.loads((ROOT / "tools.lock.json").read_text())["tools"]},
                "zsh": "--version", "tmux": "-V", "file": "--version", "git": "--version", "psql": "--version"}
    for name, flag in commands.items():
        executable = find_tool(name)
        if not executable:
            print(f"MISSING {name}")
            failed.append(name)
            continue
        result = subprocess.run([executable, flag], capture_output=True, text=True)
        line = (result.stdout or result.stderr).splitlines()
        print(f"{'OK' if result.returncode == 0 else 'FAIL':7} {name:12} {line[0] if line else executable}")
        if result.returncode:
            failed.append(name)
    zsh = shutil.which("zsh")
    if zsh:
        result = subprocess.run([zsh, "-lic", '(( $+functions[_zsh_autosuggest_start] && $+functions[_zsh_highlight] && $+functions[_omp_precmd] && $+functions[z] && $+functions[y] )) && [[ -r "$POSH_CONFIG" ]]'], capture_output=True, text=True)
        print("OK      shell integrations" if result.returncode == 0 else "FAIL    shell integrations: " + result.stderr)
        if result.returncode:
            failed.append("shell integrations")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--config-only", action="store_true", help="Link configuration without downloading tools")
    group.add_argument("--check", action="store_true", help="Check tools and shell integrations")
    group.add_argument("--mcp-only", action="store_true", help="Register the Oh My Posh MCP server in Codex")
    group.add_argument("--restore", action="store_true", help="Restore files replaced by this installer")
    group.add_argument("--dry-run", action="store_true", help="Print the install plan without changing anything")
    group.add_argument("--preflight", action="store_true", help="Check prerequisites and network without installing")
    parser.add_argument("--skip-mcp", action="store_true", help="Do not modify Codex MCP configuration")
    args = parser.parse_args()
    os.environ["PATH"] = str(BIN) + os.pathsep + os.environ.get("PATH", "")
    if args.check:
        return doctor()
    if args.mcp_only:
        platform_key()
        migrate_legacy()
        install_mcp(Deployment())
        return 0
    if args.restore:
        platform_key()
        migrate_legacy()
        deploy = Deployment()
        prepare_retained_zsh(deploy)
        include = deploy.state.pop("git_include", None)
        if include:
            subprocess.run(["git", "config", "--global", "--fixed-value", "--unset-all", "include.path", include], check=False)
            deploy.save()
        deploy.restore(targets=[p for p, item in deploy.state["links"].items() if not item.get("program")])
        print("Restored setup configuration; managed programs and caches were retained.")
        return 0
    key = platform_key()
    lock = json.loads((ROOT / "tools.lock.json").read_text())
    from preflight import check
    cached = all(find_tool(TOOLS.get(name, name)) for name in lock["tools"])
    for message in check(ROOT, CONFIG, DATA, STATE, CACHE, BIN, config_only=args.config_only,
                         network=args.preflight or (not args.config_only and not args.dry_run and not cached)):
        print(message)
    if args.preflight:
        return 0
    if args.dry_run:
        print(f"Platform: {key}\nCheckout: {ROOT}\nConfiguration link: {CONFIG / 'linux-setup'}\nExecutables: {BIN}\nData: {DATA}\nBackups: {STATE / 'backups'}")
        print("Tools:", ", ".join(lock["tools"]))
        print("Plugins:", ", ".join(lock["plugins"]))
        print("Vite+ and uv are installed only when absent; existing installations are kept.")
        print("Base tools use the host package manager; existing files are backed up.")
        return 0
    migrate_legacy()
    deploy = Deployment()
    BIN.mkdir(parents=True, exist_ok=True)
    if not args.config_only:
        install_base(deploy)
        install_tools(lock, key, deploy)
    install_config(deploy)
    if not args.skip_mcp:
        install_mcp(deploy)
    print(f"\nInstalled from {ROOT}\nBackups: {STATE / 'backups'}\nRun: exec zsh\nThen: dev-doctor")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"linux-setup: {error}", file=sys.stderr)
        sys.exit(1)
