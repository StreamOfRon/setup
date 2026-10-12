#!/usr/bin/env zsh
# Daily full re-apply of the setup playbook from the ansible-pull checkout.
# Skips when the checkout has local uncommitted changes, so in-progress
# edits are never clobbered by an automatic run.
SETUPDIR="${SETUPDIR:-${HOME}/.setup}"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "$SETUPDIR" || { log "ERROR: $SETUPDIR not found"; exit 1; }

# Guard: never touch a checkout with local uncommitted changes.
if [[ -n "$(git status --porcelain)" ]]; then
  log "SKIP: uncommitted local changes in $SETUPDIR"
  exit 0
fi

git fetch origin || { log "ERROR: git fetch failed"; exit 1; }
# origin/HEAD is not always set in fresh checkouts; fall back to main.
REMOTE_HEAD=$(git symbolic-ref --quiet refs/remotes/origin/HEAD || echo refs/remotes/origin/main)
git reset --hard "${REMOTE_HEAD#refs/remotes/}" || { log "ERROR: git reset failed"; exit 1; }

AP=$(which ansible-playbook)
$AP -i localhost, -c local main.yml
