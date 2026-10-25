# Package Manager Precedence — Design Spec

Date: 2026-10-25
Status: proposed, pending approval

## Purpose

On Linux machines that have both Homebrew (Linuxbrew) and apt, the playbook
currently treats the machine as apt-only. Ansible reports
`ansible_facts.pkg_mgr == "apt"` even when brew is installed, so every
package group runs its apt path and skips its Homebrew path. Homebrew
packages are generally newer, and the user wants brew to win whenever it is
available, with apt used only for packages brew cannot supply.

Desired precedence for a package group:

1. Homebrew formula (when Homebrew is available and the package has one)
2. apt (when apt is available and the package has no Homebrew formula)
3. Homebrew cask (macOS only; skipped entirely on non-macOS)

## Background / current state

- `main.yml` dispatches each package group on
  `ansible_facts.pkg_mgr == "homebrew"` or `== "apt"`. On Linux+brew only
  the apt branch runs.
- Group configuration keeps parallel lists: `*_formulae`, `*_casks`, and
  `*_apt_packages`. They are not strict equivalents:
  - `kube_formulae` contains `kubernetes-cli`; `kube_apt_packages` contains
    `kubectl`.
  - `ai_dev_tools_formulae` contains `node`; `ai_dev_tools_apt_packages`
    contains `nodejs` and `npm`.
  - `sync_casks`/`media_casks`/`misc_casks` are macOS GUI apps with apt
    equivalents in `*_apt_packages`.
- Casks are not installable on Linux, so they must never run there.
- `git.yml` and `krew.yml` also branch on `pkg_mgr`; `krew.yml` falls back
  to a manual install whenever it does not see Homebrew.
- The ansible-pull cron `PATH` does not include
  `/home/linuxbrew/.linuxbrew/bin`, so even a brew-aware playbook would miss
  brew during unattended runs.
- `community.general.homebrew` and `homebrew_tap` already default to
  searching `/home/linuxbrew/.linuxbrew/bin`; `homebrew_cask` does not, but
  casks will be macOS-only.

## Goals

- Detect Homebrew independently of `ansible_facts.pkg_mgr`.
- Prefer Homebrew formulae on any machine where brew is available.
- Promote apt-listed packages to Homebrew automatically when a same-named
  formula exists, so groups with empty `*_formulae` lists still get brew
  versions.
- Cover the few renamed equivalents with a small explicit mapping.
- Use apt only for packages not covered by Homebrew.
- Never run casks on non-macOS.
- Keep the three-valued group semantics (`true` install, `false` remove,
  `ignore` skip) and unattended sudo gating.
- Make the preference overridable with `prefer_homebrew: true|false`.

## Non-goals

- No changes to official-installer paths: `uv`, `opencode`, `omp`, `herdr`,
  `rustup`, and `bootstrap.sh`.
- No per-OS package-list split (no `*_linux_formulae`).
- No removal of apt packages that were installed outside the playbook.
- No automatic mapping of every possible apt/brew rename; only the
  configured equivalents.
- No TUI list editor for the equivalent map.

## Approaches considered

### A. Prefer brew, auto-promote apt entries, apt fills gaps (chosen)

Detect brew; install `*_formulae` plus apt entries that have a same-named
brew formula; skip apt for anything already covered by brew (same name,
installed formula, or explicit alias); run casks only on macOS.

- Pros: delivers brew freshness without editing every group's formula list;
  apt remains the safety net for Linux-only packages; one alias map.
- Cons: promotion is implicit, and one extra `brew formulae` query.

### B. Same precedence, explicit lists only

Brew installs only `*_formulae`; apt handles the rest, with the alias map.

- Pros: fully predictable; no implicit manager changes.
- Cons: groups with empty `*_formulae` (sync, media, misc) keep using apt;
  populating them can install both a CLI formula and a macOS cask.

### C. Literal formulae → apt → casks with no coverage logic

Run each list through its native manager in order.

- Rejected: installs both sides (`kubectx` twice, `node` plus `nodejs`),
  still runs apt for everything, and so does not actually prefer brew.

## Design

### 1. Homebrew detection and preference (`tasks/package_manager.yml`)

New pre-task file, imported after `~/.setup-options` is loaded and before
package lists are gathered:

- Locate brew with `which brew`, searching the normal PATH plus
  `~/.linuxbrew/bin`, `/home/linuxbrew/.linuxbrew/bin`, `/opt/homebrew/bin`,
  and `/usr/local/bin`. `failed_when: false`.
- Set facts:
  - `brew_bin` — resolved absolute path (empty when absent)
  - `brew_bin_dir` — `dirname` of `brew_bin`
  - `brew_available` — brew found AND
    (`prefer_homebrew` is true OR `ansible_facts.pkg_mgr == "homebrew"`).
    The second clause keeps macOS working when the preference is off, since
    apt is not an alternative there.
- When brew is unavailable, initialise `installed_brew_formulae`,
  `installed_brew_casks`, `brew_taps`, and `available_brew_formulae` to
  `{stdout_lines: []}` so later expressions never touch an undefined var.

`default.config.yml` gains:

```yaml
prefer_homebrew: true
```

### 2. Package-list snapshot (`tasks/homebrew_list.yml`)

- Gate the file on `brew_available` in `main.yml` instead of
  `pkg_mgr == "homebrew"`.
- Invoke `{{ brew_bin }}` explicitly so cron runs do not depend on PATH.
- Add `available_brew_formulae` via `{{ brew_bin }} formulae`
  (`changed_when: false`, `failed_when: false`), used for auto-promotion.

### 3. Effective list resolution (`tasks/package_resolve.yml`)

`tasks/package_resolve.yml` computes the effective lists only, so it can be
exercised by a side-effect-free test playbook. `tasks/package_group.yml` is
the dispatcher: it imports the resolver once per group with
`enabled`, `groupname`, `formulae`, `casks`, `apt_packages`, and optional
`taps`, then imports the Homebrew and apt task files.

The resolver computes (via `set_fact`, one step each):

```text
_group_formulae   = unique(formulae + (apt_packages ∩ available_brew_formulae))
_group_brew_present = unique(_group_formulae + installed_brew_formulae)
_group_apt_covered = keys of brew_apt_equivalents whose value ∈ _group_brew_present
_group_apt_packages =
    enabled == true  -> apt_packages - _group_brew_present - _group_apt_covered
    enabled != true  -> apt_packages          # removal keeps the full list
```

`tasks/package_group.yml` then imports, in order:

1. `tasks/homebrew_packages.yml` when `brew_available`, passing
   `formulae: _group_formulae`, `casks`, `taps`, and the unchanged
   `enabled`/`groupname`.
2. `tasks/apt_packages.yml` when `pkg_mgr == "apt"`, passing
   `packages: _group_apt_packages`.

`brew_apt_equivalents` lives in `default.config.yml`:

```yaml
brew_apt_equivalents:
  nodejs: node
  npm: node
  kubectl: kubernetes-cli
```

The map is keyed by apt name and valued by brew formula. It covers the
cases where the names differ; same-name packages are covered by the
intersection with `available_brew_formulae` or the installed formula list.

Removal (`enabled: false`) keeps the full apt list so packages installed by
either manager are removed. Auto-promoted names are also removed via
Homebrew, which is a no-op when brew never installed them.

### 4. Homebrew task file (`tasks/homebrew_packages.yml`)

- Add `path: "{{ brew_bin_dir }}"` to the tap, formula, and cask modules so
  non-standard brew roots work.
- Gate the cask task on `ansible_facts.system == "Darwin"` as well as its
  existing conditions. This is the "skip casks on non-mac" decision.
- Keep formulae before casks. On Linux apt runs after this file; on macOS
  apt never runs, so the effective order is still formulae → apt (n/a) →
  casks.

### 5. Group wiring (`main.yml`, `tasks/ai-dev-tools.yml`)

Replace each pair of Homebrew/apt imports with one
`tasks/package_group.yml` import. Group blocks keep their existing
`rescue` warnings and `install_*` defaults. The kube group also passes
`taps`. `tasks/ai-dev-tools.yml` uses the same dispatcher for its package
lists before its installer/config tasks.

`tasks/krew.yml` changes from `pkg_mgr == "homebrew"` to `brew_available`
for the brew formula, and from `!= "homebrew"` to `not brew_available` for
the apt prerequisite and manual install.

`tasks/git.yml`:

- Install via Homebrew when `brew_available` and git is absent from the
  brew list.
- Install via apt only when `pkg_mgr == "apt"`, `not brew_available`, a
  become password is available, and git is absent from dpkg.

### 6. Package-manager updates (`main.yml`)

- Homebrew update task runs when `brew_available`, with
  `path: "{{ brew_bin_dir }}"`.
- apt cache update is unchanged (needed for fallback packages on Linux+brew).

### 7. Cron PATH (`tasks/ansible-pull-cron.yml`)

Add `/home/linuxbrew/.linuxbrew/bin` and
`/home/linuxbrew/.linuxbrew/sbin` to the cron `PATH` so unattended runs
detect brew. Keep the existing macOS entries.

### 8. Configuration UI

Add `prefer_homebrew` as a boolean under "System & shell" in
`setup-config-menu.json` (label "Prefer Homebrew over apt"), so it can be
changed per machine. Update the menu item count test from 7 to 8.

### 9. Documentation

Update `AGENTS.md` with the precedence and alias-map conventions, and
mention `prefer_homebrew` in the README/TUI description.

## Files touched

| File | Change |
|---|---|
| `default.config.yml` | `prefer_homebrew`, `brew_apt_equivalents` |
| `main.yml` | detection import, brew list gating, group dispatcher, update gating |
| `tasks/package_manager.yml` | new: brew detection and initialization |
| `tasks/package_resolve.yml` | new: effective-list resolution (side-effect free) |
| `tasks/package_group.yml` | new: imports the resolver, Homebrew, and apt tasks |
| `tests/test_brew_detection.yml` | new: portable assertions for detection/preference |
| `tests/test_package_precedence.yml` | new: assertions for resolution scenarios |
| `tasks/homebrew_list.yml` | absolute brew, available formulae list |
| `tasks/homebrew_packages.yml` | `path`, macOS-only casks |
| `tasks/apt_packages.yml` | comment/fallback wording only |
| `tasks/git.yml` | brew-first, apt only without brew |
| `tasks/krew.yml` | brew-first, manual only without brew |
| `tasks/ai-dev-tools.yml` | use package dispatcher |
| `tasks/ansible-pull-cron.yml` | Linuxbrew in cron PATH |
| `setup-config-menu.json` | `prefer_homebrew` toggle |
| `tests/test_setup_config.py` | system item count |
| `AGENTS.md`, `README.md` | conventions and toggle |

## Risks and edge cases

- `brew formulae` is a large list (~17k on this machine) and may warn about
  untrusted taps on stderr. It is read once, errors are ignored, and stdout
  is the only input.
- Auto-promotion may move a package from apt to brew without a config edit.
  The alias map and curated group lists limit surprises; set
  `prefer_homebrew: false` to force apt.
- Some macOS GUI casks have Linux apt equivalents (`vlc`, `nextcloud`). On
  Linux the cask is skipped and apt supplies the app; on macOS apt is not
  used and the cask supplies it.
- On Linux+brew, `git` and `krew` must not be installed twice. Their apt and
  manual branches are gated off whenever brew is available.
- Unattended runs still cannot install fallback apt packages without a
  become password; brew packages continue to install.

## Verification

- `ansible-playbook --syntax-check -i localhost, main.yml`
- `ansible-lint main.yml tasks/package_manager.yml tasks/package_group.yml
  tasks/homebrew_packages.yml tasks/homebrew_list.yml tasks/git.yml
  tasks/krew.yml tasks/ai-dev-tools.yml tasks/apt_packages.yml`
- `python3 -m unittest tests.test_setup_config`
- `ansible-playbook -i localhost, -c local tests/test_brew_detection.yml`
  asserts detection consistency with and without `prefer_homebrew`.
- `ansible-playbook -i localhost, -c local tests/test_package_precedence.yml`
  asserts the resolution scenarios below without installing anything:
  - A test play that imports the resolution logic for representative
    groups, expecting:
  - sync: brew `syncthing`, apt `nextcloud-desktop`
  - kube: brew `kubernetes-cli`/`kubectx`, no apt fallback
  - ai: brew `fzf`/`node`, no apt `fzf`/`nodejs`/`npm`
  - dev-gui: no brew formula, apt `fonts-firacode`
  - media: brew `handbrake`
  - `prefer_homebrew: false` on Linux: apt lists only
- `ansible-playbook main.yml --list-tasks` to confirm the group dispatches
  are present exactly once.
