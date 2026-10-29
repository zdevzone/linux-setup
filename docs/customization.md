# Customize your terminal setup

[Documentation](README.md) · [Project overview](../README.md)

## Switch the prompt theme

The default is `quick-term`. Both bundled themes are Oh My Posh configurations
for Zsh; the `iterm2` name does not require the iTerm2 application.

| Theme | Appearance | Configuration |
| --- | --- | --- |
| Quick-term | Orange accents, two-line prompt, duration and clock, compact command history | [`quick-term.omp.json`](../config/oh-my-posh/quick-term.omp.json) |
| iTerm2 | Blue and lime segments, exit-status color, rocket prompt, contextual segments | [`iterm2.omp.json`](../config/oh-my-posh/iterm2.omp.json) |

To try the alternative in your current Zsh session:

```zsh
eval "$(oh-my-posh init zsh --config "$LINUX_SETUP_DIR/config/oh-my-posh/iterm2.omp.json")"
```

To make it the shared default, change the `--config` path in
[`config/zsh/zshrc`](../config/zsh/zshrc) from `quick-term.omp.json` to
`iterm2.omp.json`, then run `reload`. To keep the choice private to one device,
put the initialization command above in `~/.config/linux-setup-local/zshrc`,
which loads after the shared prompt configuration. Remove that override to use
the shared default again.

Use a Nerd Font in your terminal emulator. Font, terminal colors, Git state,
screen width, and available hardware affect the appearance. Battery and Python
environment segments in the alternative theme appear when their context is
available. See the [preview gallery](previews.md) for both themes and the command
picker, and [font setup](installation.md#optional-terminal-features) for details.

## Repository layout

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
