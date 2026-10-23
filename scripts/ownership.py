"""Ownership metadata and recoverable migration from the original project name."""
import hashlib
import json
import os
from pathlib import Path


def fingerprint(path):
    path = Path(path)
    if path.is_symlink():
        return "link:" + os.readlink(path)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return "file:" + digest.hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for parent, directories, files in os.walk(path, followlinks=False):
            directories.sort()
            for name in sorted(directories + files):
                child = Path(parent) / name
                relative = child.relative_to(path).as_posix()
                value = "directory" if child.is_dir() and not child.is_symlink() else fingerprint(child)
                digest.update((relative + "\0" + value + "\0").encode())
        return "tree:" + digest.hexdigest()
    return "missing"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def migrate(setup):
    legacy_state = setup.STATE.parent / "dev-setup"
    if not (legacy_state / "deployment.json").is_file() and not (setup.STATE / "migration.json").is_file():
        return
    pairs = [(path.parent / "dev-setup", path) for path in [setup.STATE, setup.DATA, setup.CACHE]]
    pairs.append((setup.CONFIG / "dev-setup-local", setup.CONFIG / "linux-setup-local"))
    for old, new in pairs:
        if old.is_symlink():
            if old.resolve() != new.resolve():
                raise RuntimeError(f"Migration needs review: {old} is an unrelated symlink")
        elif old.exists() and (new.exists() or new.is_symlink()):
            raise RuntimeError(f"Both {old} and {new} exist; move the unrelated destination aside before migrating")
    journal_root = setup.STATE if setup.STATE.exists() else legacy_state
    atomic_json(journal_root / "migration.json", {"from": "dev-setup", "to": "linux-setup", "status": "pending"})
    aliases = []
    for old, new in pairs:
        if old.is_dir() and not old.is_symlink():
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
        # Also repairs interruption between rename and compatibility-link creation.
        if new.exists() and not old.exists() and not old.is_symlink():
            old.symlink_to(new, target_is_directory=True)
        if old.is_symlink() and old.resolve() == new.resolve():
            aliases.append(str(old))
    if aliases:
        manifest = setup.STATE / "deployment.json"
        state = json.loads(manifest.read_text()) if manifest.exists() else {"links": {}}
        state["legacy_aliases"] = sorted(set(state.get("legacy_aliases", []) + aliases))
        atomic_json(manifest, state)
    atomic_json(setup.STATE / "migration.json", {"from": "dev-setup", "to": "linux-setup", "status": "complete"})


def infer_programs(setup, state):
    """Adopt only recorded links to managed artifacts; never adopt PATH programs."""
    programs = state.setdefault("programs", {})
    for target, link in state.setdefault("links", {}).items():
        source = Path(link["source"])
        canonical = source.resolve()
        data_root = setup.DATA
        if not data_root.exists() and (data_root.parent / "dev-setup").is_dir():
            data_root = data_root.parent / "dev-setup"
        try:
            relative = canonical.relative_to(data_root.resolve())
        except ValueError:
            continue
        parts = relative.parts
        if len(parts) >= 3 and parts[0] in ("tools", "plugins"):
            name = parts[1]
            directory = data_root.joinpath(*parts[:3])
            if not (directory / ".sha256").is_file():
                continue
            kind, paths, shared = ("tool" if parts[0] == "tools" else "plugin"), [str(directory)], []
        elif len(parts) == 2 and parts[0] == "wrappers" and parts[1] in setup.BASE:
            name, kind, paths, shared = parts[1], "base", [str(canonical)], [str(data_root / "runtime")]
        else:
            continue
        link["program"] = name
        for p in shared:
            if p not in state.setdefault("shared_fingerprints", {}):
                state["shared_fingerprints"][p] = fingerprint(p)
        if name not in programs:
            programs[name] = {"owned": True, "kind": kind, "paths": paths, "shared": shared,
                              "version": "legacy", "binaries": [Path(target).name],
                              "fingerprints": {p: fingerprint(p) for p in paths}, "legacy": True}
        elif programs[name].get("owned"):
            for p in paths:
                if p not in programs[name]["paths"]:
                    programs[name]["paths"].append(p)
                    programs[name].setdefault("fingerprints", {})[p] = fingerprint(p)
    state["schema"] = 2
