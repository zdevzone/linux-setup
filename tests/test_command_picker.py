import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")
FZF = shutil.which("fzf")
spec = importlib.util.spec_from_file_location("command_catalog", ROOT / "scripts/command_catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogTests(unittest.TestCase):
    def test_current_definition_and_alias_precedence(self):
        metadata = {("alias", "same"): "Alias description", ("function", "same"): "Function description"}
        entries = catalog.catalog("alias\0same\0echo current\0function\0same\0echo function\0", metadata)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["command"], "echo current")
        self.assertEqual(entries[0]["insert"], "echo current")
        self.assertEqual(entries[0]["description"], "Alias description")

    def test_function_body_is_searchable_but_only_name_is_inserted(self):
        body = '  command curl --fail "$1"\n  print done'
        entries = catalog.catalog("function\0probe\0" + body + "\0", {("function", "probe"): "Probe a URL"})
        self.assertEqual(entries[0]["insert"], "probe ")
        self.assertIn(body, entries[0]["command"])
        self.assertIn('command curl --fail "$1"', catalog.row(entries[0]))

    def test_unavailable_and_internal_commands_are_not_listed(self):
        metadata = {("alias", "absent"): "Unavailable tool", ("function", "_internal"): "Private helper"}
        self.assertEqual(catalog.catalog("function\0_internal\0echo private\0", metadata), [])


@unittest.skipUnless(ZSH, "Zsh is required for shell picker tests")
class CommandPickerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "ZDOTDIR": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_DATA_HOME": str(self.home / "data"),
            "XDG_STATE_HOME": str(self.home / "state"),
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "LINUX_SETUP_DIR": str(ROOT),
            "PATH": os.pathsep.join([str(self.bin), str(Path(sys.executable).parent), os.defpath]),
            "TERM": "xterm-256color",
            "PICKER_TEST_MARKER": str(self.home / "executed"),
            "PICKER_TEST_REPORT": str(self.home / "fzf.json"),
            "PICKER_TEST_BUFFER": str(self.home / "buffer"),
            "PICKER_TEST_SELECT": "gs",
            "PICKER_TEST_REAL_FZF": FZF or "",
            "FZF_DEFAULT_OPTS": "--bind=enter:execute(touch MUST_NOT_RUN)",
            "FZF_DEFAULT_OPTS_FILE": str(self.home / "nonexistent-options"),
        }
        # A user-space Zsh executable needs its installed modules even with -f.
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        module_paths = sorted((data / "linux-setup/runtime/usr/lib").glob("*/zsh/*"))
        self.prelude = "module_path=(" + " ".join(shlex.quote(str(path)) for path in module_paths) + " $module_path)\n"
        self.prelude += '\n'.join(
            'source "$LINUX_SETUP_DIR/config/zsh/' + filename + '"'
            for filename in ("aliases.zsh", "functions.zsh", "command-picker.zsh")
        ) + "\n"
        fzf = self.bin / "fzf"
        fzf.write_text('''#!/usr/bin/env python3
import json, os, pathlib, shlex, subprocess, sys
args = sys.argv[1:]
rows = sys.stdin.read().splitlines()
report = {"args": args, "options": os.environ.get("FZF_DEFAULT_OPTS"),
          "options_file": os.environ.get("FZF_DEFAULT_OPTS_FILE"), "rows": rows}
if os.environ.get("PICKER_TEST_CANCEL"):
    pathlib.Path(os.environ["PICKER_TEST_REPORT"]).write_text(json.dumps(report))
    sys.exit(130)
if os.environ.get("PICKER_TEST_FILTER"):
    result = subprocess.run([os.environ["PICKER_TEST_REAL_FZF"], "--delimiter=\\t", "--with-nth=2..",
                             "--filter", os.environ["PICKER_TEST_FILTER"]],
                            input="\\n".join(rows), text=True, stdout=subprocess.PIPE)
    rows = result.stdout.splitlines()
matches = [row for row in rows if row.split("\\t")[1] == os.environ["PICKER_TEST_SELECT"]]
if not matches:
    sys.exit(1)
row = matches[0]
preview = args[args.index("--preview") + 1].replace("{1}", shlex.quote(row.split("\\t")[0]))
result = subprocess.run(["/bin/sh", "-c", preview], text=True, stdout=subprocess.PIPE, check=True)
report["preview"] = result.stdout
pathlib.Path(os.environ["PICKER_TEST_REPORT"]).write_text(json.dumps(report))
print(row)
''')
        fzf.chmod(0o755)

    def shell(self, command, **updates):
        return subprocess.run([ZSH, "-dfc", self.prelude + command], env={**self.env, **updates},
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def test_catalog_reconciles_existing_and_new_commands(self):
        output = self.shell("_dev_commands_list").stdout
        rows = [line.split("\t") for line in output.splitlines()]
        names = [row[0] for row in rows]
        self.assertEqual(len(names), len(set(names)))
        for name in ("dcup", "dclogs", "dclog", "docker-nuclear", "dcdrop-vol", "dcinto", "mkcd", "pscripts", "sshtunnel", "pgconnect", "devcommands"):
            self.assertIn(name, names)
        self.assertTrue(all(len(row) == 4 and row[2] != "Custom alias." and row[2] != "Custom function." for row in rows))
        self.assertNotIn("_dev_commands_snapshot", names)

    def test_private_comments_and_live_override_are_used_without_execution(self):
        local = self.home / "config/linux-setup-local/zshrc"
        local.parent.mkdir(parents=True)
        local.write_text('# Check literal shell expressions.\nalias localprobe=\'touch "$PICKER_TEST_MARKER"\'\n')
        output = self.shell('source "$XDG_CONFIG_HOME/linux-setup-local/zshrc"\nalias localprobe=\'printf "%s" "$(touch "$PICKER_TEST_MARKER")"\'\n_dev_commands_list localprobe').stdout
        self.assertIn("Check literal shell expressions.", output)
        self.assertIn('$(touch "$PICKER_TEST_MARKER")', output)
        self.assertFalse((self.home / "executed").exists())

    def test_queries_can_begin_with_command_flags(self):
        output = self.shell("devhelp --follow").stdout
        self.assertIn("dclog\t", output)
        self.assertIn("--follow", output)
        self.assertNotIn("gpull\t", output)
        self.assertEqual(self.shell("_dev_commands_select --follow", PICKER_TEST_SELECT="dclog").stdout,
                         "docker compose logs --follow --tail=100")
        report = json.loads((self.home / "fzf.json").read_text())
        self.assertEqual(report["args"][report["args"].index("--query") + 1], "--follow")

    def test_selection_and_preview_keep_shell_expressions_literal(self):
        body = 'printf "%s" "$(touch "$PICKER_TEST_MARKER")" `touch "$PICKER_TEST_MARKER"`'
        result = self.shell("alias gs=" + shlex.quote(body) + "\n_dev_commands_select")
        self.assertEqual(result.stdout, body)
        report = json.loads((self.home / "fzf.json").read_text())
        self.assertIn(body, report["preview"])
        self.assertEqual(report["options"], "")
        self.assertEqual(report["options_file"], "")
        self.assertFalse((self.home / "executed").exists())

    def test_multiline_alias_is_preserved_for_editing(self):
        body = 'printf "%s\\n" first\nprintf "%s\\n" second'
        result = self.shell("alias gs=" + shlex.quote(body) + "\n_dev_commands_select")
        self.assertEqual(result.stdout, body)
        report = json.loads((self.home / "fzf.json").read_text())
        self.assertIn(body, report["preview"])

    def test_function_selection_inserts_a_call_and_previews_full_body(self):
        result = self.shell("_dev_commands_select", PICKER_TEST_SELECT="sshtunnel")
        self.assertEqual(result.stdout, "sshtunnel ")
        report = json.loads((self.home / "fzf.json").read_text())
        self.assertIn("ExitOnForwardFailure=yes", report["preview"])
        self.assertIn("Usage: sshtunnel", report["preview"])

    @unittest.skipUnless(FZF, "fzf is required to validate actual fuzzy matching")
    def test_actual_fzf_matches_name_description_and_full_command(self):
        for query, name, inserted in [
            ("gconflicts", "gconflicts", "git diff --name-only --diff-filter=U"),
            ("fast-forward", "gpull", "git pull --ff-only"),
            ("diff-filter", "gconflicts", "git diff --name-only --diff-filter=U"),
            ("ExitOnForwardFailure", "sshtunnel", "sshtunnel "),
        ]:
            with self.subTest(query=query):
                output = self.shell("_dev_commands_select", PICKER_TEST_FILTER=query, PICKER_TEST_SELECT=name).stdout
                self.assertEqual(output, inserted)

    def test_cancellation_preserves_line_and_cursor(self):
        output = self.shell('zle() { :; }\nBUFFER="original draft"\nCURSOR=3\n_dev_commands_widget\nprint -r -- "$BUFFER|$CURSOR"', PICKER_TEST_CANCEL="1").stdout
        self.assertEqual(output, "original draft|3\n")

    def test_key_bindings_cover_emacs_and_vi_modes(self):
        result = subprocess.run([ZSH, "-dfi", "-c", self.prelude + '''for keymap in emacs viins vicmd; do
  bindkey -M "$keymap" '^[x'
  bindkey -M "$keymap" '^[X'
done'''], env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.assertEqual(result.stdout.count('dev-commands'), 6)

    def terminal(self, action, cancel=False):
        pid, master = pty.fork()
        if pid == 0:
            os.execve(ZSH, [ZSH, "-dfi"], {**self.env, **({"PICKER_TEST_CANCEL": "1"} if cancel else {})})
        def close():
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            os.close(master)
            os.waitpid(pid, 0)
        self.addCleanup(close)
        setup = self.prelude + '''bindkey -e
alias gs='touch "$PICKER_TEST_MARKER"'
_capture_buffer() { print -rn -- "$BUFFER" > "$PICKER_TEST_BUFFER"; BUFFER=''; zle reset-prompt; }
zle -N capture-buffer _capture_buffer
bindkey '^G' capture-buffer
PROMPT='PICKER_READY> '
print -r -- PICKER_INITIALIZED
'''
        os.write(master, setup.encode())
        deadline = time.monotonic() + 8
        received = b""
        while b"\r\nPICKER_INITIALIZED\r\n" not in received and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                received += os.read(master, 65536)
        self.assertIn(b"\r\nPICKER_INITIALIZED\r\n", received, received.decode(errors="replace"))
        os.write(master, action)
        deadline = time.monotonic() + 8
        report = self.home / "fzf.json"
        while not report.exists() and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                received += os.read(master, 65536)
        self.assertTrue(report.exists(), received.decode(errors="replace"))
        os.write(master, b"\x07")
        buffer = self.home / "buffer"
        while not buffer.exists() and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                received += os.read(master, 65536)
        self.assertTrue(buffer.exists(), received.decode(errors="replace"))
        self.assertFalse((self.home / "executed").exists())
        return buffer.read_text()

    def test_alt_x_inserts_into_real_terminal_without_execution(self):
        self.assertEqual(self.terminal(b"\x1bx"), 'touch "$PICKER_TEST_MARKER"')

    def test_typed_devcommands_queues_editable_terminal_input(self):
        self.assertEqual(self.terminal(b"devcommands\r"), 'touch "$PICKER_TEST_MARKER"')

    def test_alt_x_cancellation_preserves_real_terminal_input(self):
        self.assertEqual(self.terminal(b"printf draft\x1bX", cancel=True), "printf draft")


if __name__ == "__main__":
    unittest.main()
