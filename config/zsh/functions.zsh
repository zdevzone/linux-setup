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

# DELETE a named Docker volume and restart its Compose service; dcdrop-vol SERVICE VOLUME.
dcdrop-vol() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "❌ Usage: dcdrop-vol <service_name> <volume_name>"
        return 1
    fi
    echo "Stopping service $1 and destroying volume $2..."
    docker compose stop "$1"
    docker compose rm -f "$1"
    docker volume rm "$2"
    docker compose up -d "$1"
    echo "✅ Service $1 reset with a fresh volume!"
}

# Rebuild and restart one Compose service without its dependencies; dcrefresh SERVICE.
dcrefresh() {
    if [ -z "$1" ]; then
        echo "❌ Usage: dcrefresh <service_name>"
        return 1
    fi
    docker compose up -d --no-deps --build "$1"
}

# Open a container shell, trying bash then sh; dcinto CONTAINER.
dcinto() {
    if [ -z "$1" ]; then
        echo "❌ Usage: dcinto <container_name>"
        return 1
    fi
    docker exec -it "$1" bash 2>/dev/null || docker exec -it "$1" sh
}

# Show the reference for the existing Docker reset and Compose helpers.
dc() {
    echo -e "\033[1;36m========================================================="
    echo -e "🔮 DEVOPS & DOCKER COMMAND MEMORY ASSISTANT"
    echo -e "=========================================================\033[0m"
    echo -e "\033[1;31m🚨 THE NUCLEAR WIPE:\033[0m"
    echo -e "  \033[33mdocker-nuclear\033[0m      - Wipes everything, cleans cache, rebuilds, and restarts fresh."
    echo ""
    echo -e "\033[1;34m📦 DOCKER COMPOSE SHORTCUTS:\033[0m"
    echo -e "  \033[32mdcup\033[0m                - Spin up the stack in the background (detached)."
    echo -e "  \033[32mdcdown\033[0m              - Stop and remove containers and networks."
    echo -e "  \033[32mdcdown-v\033[0m            - Stop containers and completely \033[4;31mDESTROY\033[0m data volumes."
    echo -e "  \033[32mdcpack\033[0m              - Rebuild images and boot up the stack."
    echo -e "  \033[32mdcrestart\033[0m           - Fast restart for all stack containers."
    echo -e "  \033[32mdclogs\033[0m              - Follow logs in real-time."
    echo -e "  \033[32mdcstats\033[0m             - Show live RAM/CPU performance graphs."
    echo ""
    echo -e "\033[1;35m🛠️ DYNAMIC SMART FUNCTIONS:\033[0m"
    echo -e "  \033[32mdcinto <name>\033[0m       - Jump straight inside a container terminal (tries bash, then sh)."
    echo -e "  \033[32mdcrefresh <svc>\033[0m     - Hot-rebuild and restart just ONE service silently."
    echo -e "  \033[32mdcdrop-vol <s|v>\033[0m    - Kill one specific database service, drop its data, and start it clean."
    echo -e "\033[1;36m=========================================================\033[0m"
}

# Show package scripts without executing them; accepts a different manifest.
pscripts() {
  if (( $# > 1 )); then
    print -u2 'Usage: pscripts [PACKAGE_JSON]'; return 2
  fi
  command jq '.scripts // {}' -- "${1:-package.json}"
}

# Search commit messages for literal text across all locally known refs.
gfind() {
  if (( $# == 0 )); then
    print -u2 'Usage: gfind TEXT'; return 2
  fi
  command git log --all --oneline --fixed-strings "--grep=$*"
}

# Open a shell in an existing container; sh works on many minimal images.
# Images without a shell (for example distroless) cannot use these helpers.
dsh() {
  if (( $# < 1 || $# > 2 )) || [[ -z "$1" || "$1" == -* ]]; then
    print -u2 'Usage: dsh CONTAINER [SHELL, default sh]'; return 2
  fi
  command docker exec -it "$1" "${2:-sh}"
}

# Open a shell in a Compose service using this directory's project and active Docker context.
dcsh() {
  if (( $# < 1 || $# > 2 )) || [[ -z "$1" || "$1" == -* ]]; then
    print -u2 'Usage: dcsh SERVICE [SHELL, default sh]'; return 2
  fi
  command docker compose exec "$1" "${2:-sh}"
}

# Follow a system service's journal, starting with the last N lines.
# For a user service use: journalctl --user -u UNIT -n 100 -f
junit() {
  if (( $# < 1 || $# > 2 )) || [[ -z "$1" || "${2:-100}" != <1-10000> ]]; then
    print -u2 'Usage: junit UNIT [LINES from 1 to 10000]'; return 2
  fi
  command journalctl --unit "$1" --lines "${2:-100}" --follow
}

# Perform one HTTP GET; discard the body and print status/timing metrics.
# Redirects are reported, not followed. HTTP 4xx/5xx return a nonzero status.
httpcheck() {
  if (( $# != 1 )) || [[ "$1" != http://* && "$1" != https://* ]]; then
    print -u2 'Usage: httpcheck http[s]://HOST/PATH'; return 2
  fi
  command curl --globoff --fail --silent --show-error \
    --connect-timeout 10 --max-time 30 --output /dev/null \
    --write-out 'HTTP %{http_code}\nDNS %{time_namelookup}s | TCP %{time_connect}s | TLS %{time_appconnect}s\nFirst byte %{time_starttransfer}s | Total %{time_total}s\n' \
    --url "$1"
}

# Foreground SSH tunnel, bound only to local loopback. Ctrl-C closes it.
# Use an SSH config host alias to retain configured identities/proxies/options.
# Remote host is resolved from the SSH server; bracket IPv6 addresses.
# Example: sshtunnel staging 15432 5432 127.0.0.1
sshtunnel() {
  if (( $# < 3 || $# > 4 )) || [[ -z "$1" || "$1" == -* ||
    "$2" != <1-65535> || "$3" != <1-65535> || ( $# == 4 && -z "$4" ) ]]; then
    print -u2 'Usage: sshtunnel SSH_HOST LOCAL_PORT REMOTE_PORT [REMOTE_HOST, default 127.0.0.1]'
    return 2
  fi
  command ssh -N -T \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "127.0.0.1:$2:${4:-127.0.0.1}:$3" "$1"
}

# Connect to any private ~/.pg_service.conf profile, with optional psql flags.
# Profile names here allow letters, numbers, underscores, dots, and hyphens.
# Example: pgconnect staging -c '\conninfo'
pgconnect() {
  if (( $# == 0 )) || [[ -z "$1" || "$1" == *[^[:alnum:]_.-]* ]]; then
    print -u2 'Usage: pgconnect SERVICE [PSQL_ARGUMENTS...]'; return 2
  fi
  local db_service="$1"
  shift
  command psql -X --dbname="service=$db_service" "$@"
}

# List all custom commands with their descriptions and full definitions.
devhelp() {
  _dev_commands_list "$@"
}
