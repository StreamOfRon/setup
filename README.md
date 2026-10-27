# Workstation Setup

## Bootstrap

curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/bootstrap.sh | zsh

## Package groups

Each group accepts three values:

- `true` installs the group and writes its managed configuration.
- `false` removes the group's packages and managed configuration.
- `ignore` leaves the machine alone.

Package groups default to `ignore`. A fresh checkout installs nothing and
removes nothing; opting in is an explicit act. Use `setup-config` (below) or
set a group to `true` in `~/.setup-options`. `false` is destructive, so only
choose it when you want the playbook to uninstall that group.

## Configuration tool

Run `setup-config` to manage package groups and local settings. The TUI uses
the arrow keys (or `h`/`j`/`k`/`l`) to move between categories and options,
`Enter` to toggle or edit a value, `r` to reset an option, `a` to apply the
playbook, and `q` to quit. Changes are written to `~/.setup-options`.

The tool is a standalone Python script with its dependencies declared inline
(PEP 723). It runs under [uv](https://docs.astral.sh/uv/), which the playbook
installs as a prerequisite.

Apply without opening the TUI:

```sh
setup-config --apply-now
```

On Debian/Ubuntu the package tasks need root. Pass `--ask-become-pass` so
Ansible prompts for your sudo password; without it those tasks are skipped, as
they are in unattended `ansible-pull` runs:

```sh
setup-config --apply-now --ask-become-pass
```

The TUI asks the same question before it applies.
