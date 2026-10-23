# Development and maintenance

Portable configuration lives in `config/`, executable helpers in `bin/`, and
their implementation in `scripts/`. Machine-specific additions belong outside
the checkout in `~/.config/linux-setup-local/`.

## Local checks

Use Python 3.9 or newer:

```sh
bash -n install.sh uninstall.sh
python3 -m unittest discover -s tests -v
./install.sh --preflight
./install.sh --dry-run
./install.sh --check
./uninstall.sh --keep-tools --dry-run
```

Tests cover archive validation, installation/restore behavior, helper parsing,
process handling, and uninstall safety. Destructive uninstall tests use isolated
temporary directories and mocked account changes. Do not test full removal on a
working personal setup just to validate a code change.

For a real installation lifecycle check, run:

```sh
python3 scripts/smoke-install.py
```

The smoke script uses a disposable home with isolated XDG paths and Git settings.
It performs a fresh install, checks retained Zsh/uv/Vite+ after configuration-only
uninstall, removes a selected program and test cache, removes remaining managed
programs, reinstalls, and runs the doctor again. It skips MCP registration and
does not change the account's login shell. Network access is required for release
downloads and runtime setup. The temporary installation is removed when it exits.

To reuse already downloaded setup archives, pass their directory:

```sh
python3 scripts/smoke-install.py \
  --cache-from "$HOME/.cache/linux-setup/downloads"
```

This copies regular files into the disposable cache; it does not delete or
modify the source cache. Artifacts remain subject to the installer's checksum
verification. Vite+ bootstrap setup may still need network access.

Unit tests additionally cover interrupted operations, changed paths, external
programs, retained shared libraries, and login-shell protection. Verify the
keyboard UI separately in a real terminal, including Enter with no boxes checked.

CI is configured to run the unit suite with Python 3.9 and 3.12 on Ubuntu and
the real lifecycle smoke script on Ubuntu 24.04. CI success is evidence for the
checked platforms and scenarios, not proof that every Linux distribution or
architecture has been exercised. Keep the README support matrix aligned with
actual testing.

## Optional live PostgreSQL tests

The regular suite skips live tests unless server binaries are explicitly supplied:

```sh
LINUX_SETUP_TEST_POSTGRES_BIN=/path/to/postgresql/bin \
  python3 -m unittest discover -s tests -v
```

That directory must contain `initdb`, `pg_ctl`, and `postgres`, and their shared
libraries must resolve. `DEV_SETUP_TEST_POSTGRES_BIN` remains accepted for older
test scripts. `psql` alone is insufficient. Distribution packages are the easiest
way to obtain compatible binaries; extracted server packages may also need their
matching ICU, NUMA, and io_uring libraries.

The tests initialize a new temporary database cluster, listen through a private
Unix socket with TCP disabled, and stop/remove their cluster afterward. They do
not read project dotenv files or reuse an existing PostgreSQL service. Test
database/schema resets intentionally destroy only test data.

## Updating pinned tools

Review the requested upstream versions and release assets, then run:

```sh
python3 scripts/update-lock.py fd fzf yazi
git diff -- tools.lock.json
./install.sh
linux-doctor
```

The lockfile contains release versions, artifact URLs, SHA-256 hashes, and plugin
commits. Update plugin tags, commits, URLs, and hashes together. Never suppress a
checksum failure as a shortcut to making an installation pass.

Vite+ and uv are installed only when absent; an existing installation is kept
even after a lockfile update. Use their supported update workflow when you
intentionally want to upgrade an existing manager. Project runtime versions and
dependencies remain in each project's own configuration.

## Ownership and migration rules

Installer changes must record their owned resources before depending on the
uninstaller to remove them. Reused programs are external. Shared runtime paths
need consumer tracking. Generated integrations outside the main storage directory
need enough information to detect subsequent edits and restore original content.

Manifest writes and uninstall progress must survive interruptions. New migration
logic must preserve original backups, private configuration, and recovery files.
When ownership is uncertain, report and retain the path rather than infer
permission from its name alone. Dry runs must not create state or change links.

## Publishing changes

The upstream repository is [zdevzone/linux-setup](https://github.com/zdevzone/linux-setup).
Before committing, review the diff and staged file list. Publish only portable
source/configuration, tests, example values, and documentation. Real dotenv files,
credentials, private startup files, shell history, downloads, and local manifests
must remain outside the repository.

Preserve third-party notices and license files when updating bundled themes.
Downloaded tools retain their own upstream licenses; see [NOTICE.md](../NOTICE.md).
