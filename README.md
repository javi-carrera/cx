# cx

A terminal UI for managing Claude Code sessions across git worktrees.

If you work with multiple git worktrees and run Claude Code sessions in each, cx gives you a single place to create, browse, launch, and manage them all.

## What it does

`cxx` opens a Textual TUI with two panels:

- **Worktrees** (left) — lists all git worktrees discovered via `git worktree list`. Shows the root worktree and any feature worktrees. Create new worktrees with scope/feature naming (`scope--feature-id`). When a matching branch exists on the remote, it's automatically checked out with a tracking branch.

- **Sessions** (right) — shows Claude Code sessions for the selected worktree. Active sessions display a green indicator. Launch a session and cx suspends, handing you a clean terminal with Claude Code running. Exit Claude Code and you're back in the TUI. Previously launched sessions are automatically resumed.

A **Settings** panel (`s` to toggle) lets you configure Claude Code launch options per session:

| Setting         | Options                                                              |
|-----------------|----------------------------------------------------------------------|
| Permission mode | `bypassPermissions`, `auto`, `acceptEdits`, `plan`, `default`, `dontAsk` |
| Model           | `opus`, `sonnet`, `haiku`                                            |
| Effort          | `high`, `low`, `medium`, `max`                                       |
| Verbose         | `OFF`, `ON`                                                          |
| Debug           | `OFF`, `ON`                                                          |

A **Status bar** at the bottom shows git info for the selected worktree: branch name, ahead/behind counts, staged/unstaged/untracked file counts, and last commit message.

`cx` is a quick launcher — clears the terminal and drops you straight into `claude --dangerously-skip-permissions` in the current directory.

## Usage

### `cxx` — Session Manager TUI

```
cxx
```

**Navigation:**

| Key               | Action                                           |
|--------------------|--------------------------------------------------|
| `Tab` / `Shift+Tab` | Switch between panels                          |
| `Left` / `Right`  | Switch between panels                             |
| `Up` / `Down`     | Navigate list items                               |
| `Enter`           | Select item / launch session / switch to sessions |
| `d`               | Delete highlighted worktree or session             |
| `s`               | Toggle settings panel                             |
| `Escape`          | Cancel current action                             |
| `q`               | Quit                                              |

**Creating a worktree:**

1. Navigate to `+ New worktree` and press `Enter`
2. Type the scope, press `Right` or `Enter` to move to feature ID
3. Press `Enter` to create

**Creating a session:**

1. Navigate to `+ New session` and press `Enter`
2. Type a session name, press `Enter`
3. Select the session and press `Enter` to launch Claude Code

**Deleting:** Press `d` on any worktree or session. An inline confirm appears — use `Left`/`Right` to select Yes/No, `Enter` to confirm.

**Safe deletion:** Worktrees with uncommitted changes or unmerged branches are blocked from deletion. A force-delete confirmation appears explaining the reason, requiring explicit opt-in.

**Settings:** Press `s` to toggle the settings panel. Use `Left`/`Right` to cycle through values for each setting. Settings apply to the next session launch.

### `cx` — Quick Launcher

```
cx
```

Clears the terminal and launches Claude Code with `--dangerously-skip-permissions` in the current directory.

## How it works

- Worktrees are discovered from git (`git worktree list --porcelain`) and stored as `scope--feature-id` directories
- Sessions are tracked in a JSON state file (`.cx-state.json`) inside the worktree directory
- Active session detection works by scanning running processes for `claude --session-id` flags
- When you launch a session, the TUI suspends and Claude Code runs in the foreground. Exiting Claude returns you to the TUI
- Session resume is automatic — first launch uses `--session-id`, subsequent launches use `--resume`

## Configuration

`cx/config.py` contains:

- `CLAUDE_FLAGS` — flags passed to Claude Code (default: `["--dangerously-skip-permissions"]`)
- Worktree directory location — defaults to `<repo-root>/.claude/worktrees/`

## Requirements

- Python 3.12+
- Git with worktree support
- Claude Code CLI (`claude`) on PATH

## License

MIT
