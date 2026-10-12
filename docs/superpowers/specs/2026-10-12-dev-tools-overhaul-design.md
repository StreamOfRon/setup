# Dev Tools Management Overhaul — Design Spec

Date: 2026-10-12
Status: approved in conversation, pending final spec review

## Purpose

Overhaul how this playbook manages development tools:

1. Separate GUI tools from CLI tools (dev groups only).
2. Install opencode and omp via their recommended shell scripts.
3. Bring the user's opencode/omp/herdr/worktrunk configuration under ansible management where possible.
4. Create a dedicated `ai-dev-tools` group for AI tooling.
5. Set up herdr + worktrunk per `~/herdr-worktrunk-reference.md`.
6. Guarantee periodic (≥ daily) playbook re-application, guarded by a clean repo tree.
7. Install the user's favorite agent skills with the AI group.

## Background / current state

- Playbook: `main.yml` + per-group toggles in `default.config.yml` (three-valued: `true` install, `false` remove, `ignore` skip). Per-machine overrides in untracked `~/.setup-options`.
- Package groups import `tasks/homebrew_packages.yml` with `enabled` / `groupname` / `formulae` / `casks` / `taps` vars. The `dev` group currently mixes CLI formulae and GUI casks/fonts.
- opencode lives at `~/.opencode/bin/opencode` (official installer), omp v18.x at `~/.local/bin/omp` (`curl -fsSL https://omp.sh/install | sh`). herdr, worktrunk, fzf are brew formulae; herdr keybindings and the worktrunk plugin were applied manually.
- Config files verified **secret-free** (2026-10-12): `~/.config/opencode/opencode.json` (`"apiKey": "-"` placeholder), `~/.config/opencode/cli.json`, `~/.omp/agent/config.yml` (`tokenRate` is a UI toggle), `~/.omp/agent/models.yml`. All may be committed to the public repo.
- `ansible-pull` skips running the playbook when the checkout is unchanged ("Repository has not changed, quitting"), so nothing re-applies without a pushed commit — hence goal 6.
- Skills are installed globally by the `skills` CLI into `~/.agents/skills/`.

## Non-goals

- No restructuring of non-dev package groups (sync, misc, entertainment, media, kube, aws, other).
- No management of runtime state: opencode `service.json` / `tui.jsonc`, omp `*.db` files, herdr logs/sockets/sessions.
- No removal of skills not in the managed list (skills management is additive).
- No changes to `~/.zshrc.local` or other user-local unmanaged files.

## Design

### 1. Group restructure (dev tools only)

`default.config.yml`:

| Old | New |
|---|---|
| `install_dev_tools` + `devtools_formulae` + `devtools_casks` | `install_dev_cli_tools` + `dev_cli_formulae` (ansible-lint, gh, git, pre-commit, yq) |
| — | `install_dev_gui_tools` + `dev_gui_casks` (font-fira-code, font-fira-code-nerd-font, visual-studio-code) |
| — | `install_ai_dev_tools: false` + `ai_dev_tools_formulae` (herdr, worktrunk, fzf, node) + `ai_dev_tools_casks: []` |

- `node` is included so `npx skills` works on fresh machines.
- `install_ai_dev_tools` defaults to `false` in the repo; enabled per-machine via `~/.setup-options`.
- Old vars are removed (single-consumer personal repo; no backward-compat shims).

### 2. `ai-dev-tools` group

Wired in `main.yml` after "Manage dev gui tools", same block/rescue pattern as the other groups:

```yaml
- name: Manage ai dev tools
  block:
    - ansible.builtin.import_tasks: tasks/ai-dev-tools.yml
      vars:
        enabled: "{{ install_ai_dev_tools | default(false) }}"
        groupname: ai-dev-tools
        formulae: "{{ ai_dev_tools_formulae }}"
        casks: "{{ ai_dev_tools_casks }}"
  rescue:
    - name: Warn about ai dev tools install failure
      ansible.builtin.debug:
        msg: "Failed to manage ai dev tools, continuing: {{ ansible_failed_result | default('unknown error') }}"
```

`main.yml` `when:` clauses use the truthy check (existing convention); task files guard against `"ignore"` with `enabled != "ignore"` / `install_ai_dev_tools != "ignore"`.

#### Task files

- `tasks/ai-dev-tools.yml` — orchestrator:
  1. Brew formulae via existing `tasks/homebrew_packages.yml` (`state: latest` when enabled keeps herdr ≥ 0.7.0, worktrunk ≥ 0.60).
  2. opencode installer (below).
  3. omp installer (below).
  4. `import_tasks: tasks/opencode.yml`
  5. `import_tasks: tasks/omp.yml`
  6. `import_tasks: tasks/herdr.yml`
  7. Skills installs (below).
- `tasks/opencode.yml`, `tasks/omp.yml`, `tasks/herdr.yml` — config management per tool.

All non-brew tasks carry `when: install_ai_dev_tools | default(false) != "ignore"`.

#### Installers (recommended shell scripts)

```yaml
- name: Install opencode via official script
  ansible.builtin.command: curl -fsSL https://opencode.ai/install | bash
  changed_when: false
  when: install_ai_dev_tools | default(false) != "ignore"

- name: Install omp via official script
  ansible.builtin.command: curl -fsSL https://omp.sh/install | sh
  changed_when: false
  when: install_ai_dev_tools | default(false) != "ignore"
```

(`command` with a pipe requires the shell form — implement as `ansible.builtin.shell` or an equivalent single-argument invocation; keep `changed_when: false`. Installers always re-fetch, so version drift is picked up on the next run.)

#### Config management

| Dest | Source | Method / notes |
|---|---|---|
| `~/.config/opencode/opencode.json` | `templates/opencode.json.j2` | full file, mode 0644. Content copied verbatim from the live file (plugins, commands, mcp servers, experimental policies). |
| `~/.config/opencode/cli.json` | `templates/opencode-cli.json.j2` | full file, mode 0644 (UI prefs + `"./herdr-opencode"` plugin ref). |
| `~/.omp/agent/config.yml` | `templates/omp-config.yml.j2` | full file, **mode 0600** (matches live perms). |
| `~/.omp/agent/models.yml` | `templates/omp-models.yml.j2` | full file, mode 0644. |
| `~/.config/worktrunk/config.toml` | `files/worktrunk-config.toml` | static copy; the path-template config from the reference doc (`worktree-path = "{{ repo_path }}/../.herdr/worktrees/{{ repo }}/{{ branch \| sanitize }}"`). |
| `~/.config/herdr/config.toml` | block content in task | **blockinfile append** of the three `[[keys.command]]` blocks (reference doc §5). Never overwrites — file holds user theme/toast/sound settings. |
| herdr worktrunk plugin | command | `herdr plugin install devashish2203/herdr-worktrunk --yes`, `changed_when: false` (re-run is a no-op reinstall). |

Templates must reproduce the live files byte-for-byte (modulo trailing newline) so the first run is a no-op and no drift is introduced; verify with `diff` after first run.

#### zshrc template (`templates/zshrc.j2`)

Gated additions (use `install_ai_dev_tools | default(false) == true` so the three-valued `"ignore"` correctly removes the lines):

- PATH: `export PATH="$HOME/.opencode/bin:$PATH"` with the other PATH exports near the top.
- Near the end, before `zshrc.local` sourcing (reference doc §3):

```sh
if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init zsh)"; fi
```

#### Skills (additive)

```yaml
- name: Install agent skills (StreamOfRon/agent-skills)
  ansible.builtin.command: npx -y skills add -g StreamOfRon/agent-skills
  changed_when: false
  when: install_ai_dev_tools | default(false) != "ignore"

- name: Install agent skills (crusty-old-engineer)
  ansible.builtin.command: npx -y skills add -g microsoft/amplifier-bundle-skills --skill crusty-old-engineer
  changed_when: false
  when: install_ai_dev_tools | default(false) != "ignore"
```

### 3. Periodic re-application

Keep the existing 15-minute ansible-pull cron and `@reboot` entry unchanged. Add a guaranteed daily full re-apply:

**New file `run-daily-apply.sh`** (repo root, executable):

```zsh
#!/usr/bin/env zsh
SETUPDIR="${HOME}/.setup"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "$SETUPDIR" || { log "ERROR: $SETUPDIR not found"; exit 1; }

# Guard: never touch a checkout with local uncommitted changes.
if [[ -n "$(git status --porcelain)" ]]; then
  log "SKIP: uncommitted local changes in $SETUPDIR"
  exit 0
fi

git fetch origin || { log "ERROR: git fetch failed"; exit 1; }
git reset --hard origin/HEAD || { log "ERROR: git reset failed"; exit 1; }

AP=$(which ansible-playbook)
$AP -i localhost, -c local main.yml
```

**New cron entry in `tasks/ansible-pull-cron.yml`**:

```yaml
- name: Ansible daily re-apply
  ansible.builtin.cron:
    name: ansible daily re-apply
    minute: "{{ daily_apply_minute | default('0') }}"
    hour: "{{ daily_apply_hour | default('3') }}"
    job: "{{ lookup('env', 'HOME') }}/.setup/run-daily-apply.sh >> {{ lookup('env', 'HOME') }}/.ansible.log 2>&1"
```

`daily_apply_hour` / `daily_apply_minute` are optional vars (defaults 03:00).

### 4. File change list

New:
- `tasks/ai-dev-tools.yml`, `tasks/opencode.yml`, `tasks/omp.yml`, `tasks/herdr.yml`
- `templates/opencode.json.j2`, `templates/opencode-cli.json.j2`, `templates/omp-config.yml.j2`, `templates/omp-models.yml.j2`
- `files/worktrunk-config.toml`
- `run-daily-apply.sh` (mode 0755)

Modified:
- `default.config.yml` — dev group split + ai vars (§1)
- `main.yml` — replace "Manage dev tools" block with dev-cli and dev-gui blocks; add ai-dev-tools block
- `templates/zshrc.j2` — gated PATH + wt shell-init lines
- `tasks/ansible-pull-cron.yml` — daily re-apply cron entry

## Rollout (this machine)

1. One-time cleanup: remove the three existing unmarked `[[keys.command]]` blocks from `~/.config/herdr/config.toml` (blockinfile would otherwise append duplicates; it re-adds them with its own markers on first run).
2. Update local `~/.setup-options`: replace `install_dev_tools: true` with `install_dev_cli_tools: true` and add `install_ai_dev_tools: true`.
3. Commit + push, then run the playbook locally via `run-playbook.sh`.

## Verification / acceptance criteria

1. Playbook runs cleanly; a second immediate run reports **zero changed tasks** (idempotency gate).
2. `diff` of all managed config files against pre-run copies shows no unintended drift.
3. `run-daily-apply.sh`: with a dirty tree → logs SKIP and exits 0 without touching git; with a clean tree → fetches, resets, runs the playbook.
4. `crontab -l` shows the existing quarter-hourly/reboot entries plus the new daily entry.
5. Sanity: `opencode --version`, `omp --version`, `wt --version` (≥ 0.60), `herdr plugin list` (worktrunk present), `ls ~/.agents/skills` includes `crusty-old-engineer`.

## Risks / notes

- Installer and skills tasks report no change (`changed_when: false`) by design; real version drift surfaces on the next scheduled run, not as a playbook "change".
- The repo is public — secret-free status of all committed config was verified at spec time (2026-10-12). If any managed config later gains secrets, move that value to a `~/.setup-options`-supplied var before committing.
- `git reset --hard origin/HEAD` in the daily script is safe only because of the preceding clean-tree guard; keep the guard first.
- opencode/omp write some runtime files alongside managed ones; only user-config files are managed, so no clobbering of state.
