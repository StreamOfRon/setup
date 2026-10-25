# Package Manager Precedence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prefer Homebrew formulae on machines that have both brew and apt, use apt only for packages brew cannot supply, and never install casks outside macOS.

**Architecture:** A new detection task sets `brew_available` independently of `ansible_facts.pkg_mgr`. A side-effect-free resolver computes the brew formula list and the apt fallback list for each group, then a dispatcher imports the existing Homebrew and apt task files. Group blocks in `main.yml` stop branching on `pkg_mgr` for brew.

**Tech Stack:** Ansible (YAML playbooks/task files), Jinja2 expressions, Community General Homebrew modules, Python stdlib `unittest` for the config tool.

**Spec:** `docs/superpowers/specs/2026-10-25-package-manager-precedence-design.md`

## Global Constraints

- Use `brew_available | bool` in every condition. `set_fact` may store the value as a bool here, but the `| bool` guard prevents the string `"False"` from being truthy on other Ansible versions.
- Casks run only when `ansible_facts.system == "Darwin"`.
- Install (`enabled: true`) filters apt packages covered by brew. Removal (`enabled: false`) passes the full apt list.
- Keep the three-valued group semantics: `true` install, `false` remove, `ignore` skip.
- Do not change official-installer tasks (`uv`, `opencode`, `omp`, `herdr`, `rustup`) or `bootstrap.sh`.
- Keep existing task-file structure; do not introduce roles.
- Local test commands use `-i localhost, -c local`.
- Match the repo's plain imperative commit style.

## Review Focus

- **Casks must never run on Linux.** `tasks/homebrew_packages.yml` must include the Darwin guard on the cask task. Pinned by a grep assertion in Task 3.
- **`brew_available` truthiness.** A string `"False"` is truthy in Ansible. Every consumer must use `| bool`. Pinned by `tests/test_brew_detection.yml` and a grep in Task 2.
- **Removal must not filter the apt list.** `enabled: false` must pass every apt package so packages installed by either manager are removed. Pinned by the removal scenarios in Task 4.
- **Renamed equivalents must not double-install.** `nodejs`/`npm` must not follow `node`, and `kubectl` must not follow `kubernetes-cli`. Pinned by the kube and AI scenarios in Task 4.
- **Unattended cron runs must find Linuxbrew.** Without the Linuxbrew directories in the cron `PATH`, `brew_available` is false and the old apt behavior returns. Pinned by a grep assertion in Task 2.

---

### Task 1: Add the preference defaults and TUI toggle

**Files:**
- Modify: `default.config.yml`
- Modify: `setup-config-menu.json`
- Modify: `tests/test_setup_config.py:71-75`

**Interfaces:**
- Produces: `prefer_homebrew` (bool, default `true`) and `brew_apt_equivalents` (mapping apt name → brew formula) available to every playbook task.
- Produces: a `prefer_homebrew` menu item in the `system` category.

- [ ] **Step 1: Write the failing test**

In `tests/test_setup_config.py`, change the system item count from 7 to 8 and add:

```python
    def test_prefer_homebrew_toggle(self):
        items = {i.key: i for c in self.menu.categories for i in c.items}
        self.assertIn("prefer_homebrew", items)
        self.assertEqual(items["prefer_homebrew"].kind, "bool")
        self.assertIs(self.defaults["prefer_homebrew"], True)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_setup_config.MenuTests -v`

Expected: FAIL — count is 7, and `prefer_homebrew` is missing from the menu.

- [ ] **Step 3: Add the defaults**

In `default.config.yml`, after the `agent_python_packages` block and before `vscode`, add:

```yaml
# Prefer Homebrew formulae over apt when both are available (Linuxbrew).
# Ignored on macOS, where Homebrew is the only supported package manager.
prefer_homebrew: true

# Apt package names that a Homebrew formula also provides under a different
# name. Used to avoid installing both when Homebrew is preferred.
brew_apt_equivalents:
  nodejs: node
  npm: node
  kubectl: kubernetes-cli
```

- [ ] **Step 4: Add the TUI menu item**

In `setup-config-menu.json`, in the `system` category, insert after the `oh_my_zsh` item:

```json
        {
          "key": "prefer_homebrew",
          "label": "Prefer Homebrew over apt",
          "type": "bool"
        },
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_setup_config -v`

Expected: PASS, including `test_categories_and_counts` and `test_prefer_homebrew_toggle`.

- [ ] **Step 6: Commit**

```bash
git add default.config.yml setup-config-menu.json tests/test_setup_config.py docs/superpowers/specs/2026-10-25-package-manager-precedence-design.md docs/superpowers/plans/2026-10-25-package-manager-precedence.md
git commit -m "Add Homebrew preference settings and plan"
```

---

### Task 2: Detect Homebrew independently of pkg_mgr

**Files:**
- Create: `tasks/package_manager.yml`
- Create: `tests/test_brew_detection.yml`
- Modify: `main.yml:21-50`
- Modify: `tasks/homebrew_list.yml`
- Modify: `tasks/ansible-pull-cron.yml:7-11`

**Interfaces:**
- Produces: `brew_bin` (string path), `brew_bin_dir` (string), `brew_available` (bool-ish; always consumed with `| bool`).
- Produces: `installed_brew_formulae`, `installed_brew_casks`, `brew_taps`, `available_brew_formulae`, each with a `stdout_lines` list, even when brew is unavailable.

- [ ] **Step 1: Write the failing detection test**

Create `tests/test_brew_detection.yml`:

```yaml
- name: Homebrew detection
  hosts: localhost
  gather_facts: true
  tasks:
    - name: Detect with Homebrew preferred
      ansible.builtin.import_tasks: ../tasks/package_manager.yml
      vars:
        prefer_homebrew: true

    - name: Assert detection matches brew presence
      ansible.builtin.assert:
        that:
          - (brew_available | bool) == (brew_bin | length > 0)

    - name: Detect with Homebrew not preferred
      ansible.builtin.import_tasks: ../tasks/package_manager.yml
      vars:
        prefer_homebrew: false

    - name: Assert preference only disables brew where apt is an alternative
      ansible.builtin.assert:
        that:
          - (brew_available | bool) == ((brew_bin | length > 0) and ansible_facts.pkg_mgr == "homebrew")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `ansible-playbook -i localhost, -c local tests/test_brew_detection.yml`

Expected: FAIL — `../tasks/package_manager.yml` does not exist.

- [ ] **Step 3: Create the detection task file**

Create `tasks/package_manager.yml`:

```yaml
# Resolve whether Homebrew should win over apt. On Linux, Ansible reports
# pkg_mgr == "apt" even when Linuxbrew is installed, so brew detection must be
# independent of pkg_mgr.
- name: Locate Homebrew
  ansible.builtin.command:
    cmd: which brew
  environment:
    PATH: >-
      {{ lookup('env', 'HOME') }}/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/bin:/opt/homebrew/bin:/usr/local/bin:{{ ansible_facts.env.PATH | default('/usr/bin:/bin') }}
  register: brew_lookup
  changed_when: false
  failed_when: false

- name: Record Homebrew availability
  ansible.builtin.set_fact:
    brew_bin: "{{ brew_lookup.stdout | trim }}"
    brew_bin_dir: "{{ (brew_lookup.stdout | trim) | dirname }}"
    brew_available: >-
      {{ (brew_lookup.rc | default(1)) == 0
         and (brew_lookup.stdout | trim | length > 0)
         and ((prefer_homebrew | default(true) | bool) or ansible_facts.pkg_mgr == "homebrew") }}

# Keep every later expression free of undefined-variable handling.
- name: Initialise empty Homebrew package lists
  ansible.builtin.set_fact:
    installed_brew_formulae: {stdout_lines: []}
    installed_brew_casks: {stdout_lines: []}
    brew_taps: {stdout_lines: []}
    available_brew_formulae: {stdout_lines: []}
  when: not (brew_available | bool)
```

- [ ] **Step 4: Run the detection test to verify it passes**

Run: `ansible-playbook -i localhost, -c local tests/test_brew_detection.yml`

Expected: PASS on this machine (brew is at `/home/linuxbrew/.linuxbrew/bin/brew`) and on machines without brew.

- [ ] **Step 5: Wire detection into the play and gate the snapshots on it**

In `main.yml`, add this import immediately after the "Include local configuration" task and before "Ensure uv is installed":

```yaml
    - name: Resolve package manager preference
      ansible.builtin.import_tasks: tasks/package_manager.yml
```

In the "Get list of installed packages" block, change the Homebrew condition from `ansible_facts.pkg_mgr == "homebrew"` to `brew_available | bool`:

```yaml
        - name: Get installed homebrew packages
          ansible.builtin.import_tasks: tasks/homebrew_list.yml
          when: brew_available | bool
```

In the "Update package managers" block, change the Homebrew update condition and pass the detected path:

```yaml
        - name: Update homebrew packages
          community.general.homebrew:
            update_homebrew: true
            path: "{{ brew_bin_dir }}"
          when: brew_available | bool
```

- [ ] **Step 6: Add the available-formulae snapshot**

Replace `tasks/homebrew_list.yml` with:

```yaml
- name: Get list of installed formulae
  ansible.builtin.command: "{{ brew_bin }} list --formulae -1"
  register: installed_brew_formulae
  changed_when: false

- name: Get list of installed casks
  ansible.builtin.command: "{{ brew_bin }} list --casks -1"
  register: installed_brew_casks
  changed_when: false

- name: Get list of taps
  ansible.builtin.command: "{{ brew_bin }} tap"
  register: brew_taps
  changed_when: false

# Used to promote apt package names that have a same-named brew formula.
- name: Get list of available formulae
  ansible.builtin.command: "{{ brew_bin }} formulae"
  register: available_brew_formulae
  changed_when: false
  failed_when: false
```

- [ ] **Step 7: Add Linuxbrew to the cron PATH**

In `tasks/ansible-pull-cron.yml`, replace the "Setup cron PATH" job value with:

```yaml
    job: "/opt/homebrew/bin:/opt/homebrew/sbin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"
```

- [ ] **Step 8: Verify syntax, lint, and the bool guard**

Run:

```bash
ansible-playbook --syntax-check -i localhost, -c local main.yml
ansible-lint tasks/package_manager.yml tasks/homebrew_list.yml tasks/ansible-pull-cron.yml main.yml
grep -n 'when: brew_available' main.yml
```

Expected: syntax and lint clean; every `brew_available` condition in `main.yml` shows `| bool`.

- [ ] **Step 9: Commit**

```bash
git add tasks/package_manager.yml tests/test_brew_detection.yml main.yml tasks/homebrew_list.yml tasks/ansible-pull-cron.yml
git commit -m "Detect Homebrew independently of apt"
```

---

### Task 3: Make Homebrew and apt task files precedence-aware

**Files:**
- Modify: `tasks/homebrew_packages.yml`
- Modify: `tasks/apt_packages.yml:1-9`

**Interfaces:**
- Consumes: `brew_bin_dir` from Task 2.
- Produces: Homebrew modules search the detected brew root; the cask task is macOS-only.

- [ ] **Step 1: Add the Darwin guard and brew path**

In `tasks/homebrew_packages.yml`, add `path: "{{ brew_bin_dir }}"` to the tap, formula, and cask modules. Add `- ansible_facts.system == "Darwin"` as the first condition on the cask task. The three task headers become:

```yaml
- name: Homebrew taps for {{ groupname }}
  community.general.homebrew_tap:
    name: "{{ taps }}"
    path: "{{ brew_bin_dir }}"
    state: '{{ enabled | ternary("present", "absent") }}'
```

```yaml
- name: Homebrew formulae for {{ groupname }}
  community.general.homebrew:
    name: "{{ formulae }}"
    path: "{{ brew_bin_dir }}"
    state: '{{ enabled | ternary("latest", "absent") }}'
```

```yaml
- name: Homebrew casks for {{ groupname }}
  community.general.homebrew_cask:
    name: "{{ casks }}"
    path: "{{ brew_bin_dir }}"
    state: '{{ enabled | ternary("present", "absent") }}'
    sudo_password: "{{ ansible_become_password | default() }}"
  when:
    - ansible_facts.system == "Darwin"
    - casks | length > 0
    - casks | difference(installed_brew_casks.stdout_lines) | length > 0 or
      (casks | intersect(installed_brew_casks.stdout_lines) | length > 0 and not enabled)
    - enabled != "ignore"
```

- [ ] **Step 2: Update the apt task-file comment**

Replace the header comment in `tasks/apt_packages.yml` with:

```yaml
# Apt (Debian/Ubuntu) fallback for a package group.
#
# Groups run Homebrew first (tasks/package_group.yml); when the group is
# enabled, `packages` already excludes anything Homebrew provides. On removal
# (enabled false) the full apt list is passed so packages installed by either
# manager are cleaned up.
```

Leave the task logic unchanged.

- [ ] **Step 3: Verify the Darwin guard and syntax**

Run:

```bash
grep -A8 'name: Homebrew casks' tasks/homebrew_packages.yml | grep 'Darwin'
ansible-playbook --syntax-check -i localhost, -c local main.yml
ansible-lint tasks/homebrew_packages.yml tasks/apt_packages.yml
```

Expected: the grep prints the Darwin condition; syntax and lint clean.

- [ ] **Step 4: Commit**

```bash
git add tasks/homebrew_packages.yml tasks/apt_packages.yml
git commit -m "Gate casks to macOS and pass the brew path"
```

---

### Task 4: Add the resolver, dispatcher, and migrate the groups

**Files:**
- Create: `tasks/package_resolve.yml`
- Create: `tasks/package_group.yml`
- Create: `tests/test_package_precedence.yml`
- Modify: `main.yml:78-343` (the ten group blocks)
- Modify: `tasks/ai-dev-tools.yml:5-22`

**Interfaces:**
- Consumes: `brew_available`, `available_brew_formulae`, `installed_brew_formulae` (Task 2); `brew_apt_equivalents` (Task 1).
- Produces: `_group_formulae`, `_group_brew_present`, `_group_apt_covered`, `_group_apt_packages`.
- Produces: `tasks/package_group.yml` accepting `enabled`, `groupname`, `formulae`, `casks`, `apt_packages`, and optional `taps`.

- [ ] **Step 1: Write the failing resolution test**

Create `tests/test_package_precedence.yml`:

```yaml
- name: Package precedence resolution
  hosts: localhost
  gather_facts: false
  vars_files:
    - ../default.config.yml
  vars:
    available_brew_formulae:
      stdout_lines:
        - handbrake
        - kubectx
        - kubernetes-cli
        - node
        - syncthing
        - zstd
    installed_brew_formulae:
      stdout_lines: []
  tasks:
    - name: Same-name apt package with a brew formula
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: media
        formulae: "{{ media_formulae }}"
        apt_packages: "{{ media_apt_packages }}"
    - name: Media resolves to brew
      ansible.builtin.assert:
        that:
          - _group_formulae == ['handbrake']
          - _group_apt_packages == []

    - name: Sync group with a brew formula and an apt-only package
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: sync
        formulae: "{{ sync_formulae }}"
        apt_packages: "{{ sync_apt_packages }}"
    - name: Sync resolves to brew plus one apt gap
      ansible.builtin.assert:
        that:
          - _group_formulae | sort == ['syncthing']
          - _group_apt_packages == ['nextcloud-desktop']

    - name: Renamed kube equivalent
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: kube
        formulae: "{{ kube_formulae }}"
        apt_packages: "{{ kube_apt_packages }}"
    - name: Kube resolves without duplicate kubectl
      ansible.builtin.assert:
        that:
          - _group_formulae | sort == ['argocd', 'kubectx', 'kubernetes-cli']
          - _group_apt_packages == []

    - name: Renamed node equivalents
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: ai-dev-tools
        formulae: "{{ ai_dev_tools_formulae }}"
        apt_packages: "{{ ai_dev_tools_apt_packages }}"
    - name: AI tools resolve without nodejs or npm
      ansible.builtin.assert:
        that:
          - _group_apt_packages == []

    - name: No brew formula exists
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: dev-gui
        formulae: "{{ dev_gui_formulae }}"
        apt_packages: "{{ dev_gui_apt_packages }}"
    - name: Dev GUI falls back to apt
      ansible.builtin.assert:
        that:
          - _group_formulae == []
          - _group_apt_packages == ['fonts-firacode']

    - name: Removal keeps the full apt list
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: false
        groupname: sync
        formulae: "{{ sync_formulae }}"
        apt_packages: "{{ sync_apt_packages }}"
    - name: Removal list is unfiltered
      ansible.builtin.assert:
        that:
          - _group_apt_packages | sort == ['nextcloud-desktop', 'syncthing']

    - name: Brew unavailable
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: sync
        formulae: "{{ sync_formulae }}"
        apt_packages: "{{ sync_apt_packages }}"
        available_brew_formulae: {stdout_lines: []}
        installed_brew_formulae: {stdout_lines: []}
    - name: Apt runs everything when brew is unavailable
      ansible.builtin.assert:
        that:
          - _group_formulae == []
          - _group_apt_packages | sort == ['nextcloud-desktop', 'syncthing']

    - name: Formula already installed by brew
      ansible.builtin.import_tasks: ../tasks/package_resolve.yml
      vars:
        enabled: true
        groupname: installed-check
        formulae: []
        apt_packages: [fzf, zstd]
        available_brew_formulae: {stdout_lines: []}
        installed_brew_formulae: {stdout_lines: [fzf]}
    - name: Installed brew formula shadows apt
      ansible.builtin.assert:
        that:
          - _group_apt_packages == ['zstd']
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `ansible-playbook -i localhost, -c local tests/test_package_precedence.yml`

Expected: FAIL — `../tasks/package_resolve.yml` does not exist.

- [ ] **Step 3: Create the resolver**

Create `tasks/package_resolve.yml`:

```yaml
# Compute the effective Homebrew and apt package lists for a group.
# Side-effect free so tests/test_package_precedence.yml can exercise it.
- name: Resolve effective package lists for {{ groupname }}
  ansible.builtin.set_fact:
    _group_formulae: >-
      {{ (formulae | default([]) +
          (apt_packages | default([]) | intersect(available_brew_formulae.stdout_lines | default([]))))
         | unique }}

- name: Resolve Homebrew coverage for {{ groupname }}
  ansible.builtin.set_fact:
    _group_brew_present: >-
      {{ (_group_formulae + (installed_brew_formulae.stdout_lines | default([]))) | unique }}

- name: Resolve aliases covered by Homebrew for {{ groupname }}
  ansible.builtin.set_fact:
    _group_apt_covered: >-
      {{ brew_apt_equivalents | default({}) | dict2items
         | selectattr('value', 'in', _group_brew_present)
         | map(attribute='key') | list }}

- name: Resolve apt fallback packages for {{ groupname }}
  ansible.builtin.set_fact:
    _group_apt_packages: >-
      {{ ((apt_packages | default([])) | difference(_group_apt_covered) | difference(_group_brew_present))
         if enabled == true else (apt_packages | default([])) }}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `ansible-playbook -i localhost, -c local tests/test_package_precedence.yml`

Expected: PASS, all eight scenarios.

- [ ] **Step 5: Create the dispatcher**

Create `tasks/package_group.yml`:

```yaml
# Manage one package group with Homebrew-first precedence:
# formulae -> apt fallback -> casks (macOS only).
#
# Vars: enabled, groupname, formulae, casks, apt_packages, taps (optional).
- name: Resolve package lists for {{ groupname }}
  ansible.builtin.import_tasks: tasks/package_resolve.yml

- name: Manage Homebrew packages for {{ groupname }}
  ansible.builtin.import_tasks: tasks/homebrew_packages.yml
  vars:
    enabled: "{{ enabled }}"
    groupname: "{{ groupname }}"
    taps: "{{ taps | default([]) }}"
    formulae: "{{ _group_formulae }}"
    casks: "{{ casks | default([]) }}"
  when: brew_available | bool

- name: Manage apt fallback packages for {{ groupname }}
  ansible.builtin.import_tasks: tasks/apt_packages.yml
  vars:
    enabled: "{{ enabled }}"
    groupname: "{{ groupname }}"
    packages: "{{ _group_apt_packages }}"
  when: ansible_facts.pkg_mgr == "apt"
```

- [ ] **Step 6: Replace each group's two imports with one dispatcher import**

Apply this pattern to every group block in `main.yml`:

```yaml
    - name: Manage <group label>
      block:
        - name: Manage <group label> packages
          ansible.builtin.import_tasks: tasks/package_group.yml
          vars:
            enabled: "{{ <toggle> | default(false) }}"
            groupname: <groupname>
            formulae: "{{ <formulae list> }}"
            casks: "{{ <casks list> }}"
            apt_packages: "{{ <apt list> }}"
      rescue:
        - name: Warn about <group label> install failure
          ansible.builtin.debug:
            msg: "Failed to manage <group label>, continuing: {{ ansible_failed_result | default('unknown error') }}"
```

Use these exact values:

| Label | `enabled` | `groupname` | `formulae` | `casks` | `apt_packages` | extra |
|---|---|---|---|---|---|---|
| sync tools | `install_sync_tools` | `sync` | `sync_formulae` | `sync_casks` | `sync_apt_packages` | |
| misc apps | `install_misc_apps` | `misc` | `misc_formulae` | `misc_casks` | `misc_apt_packages` | |
| entertainment apps | `install_entertainment_apps` | `entertainment` | `entertainment_formulae` | `entertainment_casks` | `entertainment_apt_packages` | |
| media tools | `install_media_tools` | `media` | `media_formulae` | `media_casks` | `media_apt_packages` | |
| kube tools | `install_kube_apps` | `kube` | `kube_formulae` | `kube_casks` | `kube_apt_packages` | `taps: "{{ kube_taps }}"` |
| dev cli tools | `install_dev_cli_tools` | `dev-cli` | `dev_cli_formulae` | `dev_cli_casks` | `dev_cli_apt_packages` | keep the rustup import after the dispatcher |
| dev gui tools | `install_dev_gui_tools` | `dev-gui` | `dev_gui_formulae` | `dev_gui_casks` | `dev_gui_apt_packages` | |
| common cli tools | `install_common_cli_tools` | `common cli` | `common_cli_formulae` | `common_cli_casks` | `common_cli_apt_packages` | |
| aws tools | `install_aws_tools` | `aws` | `aws_formulae` | `aws_casks` | `aws_apt_packages` | |
| other packages | `install_other_apps` | `other` | `install_other_formulae` | `install_other_casks` | `install_other_apt_packages` | default `true`, not `false` |

Do not add a `taps` var to groups that do not have one.

- [ ] **Step 7: Migrate the AI group**

In `tasks/ai-dev-tools.yml`, replace the two imports at the top ("Homebrew packages for ai dev tools" and "Apt packages for ai dev tools") with:

```yaml
- name: Manage ai dev tools packages
  ansible.builtin.import_tasks: tasks/package_group.yml
  vars:
    enabled: "{{ install_ai_dev_tools | default(false) }}"
    groupname: ai-dev-tools
    formulae: "{{ ai_dev_tools_formulae }}"
    casks: "{{ ai_dev_tools_casks }}"
    apt_packages: "{{ ai_dev_tools_apt_packages }}"
```

Leave the remaining install/config/remove tasks unchanged.

- [ ] **Step 8: Verify the migration**

Run:

```bash
ansible-playbook -i localhost, -c local tests/test_package_precedence.yml
ansible-playbook --syntax-check -i localhost, -c local main.yml
ansible-lint tasks/package_resolve.yml tasks/package_group.yml tasks/ai-dev-tools.yml main.yml
grep -c 'tasks/package_group.yml' main.yml
grep -c 'tasks/package_group.yml' tasks/ai-dev-tools.yml
ansible-playbook -i localhost, -c local main.yml --list-tasks | grep -E 'Manage (sync tools|kube tools|ai dev tools|other) packages'
```

Expected: resolution test PASS; syntax and lint clean; `main.yml` has 10 dispatcher imports; `ai-dev-tools.yml` has 1; each spot-checked group task appears once in `--list-tasks`.

- [ ] **Step 9: Commit**

```bash
git add tasks/package_resolve.yml tasks/package_group.yml tests/test_package_precedence.yml main.yml tasks/ai-dev-tools.yml
git commit -m "Prefer Homebrew packages with apt fallback"
```

---

### Task 5: Apply the same preference to git and krew

**Files:**
- Modify: `tasks/git.yml`
- Modify: `tasks/krew.yml`

**Interfaces:**
- Consumes: `brew_available`, `brew_bin_dir`, `installed_brew_formulae` (Task 2).

- [ ] **Step 1: Update git**

Replace `tasks/git.yml` with:

```yaml
# Ensure git is always installed. git is a hard dependency of ansible-pull
# (and of many other tasks), so it must not be tied to an optional group.
#
# Homebrew wins whenever it is available. apt is used only when brew is not
# preferred/available, and then only with a sudo password and when dpkg does
# not already have git.
- name: Ensure git is installed (Homebrew)
  when:
    - brew_available | bool
    - "'git' not in (installed_brew_formulae.stdout_lines | default([]))"
  block:
    - name: Ensure git is installed (Homebrew)
      community.general.homebrew:
        name: git
        state: present
        path: "{{ brew_bin_dir }}"

- name: Ensure git is installed (apt)
  when:
    - ansible_facts.pkg_mgr == "apt"
    - not (brew_available | bool)
    - ansible_become_password is defined
    - "'git' not in (installed_apt_packages.stdout_lines | default([]))"
  block:
    - name: Ensure git is installed (apt)
      ansible.builtin.apt:
        name: git
        state: present
      become: true
```

- [ ] **Step 2: Update krew**

In `tasks/krew.yml`, change the header comment and conditions:

```yaml
# Install krew itself. All krew setup lives here:
#   - Homebrew systems: manage the `krew` formula via Homebrew.
#   - Systems without Homebrew: follow the manual instructions at
#     https://krew.sigs.k8s.io/docs/user-guide/setup/install/.

- name: Manage krew via Homebrew
  ansible.builtin.import_tasks: tasks/homebrew_packages.yml
  vars:
    enabled: "{{ install_kube_apps | default(false) }}"
    groupname: krew
    taps: []
    formulae:
      - krew
    casks: []
  when:
    - brew_available | bool

- name: Ensure git is installed (krew prerequisite, no Homebrew)
  when:
    - install_kube_apps | default(false) == true
    - not (brew_available | bool)
    - ansible_become_password is defined
    - "'git' not in (installed_apt_packages.stdout_lines | default([]))"
  block:
    - name: Ensure git is installed (krew prerequisite, no Homebrew)
      ansible.builtin.apt:
        name: git
        state: present
      become: true

- name: Install krew via manual instructions (no Homebrew)
  ansible.builtin.shell: |
    set -e
    cd "$(mktemp -d)"
    OS="$(uname | tr '[:upper:]' '[:lower:]')"
    ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')"
    KREW="krew-${OS}_${ARCH}"
    curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz"
    tar zxvf "${KREW}.tar.gz"
    ./"${KREW}" install krew
  args:
    executable: /bin/bash
  changed_when: false
  when:
    - install_kube_apps | default(false) == true
    - not (brew_available | bool)
```

- [ ] **Step 3: Verify**

Run:

```bash
ansible-playbook --syntax-check -i localhost, -c local main.yml
ansible-lint tasks/git.yml tasks/krew.yml
grep -n 'brew_available' tasks/git.yml tasks/krew.yml
```

Expected: syntax and lint clean; every brew gate uses `| bool`, and every apt/manual gate uses `not (brew_available | bool)`.

- [ ] **Step 4: Commit**

```bash
git add tasks/git.yml tasks/krew.yml
git commit -m "Prefer Homebrew for git and krew"
```

---

### Task 6: Document the precedence and run the full verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Add the convention to AGENTS.md**

Add this section under the existing conventions (after the apt-package-presence section):

```markdown
### Package manager precedence
- Prefer Homebrew whenever `brew` is available, even on Linux where
  `ansible_facts.pkg_mgr` reports `apt`. `tasks/package_manager.yml` sets
  `brew_available`; gate brew tasks on `brew_available | bool`, never on
  `pkg_mgr == "homebrew"`.
- Group dispatch lives in `tasks/package_group.yml`: Homebrew formulae run
  first, apt supplies only packages Homebrew cannot, and casks run only on
  macOS.
- `brew_apt_equivalents` in `default.config.yml` maps apt names to brew
  formulae that use a different name. Same-name packages are covered
  automatically from `brew formulae`.
- Set `prefer_homebrew: false` to force apt on a Linux machine that has
  Homebrew installed.
```

- [ ] **Step 2: Mention the toggle in README.md**

After the `setup-config` paragraph, add:

```markdown
`prefer_homebrew` (default on) makes the playbook use Homebrew formulae
ahead of apt when both are available; apt is used only for packages
Homebrew does not provide.
```

- [ ] **Step 3: Run the full verification suite**

Run:

```bash
ansible-playbook --syntax-check -i localhost, -c local main.yml
ansible-lint main.yml tasks/package_manager.yml tasks/package_resolve.yml tasks/package_group.yml tasks/homebrew_packages.yml tasks/homebrew_list.yml tasks/apt_packages.yml tasks/git.yml tasks/krew.yml tasks/ai-dev-tools.yml tasks/ansible-pull-cron.yml
python3 -m unittest tests.test_setup_config
ansible-playbook -i localhost, -c local tests/test_brew_detection.yml
ansible-playbook -i localhost, -c local tests/test_package_precedence.yml
```

Expected: all commands exit 0; both resolution test plays report `failed=0`.

- [ ] **Step 4: Confirm the old dispatch is gone**

Run:

```bash
grep -n 'pkg_mgr == "homebrew"' main.yml tasks/ai-dev-tools.yml tasks/git.yml tasks/krew.yml tasks/homebrew_list.yml
```

Expected: no output. (The only `pkg_mgr` checks left are `== "apt"` for the fallback and the macOS-only App Store path.)

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md
git commit -m "Document Homebrew package precedence"
```

---

## Self-Review Notes

- Spec coverage: detection (§1), snapshot (§2), resolution/dispatch (§3), cask guard (§4), group wiring (§5), updates (§6), cron (§7), TUI (§8), docs (§9). Every section maps to a task.
- Test coverage: `tests/test_brew_detection.yml` covers detection and `prefer_homebrew`; `tests/test_package_precedence.yml` covers same-name promotion, renamed aliases, apt gaps, removal, brew-unavailable, and already-installed formulae. The cask guard is pinned by the Step 3 grep in Task 3.
- Naming is consistent across tasks: `brew_available`, `brew_bin`, `brew_bin_dir`, `_group_formulae`, `_group_brew_present`, `_group_apt_covered`, `_group_apt_packages`.
