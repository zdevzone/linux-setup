# linux-setup

A reproducible Linux terminal setup with Zsh, Oh My Posh, productivity tools,
development helpers, and selective uninstall. Clone it onto another device to
reuse the same configuration, pinned tools, aliases, and scripts.

The default prompt is **quick-term**, with orange `╰─ $` transient prompts and a
blank line between commands. The earlier customized `iterm2` theme is also saved.

## Get started

Clone or copy this folder to a persistent location, then run:

```sh
git clone https://github.com/zdevzone/linux-setup.git ~/linux-setup
cd ~/linux-setup
./install.sh --preflight
./install.sh --dry-run
./install.sh
exec zsh
linux-doctor
```

For a copied folder, start with `cd /path/to/linux-setup`. You can keep it anywhere;
rerun `./install.sh` if you move it. Keep the checkout: your live configuration
is linked to its files, so edits take effect without recopying them.

Prerequisites: Bash, **Python 3.9+**, trusted HTTPS/network access, and the
platform's base package tools. Git is needed to clone; downloading a ZIP also
works. On Ubuntu/Debian, `./install.sh --install-prerequisites` offers the required
system prerequisites and package-index refresh. This explicit option may request
administrator authentication; the normal tool installation uses your home directory.

| Platform | Installation |
| --- | --- |
| Ubuntu/Debian, x86_64 | Primary target. Missing base tools are extracted from APT packages into your home directory without sudo; package indexes must be available. Development testing used Ubuntu 26.04 x86_64. |
| Ubuntu/Debian, ARM64 | Linux release mappings are provided. Equivalent installation testing on ARM64 hardware has not yet been completed. |
| WSL with Ubuntu/Debian | Uses the Linux installation path. Install terminal fonts on Windows, where the terminal is rendered. |
| Other glibc Linux distributions | Install `zsh tmux file git curl lsof` and the PostgreSQL client (`psql`) with your package manager first. Compatibility depends on the pinned upstream binaries and the host libraries; these distributions are not yet integration-tested. |
| macOS / native Windows / musl Linux | Outside this release's supported targets. A native Windows/PowerShell setup is planned as a separate project. |

See [installation and migration](docs/installation.md) for prerequisites, file
locations, default-shell configuration, optional previews, and moving an existing
`dev-setup` installation.

The default install does not change your account's login shell. The terminal
emulator and its font selection remain settings of your device.

## Uninstall

```sh
./uninstall.sh                         # Interactive program and cache checkboxes
./uninstall.sh --keep-tools --dry-run   # Preview configuration removal only
./uninstall.sh --keep-tools            # Restore config; keep installed programs
./uninstall.sh --remove bat --remove fd # Restore config; remove selected programs
./uninstall.sh --all-tools             # Restore config; remove setup-owned programs
```

Programs and caches are kept unless selected. The uninstaller shows what it will
remove before asking for confirmation. Existing system/user installations are
preserved, as are the repository, personal settings, backups, history, projects,
and database recovery files. Removing the setup also removes its aliases and
prompt configuration; retained tools remain installed.

If the managed Zsh is your login shell, it cannot be removed until the account
successfully switches to another registered shell. Cache cleanup is optional and
can cause future downloads or rebuilding. See the [uninstall guide](docs/uninstall.md)
for selection keys, automation, shared dependencies, and recovery.

## Documentation

- [Installation, prerequisites, supported systems, and migration](docs/installation.md)
- [Developer workflow and project command reference](docs/developer-workflow.md)
- [Selective uninstall, cache choices, and recovery](docs/uninstall.md)
- [Troubleshooting and development findings](docs/troubleshooting.md)
- [Development, tests, and maintaining pinned versions](docs/development.md)

## Included tools

| Tool | Use |
| --- | --- |
| Zsh | Interactive shell, completion, persistent history |
| Oh My Posh | `quick-term` theme, spacing, transient prompts |
| fd / ripgrep (`rg`) | Find files / search their contents |
| fzf | Fuzzy selection and shell shortcuts |
| zoxide | Jump to frequently visited directories with `z` / `zi` |
| bat | File viewer with syntax highlighting |
| Yazi (`yazi`, `ya`) | File manager; use `y` to update your shell directory on exit |
| lazygit | Git interface, including delta diffs |
| tmux | Persistent sessions, windows, panes |
| eza | Detailed file listings and directory trees |
| delta | Git diffs with syntax highlighting and line numbers |
| jq | JSON querying and formatting |
| Vite+ (`vp`) | Manage Node.js runtimes, package managers, and the JavaScript toolchain |
| uv / uvx | Python versions, projects, packages, virtual environments, and tools |
| psql / lsof | PostgreSQL management client and TCP listener inspection |
| zsh-autosuggestions | Suggestions from history and completion |
| zsh-syntax-highlighting | Highlight valid commands and shell syntax |

`tools.lock.json` pins upstream release versions, URLs, SHA-256 checksums, and
plugin commits. Downloads are verified before installation. Repeated installs
reuse verified downloads and installed versions. Base packages follow the target
OS's repositories. This reproduces the
configuration and pinned tools, rather than freezing the entire operating system.

Vite+ and uv are **installed only when missing**. Existing installations and their
versions are preserved, including Vite+'s current and older installation locations and uv's older
Cargo location. The lockfile pins the versions used on fresh devices. A new Vite+
installation retains its full release bundle and runs `vp env setup` to prepare
its bootstrap dependencies, official environment, and runtime/package-manager
shims. Zsh loads that environment automatically. uv and uvx shell
completion is enabled when available. Runtime versions and project dependencies
remain controlled by each project's own configuration and lockfiles.
The bundled Linux Vite+ installer targets glibc distributions such as Ubuntu and
Debian, so it downloads matching Node.js runtimes. musl-based distributions are
outside the supported targets for this release.

Examples in a project directory:

```sh
vp env install lts         # Install a Node.js runtime through Vite+
vp install                # Install JavaScript project dependencies
vp run dev                # Run a project task
uv init                   # Create a Python project
uv add requests           # Add a Python dependency
uv run python             # Run Python in the project's environment
uvx ruff check .           # Run a Python tool without installing it globally
```

See the official [Vite+ guide](https://viteplus.dev/guide/) and
[uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).
For existing manager installations, use their supported upgrade commands;
rerunning this installer deliberately keeps their current versions.

Yazi's file search, text search, JSON previews, fuzzy navigation, and zoxide
integration have their companion tools installed. Extra preview formats are
optional: `ffmpeg` for video, Poppler for PDFs, and 7-Zip for archives. On Ubuntu:

```sh
sudo apt install ffmpeg poppler-utils 7zip
```

Install a Nerd Font in the device that renders the terminal and select it in
your terminal's font settings. For a local desktop, one option is
`oh-my-posh font install meslo`. In WSL or SSH sessions, the font belongs on the
Windows/desktop client. Terminal font and color settings cannot be selected
reliably without knowing the terminal emulator.

## Everyday shortcuts

| Command / key | Action |
| --- | --- |
| `ll`, `la`, `lt` | Detailed listing, all files, shallow tree |
| `ccat FILE` | View a file with bat |
| `z NAME`, `zi` | Jump by directory history / pick interactively |
| `y` | Open Yazi and follow its final directory |
| `lg` | Open lazygit |
| `fe` | Choose files with fzf and open them in `$EDITOR` |
| `cdf` | Choose and enter a directory |
| `search TEXT` | Search project contents with ripgrep |
| `mkcd DIR` | Create a directory and enter it |
| `up [N]` | Move up one or N directory levels |
| `..`, `...`, `....`, `.....` | Move up one, two, three, or four levels |
| `-`, `home`, `croot` | Previous directory, home, Git repository root |
| `work [DIR]` | Create or enter a tmux session for a project |
| `lip [PORT ...]` / `ports` | List TCP listeners, PIDs, and command names |
| `kip PORT [PORT ...]` | Confirm and send SIGTERM to the listeners on explicit ports |
| `serve [PORT] [DIR]` | Serve a directory on localhost (default port 8000) |
| `db [ENV_FILE]` / `dbm` | Interactive PostgreSQL database/schema manager |
| `dev-check [PATH]` | Read-only project dependency, Git, runtime, and Docker checks |
| `dev-browser doctor` | Check a project's Playwright/browser setup |
| `pathlist` | Print one PATH entry per line |
| `linux-doctor` / `dev-doctor` | Check installed tools and shell integration |
| `linuxsetup` / `devsetup` | Enter this repository |
| `reload` | Restart Zsh after config changes |
| `gs`, `gd`, `gds`, `gl` | Git status, diff, staged diff, recent graph |
| `ga`, `gc`, `gsw`, `gfetch` | Git add, commit, switch, fetch |
| Ctrl-R | Search command history with fzf |
| Ctrl-T | Select files with fzf and bat previews |
| Alt-C | Choose a directory with fzf |
| Right arrow | Accept an autosuggestion |

Standard commands such as `ls`, `cat`, `cd`, and `rm` keep their normal meanings.
Dot-prefixed commands are navigation shortcuts: `..`, `...`, and `....`.

tmux keeps **Ctrl-B** as the prefix. After the prefix, press `|` or `-` to split,
`h/j/k/l` to switch panes, `c` for a new window, `r` to reload config, and `d` to
detach. `work` names sessions by project directory plus a short path hash, so two
projects with the same directory name do not collide. Existing sessions are kept.

## Project checks and browser tests

```sh
dev-check                     # Inspect this checkout; --network opts into registry probes
dev-browser doctor            # Inspect the project's Playwright/browser setup
dev-browser install           # Download its pinned Chromium version
dev-browser run -- pnpm test:e2e
```

On Ubuntu/Debian, `dev-browser install --user-deps` can also extract required
APT libraries into a user cache without sudo. `run` applies those libraries only
to its child command. Project runtime versions, task names, dependencies, and
credentials remain project-owned. See the [developer workflow guide](docs/developer-workflow.md)
for the full recipe, optional aliases, environment checks, and database tools.

## Ports and local servers

```sh
lip                       # All visible TCP listeners
lip 3000 8000             # Only these ports
kip 3000                  # Show the matching processes and ask before stopping
kip --force 3000          # Explicit SIGKILL for a process that will not stop
dev-ports kill 3000 --yes # Explicit noninteractive confirmation
dev-ports list --json     # Structured listener information
serve 8000 ./public       # Bind only to 127.0.0.1; Ctrl-C stops the server
```

`kip` only signals visible PIDs still listening on the requested ports. It uses
SIGTERM by default, checks for changed listeners before signalling, and never
requests sudo. Processes owned by other users may require you to act as their
owner. A single process can listen on several ports; stopping it affects all of
its listeners. `lsof` is installed when needed; Linux can also inspect via `ss`.

## PostgreSQL database and schema manager

From a project's directory:

```sh
db                              # Read .env in the current directory
db .env.local                   # Read a different file
db -f ./config/development.env
db --var DATABASE_URL           # Only use this variable
db --var DB_URL --var TEST_DB_URL
db --connections                # Show redacted targets without connecting
db --maintenance-db app_admin   # If the role cannot connect to postgres
```

The installer supplies `psql`; this does **not** install or start a PostgreSQL
server. It uses the database role and permissions in the selected connection.
The server's `postgres` database is used for database-level operations by default.
Your role needs CONNECT there and the appropriate CREATE/ownership privileges.

Recognized variables include `DB_URL`, `DATABASE_URL`, `TEST_DB_URL`,
`TEST_DATABASE_URL`, `DB_URLS`, and `DATABASE_URLS`. Use `--var NAME` for any other
name. Multiple connections can be a JSON array or a named JSON object on a single line:

```dotenv
DATABASE_URL=postgresql://app:password@localhost:5432/my_project
DB_URLS='{"local":"postgresql://localhost/my_project","test":"postgresql://localhost/my_project_test"}'
# Or: DB_URLS='["postgresql://localhost/my_project","postgresql://localhost/my_project_test"]'
```

An example lives in `examples/postgres.env.example`. URL-encode special characters
in passwords. The parser supports `export`, quotes, inline comments, and `${VAR}`
references in double-quoted/unquoted values. It does not execute shell code.
Single quotes keep values literal. Credentials stay outside this repository;
passwords are supplied through a temporary mode-0600 password file and removed
after each `psql` call. Connection menus show names and endpoints without passwords.
Existing `.pgpass` authentication works when the URL contains no password.

Menus:

1. Select a connection, then **Databases** or **Schemas**.
2. For schemas, select the database to manage.
3. Choose **List**, **Create**, **Remove**, or **Reset**.
4. Use arrows to move, Space to select multiple targets, and Enter to accept.
   Escape returns to the previous menu. Ctrl-A selects all and Ctrl-D clears a
   batch selection. Single-choice menus accept Space or Enter.

Remove/reset shows the target server and object names and requires an exact typed
phrase such as `RESET app_test`. There are no table-management actions. Removing
or resetting a database/schema deletes its contained objects and data; schema
CASCADE can also remove dependent objects in other schemas.

- Database reset drops and recreates it from `template0`, preserving its owner,
  encoding/locale, tablespace, connection limit, access grants, and comment. Its
  custom schemas, data, installed extensions, and per-database settings are not
  restored. Active connections are **not** forcibly terminated.
- Schema reset drops and recreates the schema in one transaction, preserving its
  owner, access grants, and comment. A failed schema reset rolls back.
- Database reset cannot be atomic. If recreation fails after a successful drop,
  a private recreation script is kept under
  `~/.local/state/linux-setup/db-recovery/`; inspect the server and script before
  recovering. Other successful targets in a batch are not rolled back.
- `postgres`, template databases, the selected maintenance database, and system
  schemas are excluded from destructive selection. `public` is a user schema and
  can be explicitly reset or removed after confirmation.

SSL options such as `sslmode=require` are respected. Common ORM-only fields
(`schema`, `connection_limit`, `pool_timeout`, `pgbouncer`, `socket_timeout`, and
`statement_cache_size`) are ignored. Other unsupported URL options produce an
error rather than being silently discarded. Use a direct database endpoint when
a transaction-pooling proxy disallows database-level DDL.

Tests never read your project `.env` or connect to its databases. To additionally
run the integration tests, point this command at installed PostgreSQL **server**
binaries; the test creates, starts, and removes its own private cluster:

```sh
LINUX_SETUP_TEST_POSTGRES_BIN=/path/to/postgresql/bin \
  python3 -m unittest discover -s tests -v
```

## Customize your setup

```text
linux-setup/
├── install.sh                 # Bootstrap entry point
├── uninstall.sh               # Configuration, program, and cache removal
├── tools.lock.json            # Pinned release assets and plugin commits
├── bin/                       # Your portable executable scripts
├── config/
│   ├── zsh/                   # Shell settings, aliases, functions
│   ├── oh-my-posh/             # quick-term and iterm2 prompt themes
│   ├── tmux/                  # Pane, session, key, and status settings
│   ├── git/                   # Included delta settings
│   ├── bat/                   # File viewer settings
│   ├── ripgrep/               # Search settings
│   ├── yazi/                  # File manager settings
│   ├── lazygit/               # Git interface settings
│   └── codex/                 # Reference Oh My Posh MCP entry
├── scripts/                   # Installer, uninstaller, helpers, lock updater
├── docs/                      # Installation, recovery, troubleshooting, development
└── tests/                     # Installer, uninstall, helper, and isolated DB tests
```

Add shared aliases to `config/zsh/aliases.zsh`, functions to
`config/zsh/functions.zsh`, and executable scripts to `bin/`. Rerun the installer
to link new scripts. Edit the active theme in
`config/oh-my-posh/quick-term.omp.json`. Change its path in `config/zsh/zshrc` to
switch themes. Use `reload` after changing shell initialization or prompt settings.

Private or device-specific additions go in:

```text
~/.config/linux-setup-local/zshenv  # Environment needed by all Zsh processes
~/.config/linux-setup-local/zshrc   # Interactive additions, editor choice, local aliases
```

For example, put `export EDITOR='nvim'` in the local zshrc if Neovim is installed.
The initial migration preserves the existing Vite+ environment hook in the local
zshenv. Other old files are backed up for reference. Your Git identity, credentials,
SSH keys, shell history, project files, downloaded binaries, and private Codex
settings are not copied into the repository.

XDG config/data/cache/state directories are respected. Executables always go in
`~/.local/bin`. Rootless base-package binaries and their runtime paths are
generated separately on each device.

`LINUX_SETUP_DIR` points to the active checkout through its configuration link.
`DEV_SETUP_DIR` remains a compatibility alias for existing personal scripts.

## Maintenance and recovery

```sh
./install.sh --config-only --skip-mcp  # Link config without downloading tools
./install.sh --preflight              # Check installation prerequisites
./install.sh --check                  # Same checks as linux-doctor
./install.sh --mcp-only               # Register the Oh My Posh MCP in existing Codex
./install.sh --restore                # Restore configs; keep programs/caches/MCP
./uninstall.sh --keep-tools           # Restore configuration; retain programs
python3 -m unittest discover -s tests -v
```

The default install registers `https://ohmyposh.dev/api/mcp` as `oh-my-posh` when
Codex is installed and that registration is absent. An existing registration is
preserved. Use `--skip-mcp` to skip this. Restart Codex to load a new server.
Uninstallation reverses recorded, unchanged setup-owned integrations.
Pre-existing or older untracked MCP registrations remain for manual review.
The historical `--restore` option restores only setup configuration and the Git
include; it retains installed programs, caches, and the MCP registration. Prefer
the uninstaller for a complete removal plan and report.

Original files are moved to timestamped directories under
`~/.local/state/linux-setup/backups/`. The deployment manifest records what was
replaced and which programs belong to this setup. Restoration only touches paths
still owned by the installer; changed files are left for you to review. Use the
uninstaller to choose whether installed programs and caches also go.
Existing tmux servers are not restarted automatically; reload with Ctrl-B, then r.

To update selected pinned tools, review and commit the lockfile changes:

```sh
python3 scripts/update-lock.py fd fzf yazi
./install.sh
linux-doctor
git diff -- tools.lock.json
```

Plugin commits are intentionally explicit in the lockfile; update their release
tag, commit, archive URL, and SHA-256 together. The lock updater does not silently
upgrade plugins or existing Vite+/uv installations.

If a download fails, rerun the installer; completed verified downloads are reused.
If APT cannot locate a missing base package, update your OS's package indexes
using its usual administration workflow, then rerun.

## Set Zsh as your default shell

The installer adds tools to Zsh's PATH. To change the account's login shell, run
these yourself, authenticating when required:

```sh
command -v zsh
# Register this path only if it is not already present:
grep -qxF "$HOME/.local/bin/zsh" /etc/shells || \
  printf '%s\n' "$HOME/.local/bin/zsh" | sudo tee -a /etc/shells
chsh -s "$HOME/.local/bin/zsh"
```

If your device uses a system-provided Zsh and has no `~/.local/bin/zsh`, use the
absolute path printed by `command -v zsh` in both commands. Log out and back in.

## Share your configuration

The project repository is [zdevzone/linux-setup](https://github.com/zdevzone/linux-setup).
Fork it to maintain your own shared configuration. Commit portable changes, then
pull on your other devices and rerun the installer when adding or updating tools
or scripts. Installation itself never publishes your files.

Keep secrets and device-specific additions in the local configuration directory,
outside the checkout. Real dotenv files, credentials, shell history, runtime
downloads, and project databases do not belong in the repository.

Upstream project links and theme attribution are in [NOTICE.md](NOTICE.md).
