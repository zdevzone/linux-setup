# Shared shortcuts. Companion helpers live in functions.zsh.
# Run devhelp or press Alt+X to discover commands and their descriptions.

# Navigation.

# Move up one directory.
alias ..='cd ..'
# Move up two directories.
alias ...='cd ../..'
# Move up three directories.
alias ....='cd ../../..'
# Move up four directories.
alias .....='cd ../../../..'
# Return to the previous directory.
alias -- -='cd -'
# Go to your home directory.
alias home='cd ~'
# Go to the Git repository root, or stay in the current directory.
alias croot='cd "$(git rev-parse --show-toplevel 2>/dev/null || print -r -- "$PWD")"'
# Clear the terminal.
alias c='clear'
# Clear the terminal (compatibility shortcut).
alias cls='clear'
# Restart Zsh to reload your configuration.
alias reload='exec zsh'
# Go to your development directory ($DEV_DIR).
alias cdev='cd "$DEV_DIR"'
# Go to the setup directory ($DEV_SETUP_DIR).
alias csetup='cd "$DEV_SETUP_DIR"'
# Go to the linux-setup checkout.
alias devsetup='cd "$LINUX_SETUP_DIR"'
# Go to the linux-setup checkout (alternate name).
alias linuxsetup='cd "$LINUX_SETUP_DIR"'

# Modern tools; aliases are available when their tools are installed.

# List all files with details, Git status, and directories first.
(( $+commands[eza] )) && alias ll='eza --long --all --group-directories-first --git'
# List all files with directories first.
(( $+commands[eza] )) && alias la='eza --all --group-directories-first'
# Show a directory tree two levels deep.
(( $+commands[eza] )) && alias lt='eza --tree --level=2 --group-directories-first'
# View files with bat syntax highlighting.
(( $+commands[bat] )) && alias ccat='bat'
# Open the lazygit interface.
(( $+commands[lazygit] )) && alias lg='lazygit'
# Start or control tmux.
(( $+commands[tmux] )) && alias t='tmux'

# Git.

# Show concise Git status and branch information.
alias gs='git status --short --branch'
# Show unstaged Git changes.
alias gd='git diff'
# Show staged Git changes.
alias gds='git diff --staged'
# Show a graph of the latest 20 commits.
alias gl='git log --oneline --graph --decorate -20'
# Stage paths for a Git commit.
alias ga='git add'
# Create a Git commit.
alias gc='git commit'
# Switch Git branches.
alias gsw='git switch'
# Create and switch to a new Git branch.
alias gswc='git switch -c'
# Fetch all Git remotes and prune stale remote branches.
alias gfetch='git fetch --all --prune'
# List Git worktrees.
alias gwt='git worktree list'
# List local and remote Git branches.
alias gbranches='git branch --all'
# Show the latest commit and its file statistics.
alias glast='git log -1 --stat'
# Show Git reference history with relative dates.
alias greflog='git reflog --date=relative'
# List paths with unresolved merge conflicts.
alias gconflicts='git diff --name-only --diff-filter=U'
# List Git remotes and their URLs.
alias gremote='git remote -v'
# Pull Git changes only when a fast-forward is possible.
alias gpull='git pull --ff-only'

# GitHub CLI; commands use the current repository by default.

# Open the current GitHub repository in a browser.
alias ghrepo='gh repo view --web'
# List pull requests.
alias ghprs='gh pr list'
# Inspect a pull request.
alias ghpr='gh pr view'
# Show pull request checks.
alias ghchecks='gh pr checks'
# List workflow runs.
alias ghruns='gh run list'
# Inspect a workflow run; add --log-failed to view failed job logs.
alias ghrun='gh run view'

# Project scripts and dependencies; named scripts must exist in package.json.

# Run pnpm with the project runtime and package-manager configuration.
alias pn='pnpm'
# Install project dependencies with pnpm.
alias pi='pnpm install'
# Install dependencies without changing the existing lockfile.
alias pif='pnpm install --frozen-lockfile'
# Run a named package.json script.
alias pr='pnpm run'
# Run the project dev script.
alias pd='pnpm run dev'
# Run the project build script.
alias pb='pnpm run build'
# Run the full project check script.
alias pcheck='pnpm run check'
# Run the full project test script.
alias pt='pnpm run test'
# Run the project format script.
alias pfmt='pnpm run format'
# Run the project start script.
alias pstart='pnpm run start'
# Run a locally installed package executable.
alias px='pnpm exec'
# Select a pnpm workspace package for a command.
alias pfilter='pnpm --filter'
# Add a project dependency.
alias pa='pnpm add'
# Add a development dependency.
alias pad='pnpm add --save-dev'
# List outdated project dependencies.
alias pout='pnpm outdated'
# Explain why a dependency is installed.
alias pwhy='pnpm why'

# Vite+; direct tools do not run project check/test wrappers.

# Install project dependencies through Vite+.
alias vpi='vp install'
# Run a named project task through Vite+.
alias vr='vp run'
# Run the direct Vite+ check tool.
alias vcheck='vp check'
# Format code with the direct Vite+ tool.
alias vfmt='vp fmt'
# Run tests once with the direct Vite+ tool.
alias vtest='vp test run'
# Watch tests with the direct Vite+ tool.
alias vwatch='vp test watch'

# Rust / Cargo.

# Build the Rust project.
alias cgb='cargo build'
# Check the Rust project without producing an executable.
alias cgc='cargo check'
# Run Rust tests.
alias cgt='cargo test'
# Run the Rust project; pass program arguments after --.
alias cgr='cargo run'
# Format Rust code.
alias cgf='cargo fmt'
# Run Clippy lint checks.
alias cgl='cargo clippy'
# Build an optimized Rust release.
alias cgrelease='cargo build --release'
# Check Rust formatting without changing files.
alias cgfcheck='cargo fmt --check'
# Generate and open Rust documentation.
alias cgdoc='cargo doc --open'

# Laravel; run from the application root, or use Sail for container PHP.

# Run an Artisan command using host PHP.
alias art='php artisan'
# Start the Laravel development server using host PHP.
alias arts='php artisan serve'
# Run Laravel tests using host PHP.
alias artt='php artisan test'
# List Laravel routes using host PHP.
alias artroutes='php artisan route:list'
# Run Laravel Sail; use sail artisan or sail test for container PHP.
alias sail='./vendor/bin/sail'

# Docker; commands use the active Docker context and current Compose project.

# List running Docker containers.
alias dps='docker ps'
# List all Docker containers.
alias dpsa='docker ps --all'
# Follow a container log, starting with the last 100 lines.
alias dlogs='docker logs --follow --tail=100'
# Show live Docker container resource usage.
alias dstats='docker stats'
# Show live Docker container resource usage (existing shortcut).
alias dcstats="docker stats"
# Show Docker disk usage.
alias ddf='docker system df'
# Show the active Docker context.
alias dctx='docker context show'
# List available Docker contexts.
alias dctxs='docker context ls'
# Change the active Docker context.
alias duse='docker context use'
# Run a Compose command; supports -f FILE before the subcommand.
alias dco='docker compose'
# Start Compose services in the background.
alias dcup="docker compose up -d"
# Stop Compose services without removing containers or volumes.
alias dcstop='docker compose stop'
# Stop and remove Compose containers and networks.
alias dcdown="docker compose down"
# Stop Compose and DELETE its volumes, containers, and networks.
alias dcdown-v="docker compose down -v"
# Build images and start Compose services in the background.
alias dcpack="docker compose up -d --build"
# Restart Compose services.
alias dcrestart="docker compose restart"
# Show Compose service status.
alias dcps='docker compose ps'
# Follow Compose logs, starting with the last 100 lines.
alias dclog='docker compose logs --follow --tail=100'
# Follow Compose logs with the existing default log history.
alias dclogs="docker compose logs -f"
# Execute a command in a running Compose service.
alias dcex='docker compose exec'
# Build Compose service images.
alias dcbuild='docker compose build'
# Validate Compose configuration without printing expanded values.
alias dccheck='docker compose config --quiet'
# List Compose service names.
alias dcservices='docker compose config --services'
# DELETE Compose volumes and unused Docker resources, then rebuild and start.
alias docker-nuclear="echo '⚠️ Starting full environment wipe...' && docker compose down -v && docker system prune -a --volumes -f && docker compose build --no-cache && docker compose up -d && echo '✅ System fully rebuilt from scratch!'"

# Kubernetes; install kubectl separately and select context/namespace explicitly.

# Run kubectl with the selected context and namespace.
alias k='kubectl'
# Show the active Kubernetes context.
alias kctx='kubectl config current-context'
# List available Kubernetes contexts.
alias kcontexts='kubectl config get-contexts'
# Change the active Kubernetes context.
alias kuse='kubectl config use-context'
# List Kubernetes namespaces.
alias kns='kubectl get namespaces'
# List Kubernetes nodes with additional details.
alias knodes='kubectl get nodes -o wide'
# List pods with additional details; add -n NAMESPACE as needed.
alias kpods='kubectl get pods -o wide'
# List Kubernetes services.
alias ksvc='kubectl get services'
# List Kubernetes deployments.
alias kdeploy='kubectl get deployments'
# Describe a Kubernetes resource.
alias kdesc='kubectl describe'
# Follow pod logs, starting with the last 100 lines.
alias klogs='kubectl logs --follow --tail=100'
# List Kubernetes events by creation time.
alias kevents='kubectl get events --sort-by=.metadata.creationTimestamp'

# Terraform; install separately and run from the infrastructure directory.

# Run Terraform.
alias tf='terraform'
# Initialize Terraform, including any configured remote backend.
alias tfinit='terraform init'
# Preview Terraform changes; may contact provider APIs.
alias tfplan='terraform plan'
# Validate the Terraform configuration.
alias tfvalidate='terraform validate'
# Format Terraform files recursively.
alias tffmt='terraform fmt -recursive'
# Check Terraform formatting recursively without changing files.
alias tffmtcheck='terraform fmt -check -recursive'

# Host and network diagnostics; journal commands require systemd.

# List failed systemd units.
alias svcfailed='systemctl --failed --no-pager'
# List running systemd services.
alias svcs='systemctl list-units --type=service --state=running --no-pager'
# Show the last 100 error messages from the current boot journal.
alias jerrors='journalctl -b -p err -n 100 --no-pager'
# Show filesystem space and types in human-readable units.
alias disks='df -hT'
# Show memory and swap usage.
alias mem='free -h'
# Show disk usage one directory level deep.
alias dus='du -h --max-depth=1'
# Show listening TCP/UDP sockets and their processes.
alias listens='ss -lntup'
# Show a brief list of network addresses.
alias ipbrief='ip -brief address'

# Local development and PostgreSQL; configure service profiles in ~/.pg_service.conf.

# List TCP listeners, optionally restricted to specified ports.
alias lip='dev-ports list'
# List TCP listeners (alternate name for lip).
alias ports='dev-ports list'
# Confirm and stop listeners on explicitly specified ports.
alias kip='dev-ports kill'
# Open the PostgreSQL database/schema manager.
alias db='dev-db'
# Open the PostgreSQL database/schema manager (alternate name).
alias dbm='dev-db'
# Inspect project dependencies, Git, runtimes, and Docker.
alias dcheck='dev-check'
# Check or run a project browser-testing environment.
alias dbr='dev-browser'
# Connect to the private PostgreSQL service profile named local.
alias pg-local='psql -X "service=local"'
# Connect to the private PostgreSQL service profile named remote.
alias pg-remote='psql -X "service=remote"'
# Connect to the private PostgreSQL service profile named bingo.
alias pg-bingo='psql -X "service=bingo"'
# Print each PATH directory on a separate line.
alias pathlist='print -rl -- $path'

# JSON and file searching.

# Pretty-print JSON from a file or standard input.
alias jpretty='jq .'
# Print compact JSON from a file or standard input.
alias jcompact='jq -c .'
# List files including hidden paths, excluding .git.
alias rgfiles='rg --files --hidden --glob !.git'

# AI agents; each CLI retains its configured model and permissions.

# Start Codex.
alias cx='codex'
# Choose a Codex session to resume.
alias cxr='codex resume'
# Continue the latest Codex session.
alias cxc='codex resume --last'
# Run Codex in exec mode.
alias cxe='codex exec'
# Start Claude Code.
alias cld='claude'
# Choose a Claude Code session to resume.
alias cldr='claude --resume'
# Continue the latest Claude Code session.
alias cldc='claude --continue'
