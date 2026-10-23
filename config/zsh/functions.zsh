# Make a directory and enter it.
mkcd() {
  if (( $# != 1 )); then print -u2 'Usage: mkcd DIRECTORY'; return 2; fi
  mkdir -p -- "$1" && builtin cd -- "$1"
}

# Go up N directory levels.
up() {
  local levels="${1:-1}" destination='.'
  if (( $# > 1 )) || [[ "$levels" != <1-100> ]]; then
    print -u2 'Usage: up [LEVELS from 1 to 100]'; return 2
  fi
  repeat "$levels" destination+='/..'
  builtin cd -- "$destination"
}

# Serve a directory on localhost.
serve() {
  local port="${1:-8000}" directory="${2:-.}"
  if (( $# > 2 )) || [[ "$port" != <1-65535> ]]; then
    print -u2 'Usage: serve [PORT] [DIRECTORY]'; return 2
  fi
  command python3 -m http.server "$port" --bind 127.0.0.1 --directory "$directory"
}

# File manager that leaves the shell in its final directory.
y() {
  local tmp cwd
  tmp="$(mktemp "${TMPDIR:-/tmp}/yazi-cwd.XXXXXX")" || return
  command yazi "$@" --cwd-file="$tmp"
  local result=$?
  if [[ -f "$tmp" ]]; then
    cwd="$(<"$tmp")"
    [[ -n "$cwd" && "$cwd" != "$PWD" && -d "$cwd" ]] && builtin cd -- "$cwd"
    command rm -f -- "$tmp"
  fi
  return $result
}

# Open files in your editor with NUL-delimited selection for unusual filenames.
fe() {
  local -a selected editor
  selected=("${(@0)$(fd --type f --hidden --exclude .git --print0 | fzf --read0 --print0 --multi)}")
  selected=("${(@)selected:#}")
  (( ${#selected} )) || return 0
  editor=("${(@Q)${(z)EDITOR}}")
  command "${editor[@]}" -- "${selected[@]}"
}

# Find and enter a directory, including hidden project folders.
cdf() {
  local selected
  selected="$(fd --type d --hidden --exclude .git --print0 | fzf --read0 --print0)" || return
  selected="${selected%$'\0'}"
  [[ -n "$selected" ]] && builtin cd -- "$selected"
}

# Search project file contents, keeping rg's arguments and exit status.
search() { command rg --line-number --smart-case "$@"; }

# Give project workspaces a useful tmux session name.
work() {
  local project="${1:-$PWD}"
  command dev-session "$project"
}
