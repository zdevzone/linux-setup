# Terminal preview gallery

[Documentation](README.md) · [Project overview](../README.md) · [Switch themes](customization.md#switch-the-prompt-theme)

## Quick-term

The default theme uses orange accents, a two-line prompt, directory and Git
context, command duration, and a clock. Completed commands use a compact
transient prompt in an interactive shell.

![Quick-term prompt with a pnpm script command reference](assets/quick-term.png)

[PNG](assets/quick-term.png) · [SVG](assets/quick-term.svg) · [Theme source](../config/oh-my-posh/quick-term.omp.json)

## iTerm2

The alternative uses blue and lime segments, a status indicator, and a rocket
prompt. Battery and Python environment information appear when available.

![Blue and lime iTerm2 prompt with the same pnpm script command reference](assets/iterm2.png)

[PNG](assets/iterm2.png) · [SVG](assets/iterm2.svg) · [Theme source](../config/oh-my-posh/iterm2.omp.json)

## Alt+X command picker

Search by shortcut, description, or full command. The preview contains the whole
definition. Enter inserts the selection for editing; it does not execute it.

![Actual fzf terminal capture listing Docker commands and previewing a full definition](assets/command-picker.png)

[PNG](assets/command-picker.png) · [SVG](assets/command-picker.svg) · [Usage](terminal.md)

## How these images are made

The theme previews render the repository's actual Oh My Posh configurations with
explicit [sample prompt data](assets/prompt.data.json): user `dev`, directory
`~/linux-setup`, branch `main`, and a fixed example clock. Their command-reference
output comes from running `devhelp 'pnpm run'` against the current source. They
are rendered terminal examples, not screenshots of a personal workstation.

The picker image captures fzf in an isolated Zsh terminal, then renders its
visible character cells and colors. Capture is cancelled before selection.
The window header and dark background belong to the image renderer, not to an
installed terminal application or desktop theme.

The PNGs include the rendered font and work without local font installation.
The SVGs keep editable text and may look different without the matching font.
Both formats are kept here for reuse in documentation or a future project
landing page. Retain the upstream theme attribution in [NOTICE.md](../NOTICE.md).

## Regenerate

Install this repository's tools, the `MesloLGM Nerd Font Mono` font, and
[Noto Emoji](https://github.com/google/fonts/tree/main/ofl/notoemoji) for the
alternative theme's rocket glyph first.
Then, from the repository root:

```sh
uv run --with cairosvg==2.9.1 --with pyte==0.8.2 scripts/render-previews.py
```

The renderer needs Linux PTY support, a system Cairo library, Zsh, fzf, and
Oh My Posh with `print --data` support. The checked-in images were rendered with
Oh My Posh 31.9.1. The Python packages are documentation-only dependencies;
normal installation does not install them.

The script writes three PNG/SVG pairs in `docs/assets/`. Inspect them after
changing a theme, command description, fzf layout, font, or rendering dependency.
It uses a temporary shell configuration and excludes private local commands.
