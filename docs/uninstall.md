# Uninstall programs, configuration, and caches

Run the uninstaller from the checkout:

```sh
./uninstall.sh
```

Choose to remove the terminal setup while keeping all programs, remove selected
programs, or remove all programs owned by the setup. All three choices restore
the previous configuration where it is still safe to do so.

## Program and cache checkboxes

In a program list, a checked item means **remove**; an unchecked item means
**keep**. Move with the arrow keys, toggle with Space, and accept with Enter.
Ctrl-A selects all and Ctrl-D clears all. Escape cancels. Programs start
unchecked. If fzf is unavailable, the text fallback displays numbered `[ ]`/`[x]`
choices: enter numbers to toggle them, `a` for all, `n` for none, Enter to accept,
or `q` to cancel.

Caches have their own checkbox list and also start unchecked. You can remove a
program and keep its cache, or keep the program and clear a listed cache. The
list displays paths so you can see exactly what is included. Shared caches are
identified: clearing one may affect another installation of the same tool.

The final preview lists the selected removals and retained resources before
confirmation. Canceling before confirmation makes no removals. Cache cleanup
can require future downloads or rebuilding; it does not remove your installed
Node/Python runtimes, project dependencies, shell history, or databases.

## Command-line use

```sh
./uninstall.sh --keep-tools --dry-run
./uninstall.sh --list
./uninstall.sh --keep-tools
./uninstall.sh --remove bat --remove fd
./uninstall.sh --keep-tools --cache setup-downloads --dry-run
./uninstall.sh --keep-tools --cache browser-deps --dry-run
./uninstall.sh --all-tools --dry-run
./uninstall.sh --all-tools
```

`--list` shows recorded program ownership and currently available cache IDs
without changing files. **Previously installed** means the program was migrated
from the earlier setup without a recorded version; it does not mean outdated.
Repeat `--remove NAME` for selected programs. Repeat
`--cache NAME` for cache IDs shown by the tool. `--dry-run` only previews;
`--yes` explicitly confirms a noninteractive operation and requires an explicit
mode or cache selection. It does not choose which programs to remove. Review the
same selection with `--dry-run` before using `--yes` in automation. Unspecified
programs and caches remain.

Available cache IDs depend on what exists on the device and which programs are
owned by the setup:

| Cache ID | Contents |
| --- | --- |
| `setup-downloads` | Verified archives downloaded by the installer |
| `setup-test-artifacts` | Extracted disposable PostgreSQL development-test binaries, if present |
| `browser-deps` | Libraries and fonts extracted by `dev-browser install --user-deps`, if present |
| `zsh` | Known completion dump files; shell history is preserved |
| `uv` | The known uv dependency cache; installed Python versions and tools are preserved |
| `oh-my-posh` | Known prompt cache directory |
| `bat` | Known compiled syntax/theme cache directory |

Only listed, validated cache locations are eligible. Arbitrary custom cache
directories and caches for external programs are left alone. Vite+ runtime/global
tool storage is deliberately not classified as disposable cache. Yazi's preview
cache is not offered because its temporary/configured location cannot be inferred
safely from the setup's ownership records; see its
[cache configuration](https://yazi-rs.github.io/docs/configuration/yazi/#cache_dir).

`browser-deps` refers only to
`${XDG_CACHE_HOME:-~/.cache}/linux-setup/browser-deps`. It stays unchecked by
default and can be removed independently of installed programs. Playwright's
`ms-playwright` browser cache is preserved. Removing these extracted dependencies
may require running `dev-browser install --user-deps` again for projects that use
them; no legacy browser-cache paths are inferred or migrated for removal.

For a selected uv cache, the uninstaller runs `uv cache clean` against the listed
directory before removing uv itself. This coordinates access with other uv
processes; its directory/lock may remain after the cached entries are cleared.
If cleanup fails, uv is retained so it can be retried. Manual deletion can
interfere with that coordination; see
[uv cache safety](https://docs.astral.sh/uv/concepts/cache/#cache-safety).

Removing the setup removes its prompt, aliases, custom helper links, and other
managed configuration. The checkout stays available for reinstalling and for
reviewing your portable customizations.

The historical `./install.sh --restore` command remains available for
configuration restoration. It keeps programs, caches, and the MCP registration;
use `./uninstall.sh` for selective removal and a saved removal report.

## Ownership and retained dependencies

The uninstaller uses the installation manifest, not a list of all executables
found on the system. Programs that predate the setup, including reused Vite+ or
uv installations, are not treated as setup-owned. System packages installed
manually remain the responsibility of the system package manager. This also
applies to the bootstrap system packages installed by
`./install.sh --install-prerequisites`: Python, Git, curl, and certificate trust
can be used by unrelated applications, so this uninstaller does not remove them
from APT. Review those separately with your system administrator if needed.

Managed base tools may share an extracted runtime. Removing one tool does not
delete libraries still required by another tool you keep. A shared runtime can
be removed after its last managed consumer is removed. Older manifests contain
less ownership information; uncertain artifacts are retained and reported.

Original files are restored from recorded backups only when their current
replacement still belongs to the installer. A file or link changed after
installation is kept for review. Changed files that still reference managed
program storage can also prevent that storage from being removed.

Recorded, unchanged setup-owned integrations are reversed. Pre-existing,
untracked, or subsequently changed MCP configuration is retained. The removal
summary explains unresolved items rather than assuming they belong to the setup.

## Login-shell protection

Deleting the executable listed as your account's login shell can prevent future
logins. When managed Zsh is selected for removal, the uninstaller requires a
successful change to another installed shell registered in `/etc/shells`.

For a specific replacement, use its absolute path:

```sh
./uninstall.sh --remove zsh --replacement-shell /bin/bash
```

The account change may require authentication. If it fails, Zsh is retained and
the uninstaller reports the command you can run manually. `--yes` does not bypass
this check. Existing shell processes may continue running after an uninstall;
start a fresh login session to use the restored configuration.

When keeping programs but removing the setup, ensure `~/.local/bin` is still on
the restored shell's PATH. Retained Vite+ may also need its official environment
hook in that shell. The uninstaller reports relevant retained resources.

## Preserved data and recovery

The checkout, personal local configuration, original backups, shell/directory
history, databases, projects, installed language runtimes, and database recovery
SQL are preserved. They are not disposable program caches.

The removal journal and report are saved at
`~/.local/state/linux-setup/uninstall.json` by default. If an operation is
interrupted, inspect the recorded plan and resume it:

```sh
./uninstall.sh --resume --dry-run
./uninstall.sh --resume
```

Resume uses the saved selections, including the replacement shell; do not combine
it with new program/cache selections. Completed operations are handled
idempotently. Review retained or unresolved paths in the final report before
doing any manual cleanup. A nonzero exit status indicates a cancellation or an
operation requiring attention; inspect the displayed reason.

To reinstall, run `./install.sh` from the retained checkout, then open a new Zsh
session. Do not erase the state directory while an uninstall or recovery is
unfinished: it contains the ownership information and original backup locations.
