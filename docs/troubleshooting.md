# Troubleshooting and development findings

Start with `./install.sh --preflight` for installation prerequisites and
`linux-doctor` for installed tools and shell integrations. Run checks as the user
whose terminal is being configured.

The findings below come from developing and testing this setup. Some are specific
to the test environment; they are not universal requirements for every machine.

## Missing Python or bootstrap tools

The installer requires Python 3.9 or newer, not merely a command named `python3`.
Check `python3 --version`. On Ubuntu/Debian,
`./install.sh --install-prerequisites` offers the required system prerequisites.
If administrative authentication is unavailable, an administrator must supply
these bootstrap components. Once they exist, normal managed-tool installation can
run without sudo.

Downloading a ZIP avoids requiring Git just to obtain the source, but Git is
still part of the configured development toolset.

## APT cannot find a package

The rootless installer uses the host's APT package indexes to resolve package
versions and dependencies. Empty or stale indexes can prevent dependency
resolution or point at package versions no longer on the mirror.

Refresh them with the prerequisite option or the distribution's normal
administration workflow, then rerun. The normal installer extracts `.deb` files
into user storage; it does not install or remove those packages in the system
package database. `apt-get` and `dpkg-deb` must both be available.

## No sudo access

Development took place in an environment where sudo required interactive
authentication. This is why base tools can be extracted into the user's home
directory. Lack of sudo alone does not prevent installation when the bootstrap
tools and package indexes already exist.

Refreshing system indexes, installing missing bootstrap prerequisites, or
changing the account's login shell can still require administrative cooperation.
The installer reports these separately instead of running the whole setup as
root.

## Downloads, TLS, and checksums

The setup needs access to upstream release hosts, including GitHub, and a working
CA certificate store. Use the environment's configured proxy and trust settings;
do not disable certificate verification to make downloads work.

Rerun after a temporary network failure. Verified archives are reused. A checksum
mismatch is an error, not an invitation to replace the expected hash blindly.
Review the upstream release and lockfile before changing pinned values.

## Vite+ or its Node runtime cannot start

During development, using a musl Vite+ build on Ubuntu caused its runtime selection
to fetch a musl Node build incompatible with the glibc host. Fresh installations
now use the Linux GNU/glibc Vite+ assets for Ubuntu/Debian. musl distributions are
outside the supported targets for this release.

Vite+ also needs its full release bundle and `vp env setup`, not just a copied
`vp` executable. The installer retains the bundle and sets up the official
environment and shims. Existing Vite+ and uv installations are preserved; if an
existing installation is broken, repair it using that tool's supported workflow
and rerun the checks.

If Vite+ works by absolute path but not in a new shell, check its environment hook
and PATH. After keeping Vite+ during uninstall, a restored Bash or other shell
may need the official hook added to its own startup file.

## Rootless psql errors

Debian's `/usr/bin/psql` can be a wrapper expecting a system PostgreSQL
installation. That wrapper does not work reliably for packages extracted under
a user's home directory. The setup runs the versioned client executable from
the managed PostgreSQL package instead.

Only the client is required for `db`. A database server must already be available
at the chosen URL. Authentication, CREATE privileges, ownership, SSL policy, and
the maintenance database are properties of that server and account. The helper
does not bypass them. Use `db --connections` to inspect redacted targets without
connecting.

Database/schema reset deletes contained data. Its recovery SQL recreates the
database definition after a failed recreation; it is not a backup of deleted
data. Keep application/database backups separately.

## Completion and shell startup messages

The development host contained dangling vendor completion links, including a
Docker Desktop completion entry. The setup builds a filtered completion path
without modifying `/usr`, so missing host targets are not loaded.

The Ubuntu 24.04 CI runner also exposed completion directories that Zsh's security
audit rejected. `compinit -i` skips those insecure directories, allowing completion
initialization to finish without a prompt in noninteractive checks. It does not
mark their contents trusted or change host permissions. If a completion is missing,
inspect the relevant directory's ownership and permissions.

Noninteractive shell probes also exposed ZLE messages from fzf restoring editor
options without a terminal. The setup now initializes fzf's editor widgets only
when standard input is a terminal. Interactive editor integrations belong in an interactive terminal;
if a diagnostic still prints a startup error, capture the command and error text
and inspect private additions under `~/.config/linux-setup-local/` as well as the
managed configuration. Never publish your full environment or shell history in a
bug report.

If a rootless Zsh reports missing modules after moving the checkout, rerun the
installer from its new location and open a fresh shell. Do not delete the managed
runtime while it remains the account's login shell.

## Missing icons or previews

Square boxes in the prompt usually indicate the terminal is not using a Nerd
Font. Install and select the font on the device rendering the terminal. With WSL
or SSH this may be the Windows/desktop client rather than Linux.

Yazi video/PDF/archive previews need optional `ffmpeg`, Poppler, and 7-Zip
packages. Their absence does not mean the base terminal setup failed. See
[installation](installation.md#optional-terminal-features).

## Live PostgreSQL tests need more than psql

Normal use requires only the client. Optional integration tests require
`initdb`, `pg_ctl`, and `postgres` server binaries, plus those binaries' runtime
libraries. Development with extracted Ubuntu PostgreSQL packages also required
matching `libpq`, `libicu`, `libnuma`, and `liburing` libraries. When using extracted
packages, include both the server and client library directories in the test
process's `LD_LIBRARY_PATH`; a missing `libpq.so.5` is a client-library lookup
failure, not a database authentication problem. Package names and versions
depend on the distribution.

Those test-only dependencies are not normal user installation prerequisites.
The tests create a disposable cluster with a private Unix socket, start no
permanent service, and remove the cluster afterward. See the
[development guide](development.md#optional-live-postgresql-tests).

## Uninstall retains a resource

A retained resource normally means it predates the setup, has been changed,
belongs to an uncertain older installation, is shared with a kept program, or is
the account's current login shell. Read the specific reason in the report.

Clearing caches does not authorize deleting histories, managed language runtimes,
project data, or recovery files. See the [uninstall guide](uninstall.md) before
manual cleanup.
