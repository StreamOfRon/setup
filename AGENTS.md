# AGENTS.md — workstation setup

Ansible-based workstation setup applied via `ansible-pull`. Targets macOS
(Homebrew) and Debian/Ubuntu (apt). Configuration is driven by
`default.config.yml` plus optional `~/.setup-options` overrides managed by
the `setup-config` TUI.

## Repository layout

- `main.yml` — playbook entry point (pre_tasks + tasks).
- `tasks/` — imported task files (`git.yml`, `apt_packages.yml`, `homebrew_packages.yml`, ...).
- `templates/` — Jinja2 templates rendered into `~`.
- `default.config.yml` — default configuration values.
- `setup-config` — standalone Python TUI (PEP 723) for editing `~/.setup-options`.
- `bootstrap.sh` — one-time bootstrap (installs ansible + git, then runs ansible-pull).
- `run-ansible-pull.sh` — full/quiet apply logic based on a stamp file.

## Conventions

### sudo / non-interactive runs
- Do **not** configure passwordless sudo. Bootstrap installs packages with an
  interactive `sudo`; unattended `ansible-pull` runs must not attempt sudo.
- Any task using `become: true` must be gated on `ansible_become_password is
  defined`. Running sudo-requiring tasks in a non-interactive context is a
  misconfiguration and should be skipped, not attempted.
- Apt cache updates (`ansible.builtin.apt: update_cache`) follow the same gate.

### Apt package presence checks
- Never do per-task `stat`/`command`/`which` checks for installed apt
  packages.
- Query the installed package list **once** in `pre_tasks` via
  `tasks/apt_list.yml` (`dpkg-query`) into `installed_apt_packages`, and use
  `installed_apt_packages.stdout_lines` as a condition in every apt task.
- Homebrew already follows this pattern with `tasks/homebrew_list.yml`
  (`installed_brew_formulae`, `installed_brew_casks`, `brew_taps`).

### Blocks for repeated conditions
- When several tasks share the same conditional check, wrap them in a
  `block:` with the `when:` at the block level so evaluation happens once.

### Idempotency / `creates`
- Shell/command install tasks (opencode, omp, herdr, uv, worktrunk, rustup,
  krew plugins, ...) must include an `args.creates` (or module `creates`)
  pointing at the resulting binary so they do not re-run on every apply.

### Debian/Ubuntu package naming
- On Debian/Ubuntu, `npx` ships in the `npm` package, separate from
  `nodejs`. Include `npm` in `*_apt_packages` whenever `npx` is needed.

### Rust toolchain fallbacks
- When a Homebrew/package-manager method is unavailable but a Rust toolchain
  is installed, install Rust-based tools (e.g. worktrunk) via
  `cargo install <crate>` with a `creates` guard on the resulting binary
  (`~/.local/bin/wt` for worktrunk, with `CARGO_HOME`/`RUSTUP_HOME` set to
  `~/.local`).

### Robustness for optional binaries
- Guard tasks that invoke optional binaries (`kubectl`, `npx`, `cargo`, ...)
  with a presence check and skip (with a debug note) when the binary is
  missing rather than failing the run.

### Verification
- Run `ansible-playbook --syntax-check -i localhost, main.yml` after edits.
- Run `ansible-lint` on changed task files.
- Python TUI tests: `python3 -m unittest tests.test_setup_config tests.test_playbook`.
- Push to `main` on `https://github.com/StreamOfRon/setup.git`.
