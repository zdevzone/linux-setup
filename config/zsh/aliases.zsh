# Navigation
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'
alias -- -='cd -'
alias home='cd ~'
alias croot='cd "$(git rev-parse --show-toplevel 2>/dev/null || print -r -- "$PWD")"'
alias c='clear'
alias cls='clear'
alias reload='exec zsh'
alias cdev='cd "$DEV_DIR"'
alias csetup='cd "$DEV_SETUP_DIR"'
alias devsetup='cd "$LINUX_SETUP_DIR"'
alias linuxsetup='cd "$LINUX_SETUP_DIR"'

# Modern tools get explicit shortcuts; standard commands remain available.
if (( $+commands[eza] )); then
  alias ll='eza --long --all --group-directories-first --git'
  alias la='eza --all --group-directories-first'
  alias lt='eza --tree --level=2 --group-directories-first'
fi
(( $+commands[bat] )) && alias ccat='bat'
(( $+commands[lazygit] )) && alias lg='lazygit'
(( $+commands[tmux] )) && alias t='tmux'

# Git shortcuts avoid destructive operations.
alias gs='git status --short --branch'
alias gd='git diff'
alias gds='git diff --staged'
alias gl='git log --oneline --graph --decorate -20'
alias ga='git add'
alias gc='git commit'
alias gsw='git switch'
alias gfetch='git fetch --all --prune'

# Local development helpers.
alias lip='dev-ports list'
alias ports='dev-ports list'
alias kip='dev-ports kill'
alias db='dev-db'
alias dbm='dev-db'
alias pathlist='print -rl -- $path'
