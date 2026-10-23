# Installation and migration

`linux-setup` installs a repeatable Linux terminal configuration and a pinned set
of command-line tools. It links configuration to this checkout, so keep the
checkout in a persistent location.

## Supported systems

Ubuntu/Debian on x86_64 is the primary target; development testing used Ubuntu
26.04 x86_64. ARM64 release mappings are included but still need equivalent
hardware validation. Ubuntu/Debian inside WSL uses the same Linux installation
path. Other glibc distributions need their own base packages installed first and
are not yet integration-tested. Native Windows/PowerShell, macOS, and musl Linux
are outside this release's supported targets.

Pinned binaries still depend on compatible host libraries. Pinning tools does
not freeze the operating system or guarantee compatibility with every older
distribution release.

## Before starting

Required bootstrap components are Bash, Python 3.9 or newer, a working HTTPS
connection, and trusted certificate authorities. Git is needed to clone the
repository; a downloaded ZIP is another way to obtain the files. On Ubuntu/Debian,
rootless base-tool installation also requires `apt-get`, `dpkg-deb`, and populated
package indexes.

```sh
git clone https://github.com/zdevzone/linux-setup.git ~/linux-setup
cd ~/linux-setup
./install.sh --preflight
./install.sh --dry-run
./install.sh
exec zsh
linux-doctor
```

The preflight checks prerequisites before installation. The dry run describes the
installation without applying it. Downloaded artifacts are verified against the
SHA-256 values in `tools.lock.json`; repeat installs reuse verified downloads.

If Ubuntu/Debian bootstrap prerequisites or current package indexes are missing:

```sh
./install.sh --install-prerequisites
```

This explicit option displays the administrative package operations before
requesting authentication. It prepares Python, Git, curl, certificate trust, and
APT indexes, then continues the normal installation. To preview both stages, add
`--dry-run`; `--yes` explicitly confirms the administrative prerequisite commands
for automation. Normal tool installation does not need sudo: missing base programs
are extracted into your user directory. On restricted devices, ask the system
administrator to provide prerequisites instead.

On other compatible glibc Linux distributions, install Bash, Python 3.9+, Git,
curl, CA certificates, Zsh, tmux, `file`, `lsof`, and the PostgreSQL client (`psql`)
through the distribution's package manager before running this installer.

Do not run the entire installer with `sudo`; it is intended to configure the
current user's home directory.

## What gets installed

The [README tool table](../README.md#included-tools) lists the included programs.
Already available base programs are reused. Existing Vite+ and uv installations
are preserved. Fresh Vite+/uv installations use the lockfile versions.

The PostgreSQL dependency is the `psql` client only. Installing it does not create
a database cluster or start a server. Your applications retain responsibility for
their Node/Python versions and dependency lockfiles.

The ownership manifest records managed programs, configuration links, backups,
and integrations so the [uninstaller](uninstall.md) can separate setup-owned
resources from pre-existing installations.

Default locations, respecting the corresponding XDG variables:

| Content | Default location |
| --- | --- |
| Configuration checkout link | `~/.config/linux-setup` |
| Private machine additions | `~/.config/linux-setup-local/` |
| Executable entry points | `~/.local/bin/` |
| Managed programs and plugins | `~/.local/share/linux-setup/` |
| Downloads and setup caches | `~/.cache/linux-setup/` |
| Manifest, backups, recovery records | `~/.local/state/linux-setup/` |
| Zsh history | `~/.local/state/zsh/history` |

The installer backs up configurations it replaces. The Git include applies this
project's diff settings without copying your Git identity into the repository.
If Codex is present and the `oh-my-posh` MCP registration is absent, the normal
install adds the endpoint. An existing registration is preserved. Use `--skip-mcp`
to leave that integration alone.

## Migrating from dev-setup

Run the current installer from the renamed or freshly cloned `linux-setup`
checkout. It recognizes the earlier `dev-setup` directories and manifest,
preserves original backups and personal additions, and updates managed paths.
Compatibility paths may remain so older wrappers and customizations continue to
resolve. Do not delete those paths by hand while retained tools still use them.

`LINUX_SETUP_DIR` is the canonical environment variable; `DEV_SETUP_DIR` remains
available for existing scripts. The familiar `dev-doctor`, `devsetup`, `dev-db`,
and `dev-ports` commands remain usable. New branding also provides `linux-doctor`
and `linuxsetup`.

Migration is repeatable after interruption. If both old and new locations contain
different data, the installer reports the conflict instead of overwriting it.
Resolve the reported paths and rerun; never remove backups or recovery records
just to clear a conflict. Earlier manifests have incomplete program ownership,
so uninstallation keeps uncertain resources and reports them for review.

To move a checkout later, move/copy it to its persistent destination and rerun
`./install.sh` there to repair managed links. Open a new shell afterward.

## Default shell

Installing Zsh and setting the account's login shell are separate operations.
Inspect the installed executable first:

```sh
command -v zsh
```

Use that absolute path. If it is missing from `/etc/shells`, an administrator must
register it. Then run `chsh -s /absolute/path/to/zsh` and authenticate when asked.
Log out and back in for the account change to take effect.

If you choose the managed `~/.local/bin/zsh`, removing it later requires switching
the account to another registered shell first. The uninstaller checks this.

## Optional terminal features

Choose a Nerd Font in the terminal emulator that renders your session. With WSL
or SSH, that is normally the Windows/desktop client, not the remote Linux host.
One font installation option on a local desktop is
`oh-my-posh font install meslo`; select it in the terminal settings afterward.

Extra Yazi previews use optional tools:

```sh
sudo apt install ffmpeg poppler-utils 7zip
```

These provide video, PDF, and archive previews. Packages installed manually with
this command belong to the system package manager; the setup uninstaller does
not claim or remove them. Basic file navigation, search, JSON previews, and fuzzy
selection use the tools already included in the setup.

For download errors, missing libraries, or completion problems, see
[troubleshooting](troubleshooting.md).
