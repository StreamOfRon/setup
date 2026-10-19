# Workstation Setup

## Bootstrap

curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/bootstrap.sh | zsh

## Configuration tool

Run `setup-config` to manage package groups and local settings. Changes are
written to `~/.setup-options`; each change offers to apply the playbook.

Apply without opening the TUI:

```sh
setup-config --apply-now
```