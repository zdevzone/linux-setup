# Included tools and runtime managers

[Documentation](README.md) · [Project overview](../README.md)

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
