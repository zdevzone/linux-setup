# Documentation

[Project overview](../README.md) · [Terminal previews](previews.md)

Start with installation, then choose a guide for the task you want to do.

| Guide | What you will find |
| --- | --- |
| [Installation and migration](installation.md) | Supported systems, prerequisites, first install, file locations, default shell, migration |
| [Terminal commands](terminal.md) | Keyboard shortcuts, Alt+X command picker, navigation, tmux, ports and local servers |
| [Developer workflow](developer-workflow.md) | Project checks, browser testing, language and container shortcuts, private commands |
| [Included tools](tools.md) | Installed tools, Vite+, uv, version pinning, optional previews |
| [Themes and customization](customization.md) | Theme switching, shared configuration, private device settings, repository layout |
| [PostgreSQL manager](databases.md) | Connection discovery, database/schema actions, confirmations, recovery |
| [Uninstall and recovery](uninstall.md) | Selective removal, retained programs, caches, backups and login-shell protection |
| [Troubleshooting](troubleshooting.md) | Downloads, missing libraries, completion, and known platform issues |
| [Development and maintenance](development.md) | Tests, isolated install lifecycle checks, lockfile updates, publishing |
| [Preview gallery](previews.md) | Theme and picker images, sample data, how to regenerate the assets |

## Where to make a change

| Change | Location |
| --- | --- |
| Shared aliases | [`config/zsh/aliases.zsh`](../config/zsh/aliases.zsh) |
| Shell functions | [`config/zsh/functions.zsh`](../config/zsh/functions.zsh) |
| Alt+X picker | [`config/zsh/command-picker.zsh`](../config/zsh/command-picker.zsh), [`scripts/command_catalog.py`](../scripts/command_catalog.py) |
| Prompt themes | [`config/oh-my-posh/`](../config/oh-my-posh/) |
| Portable commands | [`bin/`](../bin/) and [`scripts/`](../scripts/) |
| Tool versions and checksums | [`tools.lock.json`](../tools.lock.json) |
| Private settings | `~/.config/linux-setup-local/zshrc` and `zshenv` on your device |

Keep credentials, machine-specific paths, and real project environment files out
of the checkout. Follow [development guidance](development.md) when contributing.
