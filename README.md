# Workstation Setup

## Bootstrap

curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/bootstrap.sh | zsh

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