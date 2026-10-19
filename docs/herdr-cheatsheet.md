# Herdr Cheat Sheet

## Prefix Key: `ctrl+b`

Press `ctrl+b`, release, then press the action key.

---

## Core Herdr Shortcuts

### Navigation

| Shortcut | Action |
|----------|--------|
| `prefix+h/j/k/l` | Focus pane left/down/up/right |
| `prefix+w` | Open workspace picker |
| `prefix+g` | Open session navigator (goto) |
| `prefix+b` | Toggle sidebar collapse |

### Tabs

| Shortcut | Action |
|----------|--------|
| `prefix+c` | New tab |
| `prefix+n/p` | Next/previous tab |
| `prefix+1..9` | Jump to tab 1–9 |
| `prefix+shift+t` | Rename tab |
| `prefix+shift+x` | Close tab |

### Panes

| Shortcut | Action |
|----------|--------|
| `prefix+v` | Split right |
| `prefix+-` | Split down |
| `prefix+x` | Close pane |
| `prefix+z` | Zoom pane |
| `prefix+shift+h/j/k/l` | Swap pane |
| `prefix+tab` | Cycle to next pane |
| `prefix+shift+tab` | Cycle to previous pane |
| `prefix+e` | Edit scrollback in $EDITOR |

### Workspaces

| Shortcut | Action |
|----------|--------|
| `prefix+shift+n` | New workspace |
| `prefix+shift+w` | Rename workspace |
| `prefix+shift+d` | Close workspace |

### General

| Shortcut | Action |
|----------|--------|
| `prefix+?` | Show all active bindings |
| `prefix+s` | Open settings |
| `prefix+q` | Detach (leave everything running) |
| `prefix+shift+r` | Reload config |
| `prefix+shift+g` | New worktree (default: Herdr built-in) |
| `prefix+shift+o` | Open notification target |

### Copy Mode

| Shortcut | Action |
|----------|--------|
| `prefix+[` | Enter copy mode |

---

## Worktrunk Plugin Shortcuts

> These override Herdr's built-in worktree actions on the same keys.
> Requires: worktrunk (`wt`), fzf, jq installed.

| Shortcut | Action |
|----------|--------|
| `prefix+shift+G` | Switch / create worktree from **default branch** |
| `prefix+shift+C` | Switch / create worktree from **current branch** |
| `prefix+shift+M` | **Merge** into target branch (then remove) |

### How It Works

1. Press the keybinding → fzf picker opens
2. Pick or type a branch name
3. Worktree is created/switched, lifecycle hooks run
4. A new Herdr workspace opens with the worktree

### Full Action List

| CLI Action | Description |
|------------|-------------|
| `worktrunk.open` | Switch/create from default branch |
| `worktrunk.open-current` | Switch/create from current branch |
| `worktrunk.open-with-remotes` | Switch/create including remote-tracking branches |
| `worktrunk.remove` | Remove a worktree |
| `worktrunk.merge` | Merge into target branch, then remove |
| `worktrunk.merge-no-squash` | Merge keeping every commit, then remove |

---

## Mouse Interactions

- **Click panes/tabs** to focus them
- **Drag split borders** to resize
- **Right-click** for context menus
- **Drag-select** to copy text
- **Sidebar**: click on workspaces, agents, tabs to navigate

---

## Useful CLI Commands

```bash
herdr status              # Overview of sessions and agents
herdr session list        # List all sessions
herdr agent list          # List detected agents
herdr agent explain <id>  # Debug agent detection (--json for details)
herdr integration status  # Check integration versions
herdr plugin action list  # List available plugin actions
herdr --default-config    # Print full default config
```

---

## Quick Reference: Prefix + Key

```
ctrl+b  ?   → Show all bindings
ctrl+b  q   → Detach
ctrl+b  b   → Toggle sidebar
ctrl+b  w   → Workspace picker
ctrl+b  g   → Session navigator
ctrl+b  c   → New tab
ctrl+b  v   → Split right
ctrl+b  -   → Split down
ctrl+b  h/j/k/l → Focus pane
ctrl+b  z   → Zoom pane
ctrl+b  [   → Copy mode
ctrl+b  +   → Settings
```
