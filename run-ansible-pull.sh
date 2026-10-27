#!/usr/bin/env zsh
# Sync the setup repo and keep the playbook applied.
#
# Branches on a stamp file recording the last successful full re-apply:
#   stamp missing/stale -> full re-apply (ansible-pull without -o always runs
#                          the playbook), then refresh the stamp on success
#   stamp fresh         -> quiet sync (ansible-pull with -o only applies when
#                          the repo actually changed)
# This guarantees at least one full apply per day whenever the machine is
# available, whatever hour it happens to be awake.
SETUPDIR="${SETUPDIR:-${HOME}/.setup}"
STAMP="${FULL_APPLY_STAMP:-${HOME}/.ansible.last-full-apply}"
MAX_AGE_HOURS="${FULL_APPLY_MAX_AGE_HOURS:-24}"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Collections main.yml needs. ansible-pull clones the repo itself, so fetch the
# requirement list from the published branch instead of assuming a checkout.
# Failure here is not fatal: the playbook may still work with whatever the
# distribution's ansible package bundled.
REQUIREMENTS=$(mktemp)
if ! which ansible-galaxy >/dev/null 2>&1; then
  log "WARNING: ansible-galaxy not found; skipping collection install"
elif curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/requirements.yml -o "$REQUIREMENTS"; then
  ansible-galaxy collection install -r "$REQUIREMENTS" \
    || log "WARNING: collection install failed; continuing with installed collections"
else
  log "WARNING: could not fetch requirements.yml; continuing with installed collections"
fi
rm -f "$REQUIREMENTS"

AP=$(which ansible-pull)
NOW=$(date +%s)
LAST=$(cat "$STAMP" 2>/dev/null || echo 0)
[[ "$LAST" == <-> ]] || LAST=0

if (( NOW - LAST > MAX_AGE_HOURS * 3600 )); then
  log "Full re-apply (stamp missing or older than ${MAX_AGE_HOURS}h)"
  if $AP --clean -U https://github.com/StreamOfRon/setup.git -i localhost, -l localhost -c local -d "$SETUPDIR" main.yml; then
    [[ "$STAMP" == */* ]] && mkdir -p "${STAMP%/*}"
    date +%s > "$STAMP"
  else
    log "ERROR: full re-apply failed; no stamp written, will retry next run"
  fi
else
  log "Quiet sync (stamp fresh)"
  $AP --clean -U https://github.com/StreamOfRon/setup.git -i localhost, -l localhost -c local -d "$SETUPDIR" -o main.yml
fi
