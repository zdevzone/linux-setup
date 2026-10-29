# Developer workflow

[Documentation](README.md) · [Project overview](../README.md)

Run project commands from the relevant checkout. This setup supplies shared
tools; each project keeps its own runtime version, package manager, dependencies,
tasks, and credentials.

## Activate new helpers in an existing installation

After the changes are merged, update your persistent installation checkout
and refresh its configuration links:

```sh
cd ~/linux-setup                 # Use your actual installation checkout
git pull --ff-only
./install.sh --config-only --skip-mcp
exec zsh
```

Use the persistent checkout for installation, rather than a temporary review
worktree. Configuration-only installation keeps existing tools and their versions.

## Check a checkout

```sh
dev-check                       # Read-only checks for the current project
dev-check ../another-project     # Check another checkout
dev-check --json                 # Machine-readable results
dev-check --network              # Also probe registry reachability
linux-doctor                    # Check the terminal setup itself
```

`dev-check` inspects manifests, lockfiles, dependency markers, Git checkout status, and
tool availability. A Compose filename enables a local Docker check. It does not
install packages, start services, source dotenv files, or run project tasks.
The optional npm registry probe requires `--network`.

JSON `ready: true` and exit status 0 mean no failure was detected. Review warnings
and skipped checks: PnP dependencies and remote Docker contexts can remain
unverified. Follow the reported next steps in the project's own setup guide.

## Find and review work

| Command | Use |
| --- | --- |
| `rg --files` | List project files using ignore rules |
| `fd config` | Find paths matching a name |
| `rg -n 'pattern' src tests` | Search selected source directories |
| `jq '.scripts' package.json` | Inspect JavaScript project tasks |
| `git status --short --branch` | Review branch and local changes |
| `git diff`, `git diff --staged` | Review pending and staged changes |
| `git worktree list` | Locate other checkouts of the repository |
| `lg` | Open the installed Git interface |

## Run project tasks

Use the repository's pinned runtime and package manager. `vp` supports the
JavaScript workflow; projects can also call their selected manager directly.
Examples below assume those task names exist:

```sh
vp install                      # Install the project's dependencies
vp run dev
vp run test
vp run typecheck
pnpm env:check                  # When the project defines this Varlock task
uv sync                        # Install a Python project's locked environment
uv run pytest                  # When pytest belongs to that project
```

Keep Varlock schemas and application-specific scripts in their projects. A
shared shell helper should not choose new dependency versions or copy a
project's secrets into global configuration. In this repository, the Python
check is `python3 -m unittest discover -s tests -v`; see
[development checks](development.md) for the complete maintenance workflow.

## Prepare browser tests

Install the project's dependencies first so its pinned Playwright package is
available. From that project, use:

```sh
dev-browser doctor
dev-browser install --user-deps
dev-browser run -- pnpm test:e2e
```

`doctor` reports installed paths and launches and closes headless Chromium to
check that it works. `install` downloads the Chromium version selected by the project's Playwright package;
it does not install or upgrade Playwright globally. Omit `--user-deps` when the
host already provides the required libraries. The initial supported browser
workflow is headless Chromium.

On Ubuntu/Debian, `--user-deps` explicitly downloads and extracts APT packages
into `${XDG_CACHE_HOME:-~/.cache}/linux-setup/browser-deps`. It does not use sudo
or update APT indexes, so package indexes must already be available. Chromium
itself uses Playwright's normal browser cache. Extracted libraries and fonts
apply only to commands launched by the helper; your shell's global
library configuration stays unchanged. `run` returns that command's exit code.

Rootless installation accepts only the recognized Playwright dependency-report
format. An unfamiliar or older dry-run format stops before APT downloads;
follow the displayed administrator-assisted `playwright install-deps chromium`
guidance instead. The helper does not upgrade Playwright to change its output.

Replace `pnpm test:e2e` with the project's actual browser-test command. Use
`dev-browser --project /path/to/project doctor` to target another checkout.
The browser helper does not read dotenv files itself; it executes the project's
installed Playwright and your chosen test command. On hosts without the supported
APT workflow, use the administrator-managed system dependencies documented by
[Playwright](https://playwright.dev/docs/browsers#install-system-dependencies).
The optional browser dependency cache can be selected for removal
in the uninstaller; ordinary uninstall keeps it.

## Inspect local services

```sh
lip 3001 5173                    # List listeners for an API and web server
kip 5173                        # Confirm before stopping the matching process
docker compose ps               # Inspect this project's Compose services
db --connections                # List redacted .env targets without connecting
db .env.local --connections      # Select a different dotenv file explicitly
db --var TEST_DATABASE_URL       # Open the interactive manager for that target
```

The database helper discovers `TEST_DATABASE_URL` and `TEST_DB_URL` alongside
the usual `DATABASE_URL`/`DB_URL` names. It parses the selected file as data and
does not source shell commands. `db --connections` is an inspection command;
the interactive manager also offers database changes with confirmation. Keep
test URLs pointed at disposable databases. Installing `psql` does not start a
database server.

## Discover and use custom commands

Press **Alt+X** (both lowercase and uppercase x work) or run `devcommands` to open
the fzf picker. Type part of a shortcut, its description, or its full command.
The preview includes the full definition, even for multiline functions. Ctrl-/
toggles the preview. Enter inserts the selection into the editable prompt and
does not execute it. An alias inserts its expansion; a function inserts its name
and a trailing space so you can supply arguments. Selecting replaces the current
line; Escape or Ctrl-C preserves the line and cursor. The binding works in Emacs
and vi keymaps. If your terminal uses Alt+X for a menu, use Escape then x or the
`devcommands` command.

```sh
devcommands docker              # Open with an initial search
devhelp                         # Print the current reference without fzf
devhelp pnpm                    # Filter the printed reference by text
```

The picker uses live shell definitions and description comments from
`config/zsh/aliases.zsh`, `functions.zsh`, `command-picker.zsh`, and private
`linux-setup-local/zshrc` / `zshenv`. It excludes internal helper functions and
shortcuts that were not loaded, including conditional aliases for absent tools.
It does not call any of the commands to build the list. Regular aliases and named
functions declared in these files are supported; dynamically generated commands
and commands in other sourced files are outside this catalogue.

Included shortcuts:

| Group | Examples |
| --- | --- |
| Project scripts and dependencies | `pscripts`, `pd`, `pb`, `pt`, `pcheck`, `pr TASK`, `pi`, `pif`, `pa`, `pad`, `px`, `pfilter` |
| Vite+ | `vpi`, `vr TASK`, `vcheck`, `vfmt`, `vtest`, `vwatch` |
| Rust and Laravel | `cgb`, `cgc`, `cgt`, `cgr`, `cgl`, `cgrelease`, `art`, `arts`, `artt`, `sail` |
| Git and GitHub | `gfind TEXT`, `gbranches`, `gconflicts`, `gpull`, `ghprs`, `ghpr`, `ghchecks`, `ghruns` |
| Containers | `dctx`, `dctxs`, `duse`, `dpsa`, `dccheck`, `dcservices`, `dcup`, `dcstop`, `dclog`, `dsh`, `dcsh` |
| Kubernetes and Terraform | `kctx`, `kcontexts`, `kuse`, `kpods`, `klogs`, `kdesc`, `tfinit`, `tfvalidate`, `tffmtcheck`, `tfplan` |
| Host and network | `disks`, `mem`, `dus`, `listens`, `ipbrief`, `svcfailed`, `jerrors`, `junit`, `httpcheck`, `sshtunnel` |
| PostgreSQL and JSON | `pgconnect SERVICE`, `pg-local`, `pg-remote`, `pg-bingo`, `jpretty`, `jcompact` |
| AI agents and project checks | `cx`, `cxr`, `cxc`, `cxe`, `cld`, `cldr`, `cldc`, `dcheck`, `dbr` |

Project script names must exist in `package.json`; use `pscripts` to inspect them.
Direct Vite+ tools can bypass a project's wrappers, so use `pcheck` and `pt` for
its full check/test scripts. Container commands use the active Docker context;
`dsh CONTAINER [SHELL]` and `dcsh SERVICE [SHELL]` default to `sh`. Existing Docker
reset shortcuts and `dc` help remain available, including their volume-deleting
operations. PostgreSQL shortcuts use profiles you configure privately in
`~/.pg_service.conf`, with normal password prompt or `~/.pgpass` authentication.
Kubernetes, Terraform, GitHub, Docker, language tools, and agent CLIs must be
installed separately if missing; adding an alias does not install its target.

For private additions, put a comment immediately above each alias or function
in `~/.config/linux-setup-local/zshrc`, then run `reload`:

```sh
# Follow this project's API logs.
alias apilogs='docker compose logs --follow api'

# Check the current project's package scripts.
project_scripts() { command jq '.scripts // {}' package.json; }
```

Keep credentials in the appropriate project's ignored files or configured
secret provider. Paid UI registry keys belong only in their component-install
workflow, with no `VITE_` prefix and no browser import. Use the project's
redacted configuration checks when sharing diagnostics.
