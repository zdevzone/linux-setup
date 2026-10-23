"""Read-only prerequisite checks, performed before downloading or linking files."""
import os
from pathlib import Path
import platform
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request


BASE = ("zsh", "tmux", "file", "git", "curl", "lsof", "psql")


def _glibc():
    try:
        if os.confstr("CS_GNU_LIBC_VERSION"):
            return True
    except (AttributeError, OSError, ValueError):
        pass
    return platform.libc_ver()[0].lower() in ("glibc", "gnu libc")


def _existing_vp(config, data, bin_dir):
    if shutil.which("vp"):
        return True
    candidates = [bin_dir / "vp", data.parent / "vite-plus/bin/vp", Path.home() / ".vite-plus/bin/vp"]
    for variable, suffix in (("VP_BIN_DIR", "vp"), ("VP_HOME", "bin/vp")):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]).expanduser() / suffix)
    return any(p.is_file() and os.access(p, os.X_OK) for p in candidates)


def _writable_destination(path):
    """Check the nearest existing ancestor without creating a probe file."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        return f"Use an absolute installation path, not {path}."
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return f"Cannot resolve installation path {path}; check its symlinks."
    if resolved in (Path("/"), Path.home().resolve()):
        return f"Installation destination {path} is too broad; use a dedicated subdirectory."
    ancestor = path
    while not ancestor.exists():
        if ancestor.is_symlink():
            return f"Installation destination {path} contains a dangling symlink: {ancestor}."
        if ancestor.parent == ancestor:
            return f"No accessible parent exists for {path}."
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        return f"Installation destination {path} is blocked by the file {ancestor}."
    if not os.access(ancestor, os.W_OK | os.X_OK):
        return f"Installation destination {path} is not writable by the current user."
    return None


def check(root, config, data, state, cache, bin_dir, *, config_only=False, network=True):
    """Return messages or raise RuntimeError; never create files or run installers."""
    errors, messages = [], []
    root, config, data, state, cache, bin_dir = map(Path, (root, config, data, state, cache, bin_dir))
    architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine(), platform.machine())
    if platform.system() != "Linux" or architecture not in ("x86_64", "aarch64"):
        errors.append("Supported targets are Linux x86_64 and ARM64. Native Windows and macOS are not supported; WSL must run a Linux distribution.")
    if sys.version_info < (3, 9):
        errors.append("Python 3.9+ is required. On Ubuntu/Debian run ./install.sh --install-prerequisites.")
    if not shutil.which("bash"):
        errors.append("Bash is required; install it with your distribution package manager.")
    if config_only and not shutil.which("git"):
        errors.append("Configuration-only installation requires Git to register the managed Git settings. Install Git first, or use a full installation to install missing base tools.")
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        errors.append(f"The setup checkout is not readable: {root}.")
    for destination in (config, data, state, cache, bin_dir):
        error = _writable_destination(destination)
        if error:
            errors.append(error)

    if not config_only:
        if not _glibc():
            if _existing_vp(config, data, bin_dir):
                messages.append("Non-glibc host: preserving the existing Vite+ installation. Other upstream binaries must also be compatible with this distribution; it is not a tested installation target.")
            else:
                errors.append("The pinned Vite+ Linux build requires glibc. On a musl distribution install its matching Vite+ build first, or use Ubuntu/Debian; the installer preserves an existing vp.")
        missing = [tool for tool in BASE if not shutil.which(tool)]
        if missing:
            packages = ["postgresql-client" if name == "psql" else name for name in missing]
            if not shutil.which("apt-get") or not shutil.which("dpkg-deb"):
                errors.append("Missing base tools: " + ", ".join(missing) + ". Rootless installation requires apt-get and dpkg-deb. Install these tools using your distribution package manager, then rerun.")
            else:
                try:
                    result = subprocess.run(["apt-get", "-s", "--no-install-recommends", "install", *packages], capture_output=True, text=True, timeout=30)
                    if result.returncode:
                        errors.append("APT cannot resolve the missing packages: " + ", ".join(packages) + ". Refresh the package indexes with sudo apt-get update (or ask an administrator), then rerun. This check did not change system packages.")
                    else:
                        messages.append("Missing base tools will be extracted into your user directory without sudo: " + ", ".join(missing) + ".")
                except (OSError, subprocess.TimeoutExpired):
                    errors.append("APT dependency resolution could not complete. Check apt-get and package indexes before retrying.")

    if network and not config_only and not errors:
        try:
            ssl.create_default_context()
            request = urllib.request.Request("https://github.com/", method="HEAD", headers={"User-Agent": "linux-setup/preflight"})
            with urllib.request.urlopen(request, timeout=8):
                pass
            messages.append("GitHub HTTPS and certificate verification succeeded. Individual release downloads are verified during installation.")
        except (OSError, ValueError, urllib.error.URLError):
            errors.append("Cannot reach GitHub over verified HTTPS. Check network/proxy access and the system CA certificates; keep TLS verification enabled. On Ubuntu/Debian, --install-prerequisites installs ca-certificates.")
    elif not network or config_only:
        messages.append("Network check skipped; no files were downloaded.")
    messages.append("Optional: a Nerd Font on the terminal-rendering device; ffmpeg, Poppler, and 7-Zip for extra Yazi previews.")
    if errors:
        raise RuntimeError("Preflight failed:\n- " + "\n- ".join(errors))
    return messages
