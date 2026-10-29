# Keep the live definitions separate from descriptions read from source comments.
_dev_commands_snapshot() {
  emulate -L zsh
  zmodload zsh/parameter || return
  local name
  for name in ${(ok)aliases}; do
    builtin printf '%s\0%s\0%s\0' alias "$name" "${aliases[$name]}"
  done
  for name in ${(ok)functions}; do
    [[ "$name" == _* ]] && continue
    builtin printf '%s\0%s\0%s\0' function "$name" "${functions[$name]}"
  done
}

_dev_commands_list() {
  emulate -L zsh
  setopt pipefail
  _dev_commands_snapshot | command python3 "$LINUX_SETUP_DIR/scripts/command_catalog.py" --list -- "$*"
}

_dev_commands_select() {
  emulate -L zsh
  setopt pipefail
  if (( ! $+commands[fzf] )); then
    print -u2 'Command picker requires fzf. Run ./install.sh from your linux-setup checkout.'
    return 2
  fi
  _dev_commands_snapshot | command python3 "$LINUX_SETUP_DIR/scripts/command_catalog.py" --pick -- "$*"
}

# Search custom aliases/functions and insert a command for editing without running it.
devcommands() {
  emulate -L zsh
  local selected result
  selected="$(_dev_commands_select "$@")"
  result=$?
  (( result == 1 )) && return 0
  (( result == 0 )) || return $result
  if [[ -o interactive ]]; then
    print -rz -- "$selected"
  else
    print -r -- "$selected"
  fi
}

_dev_commands_widget() {
  emulate -L zsh
  local selected result
  selected="$(_dev_commands_select)"
  result=$?
  if (( result == 0 )); then
    BUFFER="$selected"
    CURSOR=${#BUFFER}
  fi
  zle reset-prompt
  (( result == 1 )) && return 0
  return $result
}

if [[ -o interactive ]]; then
  zle -N dev-commands _dev_commands_widget
  # Bind both cases, including vi modes selected by a private zshrc later on.
  for _dev_command_keymap in emacs viins vicmd; do
    bindkey -M "$_dev_command_keymap" '^[x' dev-commands
    bindkey -M "$_dev_command_keymap" '^[X' dev-commands
  done
  unset _dev_command_keymap
fi
