#!/usr/bin/env python3
"""Restore terminal configuration and optionally remove setup-owned programs/caches."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys

SPEC = importlib.util.spec_from_file_location("linux_setup_installer", Path(__file__).with_name("setup.py"))
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


def visible(value):
    return "".join(c if c.isprintable() else "?" for c in str(value))


def version_label(item):
    version = item.get("version", "")
    return "Previously installed" if version == "legacy" else visible(version)


def present(path):
    return path.exists() or path.is_symlink()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def choose(title, choices, multi=False):
    """Return opaque choice IDs; input labels never become executable shell text."""
    if not choices:
        return [] if multi else None
    fzf = shutil.which("fzf")
    if fzf:
        args = [fzf, "--read0", "--print0", "--delimiter=\t", "--with-nth=2..", "--height=70%", "--layout=reverse", "--border", "--prompt=" + title + " > "]
        if multi:
            args += ["--multi", "--marker=☑", "--header=Space: toggle  Enter: accept  Ctrl-A: all  Ctrl-D: none  Esc: cancel", "--bind=space:toggle+down,ctrl-a:select-all,ctrl-d:deselect-all"]
            # fzf normally accepts the focused row when zero rows are checked.
            # Emit an explicit sentinel so Enter truly keeps every unchecked item.
            args += ["--with-shell=/bin/sh -c", '--bind=enter:transform:if [ "${FZF_SELECT_COUNT:-0}" = 0 ]; then printf "%s" "print(__NONE__)+accept"; else printf "%s" accept; fi']
        else:
            args += ["--header=Arrows: move  Enter: select  Esc: cancel"]
        environment = dict(os.environ, FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE="")
        payload = "".join(f"{i}\t{visible(label)}\0" for i, (label, _) in enumerate(choices))
        result = subprocess.run(args, input=payload, text=True, stdout=subprocess.PIPE, env=environment)
        if result.returncode in (1, 130):
            raise KeyboardInterrupt
        if result.returncode:
            raise RuntimeError("The selection menu failed; rerun with explicit command-line options")
        selected = []
        for row in result.stdout.split("\0"):
            if row == "__NONE__":
                return []
            if row:
                selected.append(choices[int(row.split("\t", 1)[0])][1])
        return selected if multi else (selected[0] if selected else None)
    selected = set()
    while True:
        print("\n" + title)
        for index, (label, _) in enumerate(choices, 1):
            print(f" {index:2}. [{'x' if index in selected else ' '}] {visible(label)}")
        instruction = "Numbers toggle, a selects all, n clears, Enter accepts, q cancels: " if multi else "Number to select, q cancels: "
        answer = input(instruction).strip().lower()
        if answer == "q":
            raise KeyboardInterrupt
        if multi and not answer:
            return [choices[n - 1][1] for n in sorted(selected)]
        if multi and answer in ("a", "n"):
            selected = set(range(1, len(choices) + 1)) if answer == "a" else set()
            continue
        try:
            numbers = [int(n) for n in answer.replace(",", " ").split()]
            if not numbers or any(n < 1 or n > len(choices) for n in numbers):
                raise ValueError
            if not multi:
                if len(numbers) != 1:
                    raise ValueError
                return choices[numbers[0] - 1][1]
            selected.symmetric_difference_update(numbers)
        except ValueError:
            print("Choose one of the displayed numbers.")


def cache_options(programs):
    """A small allowlist of disposable caches; never infer cache from data paths."""
    root = Path(os.environ.get("XDG_CACHE_HOME", setup.HOME / ".cache")).absolute()
    setup_cache = setup.CACHE
    old_cache = setup.CACHE.parent / "dev-setup"
    old_manifest = setup.STATE.parent / "dev-setup/deployment.json"
    if not setup_cache.exists() and old_cache.is_dir() and not old_cache.is_symlink() and old_manifest.is_file():
        # Preview legacy locations without migrating anything before confirmation.
        setup_cache = old_cache
    candidates = {
        "setup-downloads": {"paths": [setup_cache / "downloads"], "label": "Verified setup download archives", "shared": False},
        "setup-test-artifacts": {"paths": [setup_cache / "postgres-test"], "label": "Disposable PostgreSQL development-test binaries", "shared": False},
    }
    owned = {name for name, item in programs.items() if item.get("owned")}
    for name, directory in [("uv", "uv"), ("oh-my-posh", "oh-my-posh"), ("bat", "bat")]:
        if name in owned:
            candidates[name] = {"paths": [root / directory], "label": name + " cache (may be shared with other installations)", "shared": True}
    if "zsh" in owned:
        candidates["zsh"] = {"paths": sorted((root / "zsh").glob("zcompdump*")), "label": "Zsh completion dumps (may be shared)", "shared": True}
    return {key: {**item, "paths": [p for p in item["paths"] if present(p)]} for key, item in candidates.items() if any(present(p) for p in item["paths"])}


def inside(path, root):
    """Both lexical and resolved checks prevent parent-symlink escapes."""
    path, root = Path(path).absolute(), Path(root).absolute()
    return path != root and path.is_relative_to(root) and path.resolve().is_relative_to(root.resolve()) and path.resolve() != root.resolve()


def safe_program_path(path):
    path = Path(path).absolute()
    if setup.DATA.is_symlink() or not inside(path, setup.DATA):
        return False
    if any(parent.is_symlink() for parent in path.parents if parent != setup.DATA and parent.is_relative_to(setup.DATA)):
        return False
    return any(inside(path, setup.DATA / name) for name in ("tools", "plugins", "wrappers", "base"))


def safe_shared_path(path):
    path = Path(path).absolute()
    return path == setup.DATA / "runtime" and inside(path, setup.DATA) and not path.is_symlink() and not setup.DATA.is_symlink()


def canonical_cache_paths(caches):
    """Only map the two exact, known setup cache directories after migration."""
    previous = setup.CACHE.parent / "dev-setup"
    names = {"setup-downloads": "downloads", "setup-test-artifacts": "postgres-test"}
    result = {}
    for cache_id, paths in caches.items():
        suffix = names.get(cache_id)
        result[cache_id] = [str(setup.CACHE / suffix) if suffix and Path(path) == previous / suffix else path for path in paths]
    return result


def safe_cache_path(path, cache_id=None):
    root = Path(os.environ.get("XDG_CACHE_HOME", setup.HOME / ".cache")).absolute()
    path = Path(path).absolute()
    # Selection is restricted again immediately before deleting, not just at display time.
    if path.is_symlink() or not inside(path, root):
        return False
    forbidden = [setup.HOME, setup.ROOT, setup.CONFIG, setup.DATA, setup.STATE, setup.BIN]
    if any(path == p or p.is_relative_to(path) for p in map(Path.absolute, forbidden)):
        return False
    exact = {
        "setup-downloads": setup.CACHE / "downloads", "setup-test-artifacts": setup.CACHE / "postgres-test",
        "uv": root / "uv", "oh-my-posh": root / "oh-my-posh", "bat": root / "bat",
    }
    if cache_id == "zsh":
        return path.parent == root / "zsh" and path.name.startswith("zcompdump")
    return cache_id in exact and path == exact[cache_id]


def remove_path(path):
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def matches_file(path, item):
    if not present(path):
        return True
    if "symlink" in item:
        return path.is_symlink() and os.readlink(path) == item["symlink"]
    if "sha256" in item:
        return path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    return False


def program_obstacles(name, item, links):
    reasons = []
    for target, link in links.items():
        if link.get("program") != name:
            continue
        path = Path(target)
        if present(path) and (not path.is_symlink() or os.readlink(path) != link["source"]):
            reasons.append("changed managed link " + target)
        source = Path(link["source"])
        footprints = [Path(p) for p in item.get("paths", []) + item.get("shared", [])]
        if not any(source.resolve() == p.resolve() or source.resolve().is_relative_to(p.resolve()) for p in footprints):
            reasons.append("changed source alias " + link["source"])
    for target, expected in item.get("fingerprints", {}).items():
        if isinstance(expected, str):
            matches = not present(Path(target)) or setup.fingerprint(Path(target)) == expected
        else:
            matches = matches_file(Path(target), expected)
        if not matches:
            reasons.append("changed program file " + target)
    for target, expected in item.get("external_files", {}).items():
        pending = item.get("restoring_external", {})
        restored = pending.get("path") == target and pending.get("backup_fingerprint") == setup.fingerprint(Path(target)) and not present(Path(expected["backup"])) if expected.get("backup") else False
        if not restored and not matches_file(Path(target), expected):
            reasons.append("changed generated integration " + target)
    for target in item.get("paths", []):
        if not safe_program_path(target):
            reasons.append("unverified program path " + target)
    return reasons


def login_shell():
    return pwd.getpwuid(os.getuid()).pw_shell


def program_is_login_shell(name, item, links):
    shell = Path(login_shell())
    targets = [Path(p) for p, link in links.items() if link.get("program") == name]
    footprints = [Path(p) for p in item.get("paths", [])]
    if shell.name in item.get("binaries", []):
        footprints += [Path(p) for p in item.get("shared", [])]
    return shell in targets or any(shell.resolve() == p.resolve() or shell.resolve().is_relative_to(p.resolve()) for p in footprints)


def registered_shells():
    try:
        return [line.strip() for line in Path("/etc/shells").read_text().splitlines() if line.strip().startswith("/") and os.access(line.strip(), os.X_OK)]
    except OSError:
        return []


def switch_shell(replacement, selected_paths, interactive):
    candidates = [s for s in registered_shells() if not any(Path(s).resolve() == p.resolve() or Path(s).resolve().is_relative_to(p.resolve()) for p in selected_paths)]
    if not replacement and interactive:
        replacement = choose("Replacement login shell", [("Keep current shell/program", None)] + [(s, s) for s in candidates])
    if not replacement:
        return False
    if replacement not in candidates:
        print("Keeping the login shell: replacement must be an executable listed in /etc/shells outside removed programs.")
        return False
    try:
        result = subprocess.run(["chsh", "-s", replacement], stdin=None if interactive else subprocess.DEVNULL)
        return result.returncode == 0 and Path(login_shell()).resolve() == Path(replacement).resolve()
    except OSError:
        return False


def clean_integrations(deploy, report):
    include = deploy.state.get("git_include")
    if include:
        try:
            result = subprocess.run(["git", "config", "--global", "--fixed-value", "--unset-all", "include.path", include], capture_output=True, text=True)
            if result.returncode in (0, 5):
                deploy.state.pop("git_include", None)
                deploy.save()
            else:
                report["unresolved"].append("Git include could not be removed: " + include)
        except OSError:
            report["unresolved"].append("Git unavailable; retained include: " + include)
    mcp = deploy.state.get("mcp")
    if mcp and mcp.get("owned"):
        try:
            result = subprocess.run(["codex", "mcp", "get", mcp["name"], "--json"], capture_output=True, text=True)
            current = json.loads(result.stdout) if result.returncode == 0 else None
            if current is None:
                report["unresolved"].append("MCP entry could not be inspected; retained")
            elif mcp.get("fingerprint") and hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest() == mcp["fingerprint"]:
                subprocess.run(["codex", "mcp", "remove", mcp["name"]], check=True, capture_output=True, text=True)
                deploy.state.pop("mcp", None)
                deploy.save()
            else:
                report["retained"].append("Modified MCP registration")
        except (OSError, ValueError, subprocess.CalledProcessError):
            report["unresolved"].append("MCP entry could not be removed; retained")
    elif mcp:
        report["retained"].append("Pre-existing or unverified MCP registration")


def restore_external(deploy, item, report):
    for filename, expected in list(item.get("external_files", {}).items()):
        path = Path(filename)
        backup = Path(expected["backup"]) if expected.get("backup") else None
        pending = item.get("restoring_external", {})
        # Recover interruption after moving the original file back but before saving.
        already_restored = backup and not present(backup) and pending.get("path") == filename and pending.get("backup_fingerprint") == setup.fingerprint(path)
        if already_restored:
            del item["external_files"][filename]
            item.pop("restoring_external", None)
            deploy.save()
            report["restored"].append(filename)
            continue
        # These generated files can live outside DATA; only exact fingerprints authorize unlinking.
        if not matches_file(path, expected):
            raise RuntimeError("Generated integration changed: " + filename)
        item["restoring_external"] = {"path": filename, "backup_fingerprint": setup.fingerprint(backup) if backup and present(backup) else None}
        deploy.save()
        if present(path):
            if path.is_dir() and not path.is_symlink():
                raise RuntimeError("Refusing to remove integration directory: " + filename)
            path.unlink()
        if backup and present(backup):
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup), str(path))
            report["restored"].append(filename)
        del item["external_files"][filename]
        item.pop("restoring_external", None)
        deploy.save()


def apply_plan(deploy, remove, caches, replacement=None, interactive=False, journal=None):
    """Each completed program is removed from the manifest before the next begins."""
    report = {"removed": [], "restored": [], "retained": [], "unresolved": []}
    journal_path = setup.STATE / "uninstall.json"
    journal = journal or {"status": "running", "remove": sorted(remove), "caches": caches, "replacement_shell": replacement, "completed": []}
    programs = deploy.state.setdefault("programs", {})
    links = deploy.state.setdefault("links", {})
    journal["shared"] = sorted(set(journal.get("shared", [])) | {p for name in remove if name in programs for p in programs[name].get("shared", [])})
    atomic_json(journal_path, journal)
    setup.prepare_retained_zsh(deploy)
    removable = set(remove)
    selected_paths = [Path(p) for name in remove if name in programs for p in programs[name].get("paths", []) + programs[name].get("shared", [])]
    for name in sorted(remove):
        if name not in programs:
            continue
        item = programs[name]
        problems = program_obstacles(name, item, links)
        if not item.get("owned"):
            problems.append("not installed by this setup")
        if problems:
            removable.discard(name)
            report["unresolved"].append(name + ": " + "; ".join(problems))
        elif program_is_login_shell(name, item, links):
            if not switch_shell(replacement, selected_paths, interactive):
                removable.discard(name)
                report["unresolved"].append(name + ": still the account login shell; select an installed /etc/shells replacement using chsh -s PATH, then retry")
    clean_integrations(deploy, report)
    # uv's cache lock coordinates concurrent processes; never delete it directly.
    # Its executable must remain available until this finishes successfully.
    uv_cache_failed = False
    for filename in caches.get("uv", []):
        if "cache:" + filename in journal["completed"]:
            continue
        try:
            if not safe_cache_path(filename, "uv"):
                raise RuntimeError("Unsafe uv cache path")
            uv = setup.find_tool("uv")
            if not uv:
                raise RuntimeError("uv is unavailable; its cache was retained")
            subprocess.run([uv, "--cache-dir", filename, "cache", "clean"], check=True)
            journal["completed"].append("cache:" + filename)
            atomic_json(journal_path, journal)
            report["removed"].append("uv cache entries: " + filename)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            uv_cache_failed = True
            report["unresolved"].append("uv cache: " + visible(error))
    if uv_cache_failed and "uv" in removable:
        removable.remove("uv")
        report["retained"].append("uv (needed to retry cache cleanup)")
    config_targets = [target for target, item in links.items() if not item.get("program")]
    unresolved = deploy.restore(targets=config_targets) or []
    report["unresolved"].extend("Changed configuration retained: " + str(p) for p in unresolved)
    report["restored"].extend(p for p in config_targets if p not in deploy.state["links"])
    shared = set(journal["shared"])
    for name in sorted(removable):
        item = programs.get(name)
        if not item:
            continue
        try:
            # A second check catches edits made while confirmation/other operations ran.
            obstacles = program_obstacles(name, item, deploy.state["links"])
            if obstacles:
                raise RuntimeError("; ".join(obstacles))
            restore_external(deploy, item, report)
            targets = [p for p, entry in deploy.state["links"].items() if entry.get("program") == name]
            unresolved = deploy.restore(targets=targets) or []
            if unresolved:
                raise RuntimeError("managed links changed during removal")
            for filename in item.get("paths", []):
                if not safe_program_path(filename):
                    raise RuntimeError("Unsafe program path: " + filename)
                remove_path(filename)
            shared.update(item.get("shared", []))
            del programs[name]
            deploy.save()
            report["removed"].append(name)
            journal["completed"].append("program:" + name)
            atomic_json(journal_path, journal)
        except (OSError, RuntimeError) as error:
            report["unresolved"].append(name + ": " + visible(error))
    for filename in sorted(shared):
        if "shared:" + filename in journal["completed"]:
            continue
        consumers = [n for n, item in programs.items() if filename in item.get("shared", [])]
        if consumers:
            report["retained"].append(filename + " (shared by " + ", ".join(consumers) + ")")
        elif safe_shared_path(filename):
            expected = deploy.state.get("shared_fingerprints", {}).get(filename)
            if present(Path(filename)) and (not expected or setup.fingerprint(filename) != expected):
                report["unresolved"].append("Changed or unverified shared runtime retained: " + filename)
            else:
                remove_path(filename)
                deploy.state.get("shared_fingerprints", {}).pop(filename, None)
                deploy.save()
                journal["completed"].append("shared:" + filename)
                atomic_json(journal_path, journal)
                report["removed"].append(filename)
        else:
            report["unresolved"].append("Unverified shared runtime retained: " + filename)
    for cache_id, paths in caches.items():
        if cache_id == "uv":
            continue
        for filename in paths:
            if "cache:" + filename in journal["completed"]:
                continue
            try:
                if not safe_cache_path(filename, cache_id):
                    raise RuntimeError("Cache path escapes the cache directory or is a symlink")
                remove_path(filename)
                report["removed"].append(cache_id + ": " + filename)
                journal["completed"].append("cache:" + filename)
                atomic_json(journal_path, journal)
            except (OSError, RuntimeError) as error:
                report["unresolved"].append(filename + ": " + visible(error))
    report["retained"].extend(sorted(programs))
    journal["status"] = "needs-attention" if report["unresolved"] else "complete"
    journal["report"] = report
    atomic_json(journal_path, journal)
    return report


def display_plan(deploy, remove, caches):
    print("\nConfiguration: restore unchanged setup-owned links and original backups.")
    print("Remove programs:", ", ".join(sorted(remove)) or "none")
    print("Keep programs:", ", ".join(sorted(set(deploy.state.get("programs", {})) - set(remove))) or "none")
    print("Remove caches:")
    for name, paths in caches.items():
        for path in paths:
            print("  " + visible(name) + ": " + visible(path))
    if not caches:
        print("  none")
    else:
        print("Selected caches are permanently deleted and may be shared. Tools may download or rebuild them.")
    for name in sorted(remove):
        item = deploy.state.get("programs", {}).get(name)
        if item and program_is_login_shell(name, item, deploy.state.get("links", {})):
            print(name + " is the account login shell: it stays installed until a valid replacement is confirmed.")
    print("The checkout, personal files, history, projects, databases, runtimes managed by uv/Vite+, and recovery files are kept.")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--keep-tools", action="store_true", help="Restore setup configuration and keep all programs")
    mode.add_argument("--remove", action="append", default=[], metavar="NAME", help="Remove an owned program; repeat as needed")
    mode.add_argument("--all-tools", action="store_true", help="Remove all owned programs; login-shell protection still applies")
    mode.add_argument("--resume", action="store_true", help="Resume the previously recorded uninstall plan")
    result.add_argument("--cache", action="append", default=[], metavar="NAME", help="Delete a displayed cache ID; repeat as needed")
    result.add_argument("--replacement-shell", metavar="PATH", help="Registered shell to switch to before removing the current login shell")
    result.add_argument("--dry-run", action="store_true", help="Show a plan without changing files or the login shell")
    result.add_argument("--list", action="store_true", help="List program ownership and available cache IDs without changes")
    result.add_argument("--yes", action="store_true", help="Confirm the explicitly selected plan without prompting")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.yes and not (args.keep_tools or args.remove or args.all_tools or args.cache or args.resume or args.list or args.dry_run):
            raise RuntimeError("--yes requires an explicit mode: --keep-tools, --remove NAME, --all-tools, or --resume")
        deploy = setup.Deployment(read_only=True)
        programs = deploy.state.get("programs", {})
        options = cache_options(programs)
        owned = {name for name, item in programs.items() if item.get("owned")}
        if args.list:
            for name, item in sorted(programs.items()):
                print(f"{name:26} {'owned' if item.get('owned') else 'external/unknown':16} {version_label(item)}")
            print("\nAvailable cache IDs (unchecked by default):")
            for name, item in options.items():
                print(name + ": " + item["label"] + " — " + ", ".join(map(str, item["paths"])))
            return 0
        journal = None
        if args.resume:
            if args.cache or args.replacement_shell:
                raise RuntimeError("--resume uses the saved selections; do not combine with --cache or --replacement-shell")
            journal = json.loads((setup.STATE / "uninstall.json").read_text())
            remove, caches = set(journal["remove"]), journal["caches"]
            args.replacement_shell = journal.get("replacement_shell")
        else:
            remove = owned if args.all_tools else set(args.remove)
            unknown = remove - owned
            if unknown:
                raise RuntimeError("Not a setup-owned program: " + ", ".join(sorted(unknown)) + ". Use --list to inspect ownership.")
            cache_ids = args.cache
            interactive_menu = not (args.keep_tools or args.remove or args.all_tools or args.cache or args.yes or args.dry_run)
            if interactive_menu:
                if not sys.stdin.isatty():
                    raise RuntimeError("Choose --keep-tools, --remove NAME, or --all-tools; use --dry-run to preview")
                mode = choose("Uninstall mode", [("Remove setup; keep all programs", "keep"), ("Remove setup and selected programs", "select"), ("Remove setup and all owned programs", "all")])
                if mode == "all":
                    remove = owned
                elif mode == "select":
                    remove = set(choose("Checked programs will be REMOVED", [(n + " " + version_label(programs[n]), n) for n in sorted(owned)], multi=True))
                cache_ids = choose("Checked caches will be DELETED", [(n + ": " + item["label"] + " — " + ", ".join(map(str, item["paths"])), n) for n, item in options.items()], multi=True)
            invalid_caches = set(cache_ids) - set(options)
            if invalid_caches:
                raise RuntimeError("Unknown or unavailable cache ID: " + ", ".join(sorted(invalid_caches)) + ". Use --list.")
            caches = {name: list(map(str, options[name]["paths"])) for name in cache_ids}
        display_plan(deploy, remove, caches)
        if args.dry_run:
            print("Dry run: no changes made.")
            return 0
        if not args.yes:
            if not sys.stdin.isatty():
                raise RuntimeError("Confirmation requires a terminal; use --yes for an explicitly selected plan")
            if input("\nType UNINSTALL to apply this plan: ") != "UNINSTALL":
                print("Cancelled; no changes made.")
                return 0
        if hasattr(setup, "migrate_legacy"):
            setup.migrate_legacy()
        caches = canonical_cache_paths(caches)
        if journal:
            journal["caches"] = caches
        deploy = setup.Deployment()
        report = apply_plan(deploy, remove, caches, args.replacement_shell, sys.stdin.isatty(), journal)
        for heading, entries in report.items():
            if entries:
                print("\n" + heading.title() + ":")
                for entry in entries:
                    print("  " + visible(entry))
        print("\nSaved report:", setup.STATE / "uninstall.json")
        print("Retained executables remain in", setup.BIN, "— ensure this directory is on your PATH.")
        print("Open a new shell to use restored configuration. Reinstall with ./install.sh from the retained checkout.")
        return 1 if report["unresolved"] else 0
    except KeyboardInterrupt:
        print("\nCancelled. If operations had started, inspect the saved report and use --resume.")
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("linux-setup uninstall: " + visible(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
