#!/usr/bin/env python3
"""Describe live Zsh commands without evaluating their definitions."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ALIAS = re.compile(r"(?:^|\s|[;&])alias\s+(?:--\s+)?([^\s=]+)=")
FUNCTION = re.compile(r"^\s*(?:function\s+([^\s(){]+)(?:\s*\(\s*\))?|([^\s(){]+)\s*\(\s*\))\s*\{")


def descriptions(paths):
    """Read adjacent comments, not shell values; Zsh supplies the actual values."""
    result = {}
    for path in paths:
        if not path.is_file():
            continue
        comments = []
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                comments.append(stripped.lstrip("# "))
                continue
            alias = ALIAS.search(line)
            function = FUNCTION.match(line)
            if alias or function:
                name = alias[1] if alias else (function[1] or function[2])
                kind = "alias" if alias else "function"
                result[(kind, name)] = " ".join(comments) or f"Custom {kind}."
            # A conditional guard can sit between a description and its alias.
            if not stripped.startswith("if "):
                comments = []
    return result


def source_paths():
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [
        ROOT / "config/zsh/aliases.zsh",
        ROOT / "config/zsh/functions.zsh",
        ROOT / "config/zsh/command-picker.zsh",
        config / "linux-setup-local/zshenv",
        config / "linux-setup-local/zshrc",
    ]


def catalog(snapshot, metadata):
    fields = snapshot.split("\0")
    if fields[-1] == "":
        fields.pop()
    if len(fields) % 3:
        raise ValueError("Incomplete shell command snapshot")
    entries = {}
    for kind, name, body in zip(fields[::3], fields[1::3], fields[2::3]):
        if (kind, name) not in metadata or name.startswith("_"):
            continue
        # Aliases take precedence when both kinds have the same name.
        if name in entries and entries[name]["kind"] == "alias":
            continue
        entries[name] = {
            "name": name,
            "kind": kind,
            "description": metadata[(kind, name)],
            "command": body if kind == "alias" else f"{name} () {{\n{body}\n}}",
            "insert": body if kind == "alias" else shlex.quote(name) + " ",
        }
    return sorted(entries.values(), key=lambda entry: entry["name"].casefold())


def single_line(value):
    # Do not let control characters in a command alter fzf's rows or terminal.
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())


def row(entry):
    return "\t".join(single_line(entry[key]) for key in ("name", "kind", "description", "command"))


def pick(entries, query=""):
    if not entries:
        return None
    # Full definitions are plain preview files. Only opaque numeric IDs enter
    # the preview shell command; no alias/function is ever used as shell code.
    with tempfile.TemporaryDirectory(prefix="linux-setup-commands-") as temporary:
        directory = Path(temporary)
        for index, entry in enumerate(entries):
            (directory / str(index)).write_text(
                f"{entry['name']} ({entry['kind']})\n{entry['description']}\n\n"
                f"Inserts: {entry['insert']}\n\nFull command:\n{entry['command']}\n"
            )
        result = subprocess.run(
            [
                "fzf", "--height=80%", "--layout=reverse", "--border", "--no-multi",
                "--delimiter=\t", "--with-nth=2..", "--prompt=Commands> ",
                "--header=Name | kind | description | command — Enter: insert only; Esc: cancel; Ctrl-/: preview",
                "--bind=ctrl-/:toggle-preview", "--preview-window=down,50%,wrap",
                "--preview", "cat -- " + shlex.quote(str(directory)) + "/{1}",
                "--query", query,
            ],
            input="".join(f"{index}\t{row(entry)}\n" for index, entry in enumerate(entries)),
            text=True,
            stdout=subprocess.PIPE,
            # User fzf bindings (execute, become, accept on focus, etc.) must
            # not change this picker's insert-only behavior.
            env={**os.environ, "FZF_DEFAULT_OPTS": "", "FZF_DEFAULT_OPTS_FILE": "", "SHELL": "/bin/sh"},
        )
        if result.returncode in (1, 130):
            return None
        if result.returncode:
            raise RuntimeError(f"fzf exited with status {result.returncode}")
        identifier = result.stdout.partition("\t")[0]
        if not identifier.isdecimal() or int(identifier) >= len(entries):
            raise ValueError("Invalid command selection")
        return entries[int(identifier)]["insert"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--pick", action="store_true")
    parser.add_argument("query", nargs="?", default="")
    args = parser.parse_args()
    try:
        entries = catalog(sys.stdin.read(), descriptions(source_paths()))
        if args.list:
            for entry in entries:
                if args.query.casefold() in row(entry).casefold():
                    print(row(entry))
            return 0
        selected = pick(entries, args.query)
        if selected is None:
            return 1
        sys.stdout.write(selected)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Command picker: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
