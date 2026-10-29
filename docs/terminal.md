# Terminal commands and keyboard shortcuts

[Documentation](README.md) · [Project overview](../README.md)

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
| Alt-X / `devcommands [QUERY]` | Search custom aliases/functions and insert a selection for editing |
| `devhelp [TEXT]` | List custom commands, descriptions, and full definitions |
| Right arrow | Accept an autosuggestion |

Standard commands such as `ls`, `cat`, `cd`, and `rm` keep their normal meanings.
Dot-prefixed commands are navigation shortcuts: `..`, `...`, and `....`.

Press **Alt+X** in Zsh to open the command picker. Search by shortcut, description,
or any part of the full command; the preview shows the entire alias expansion or
function definition. Enter replaces the current command line with the selection
without executing it. Aliases insert their expanded command; functions insert
their name followed by a space for arguments. Edit it, then press Enter yourself
when ready. Escape or Ctrl-C leaves your original command line unchanged.
`devcommands` opens the same picker from a typed command; `devhelp` prints the list.
If your terminal intercepts Alt+X, press Escape followed by x, or use `devcommands`.

The catalogue reads the active definitions of shortcuts declared in this repo's
Zsh files and your private `linux-setup-local/zshrc` and `zshenv`. Add a description
comment directly above each `alias name='command'` or `name() { ... }`, then
`reload`; new commands appear automatically. Optional tool shortcuts still need
their corresponding tools installed. See the [workflow guide](developer-workflow.md)
for the included command groups and examples.

tmux keeps **Ctrl-B** as the prefix. After the prefix, press `|` or `-` to split,
`h/j/k/l` to switch panes, `c` for a new window, `r` to reload config, and `d` to
detach. `work` names sessions by project directory plus a short path hash, so two
projects with the same directory name do not collide. Existing sessions are kept.

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
