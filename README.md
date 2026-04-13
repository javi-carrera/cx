# cx

A terminal UI for managing Claude Code and Codex CLI sessions across git worktrees.

If you juggle multiple git worktrees and run Claude Code and/or Codex in several of them, `cx` gives you a single keyboard-driven place to create, browse, launch, and manage them all.

## Installation

`cx` is designed to be installed **globally** with [uv](https://docs.astral.sh/uv/) and run from inside any git repository.

```bash
uv tool install git+https://github.com/javi-carrera/cx.git
```

From a local checkout:

```bash
uv tool install /path/to/cx
```

Reinstall after local edits with `uv tool install --force --reinstall /path/to/cx`. Upgrade with `uv tool upgrade cx`. Remove with `uv tool uninstall cx`.

## Requirements

- Python 3.12+
- Git with worktree support
- A terminal supported by [Textual](https://textual.textualize.io/)
- At least one of:
  - [Claude Code CLI](https://github.com/anthropics/claude-code) (`claude` on `PATH`)
  - [OpenAI Codex CLI](https://github.com/openai/codex) (`codex` on `PATH`)

cx is developed and tested on Linux.

## Usage

Run `cx` from any directory inside a git repository:

```bash
cx
```

cx opens a keyboard-driven TUI with a **Worktrees** panel on top, **Claude Code Sessions** on the bottom left, **Codex Sessions** on the bottom right, a git-aware **status bar**, and toggleable **settings** panels for each column. If only one CLI is installed, the other column becomes inert.

### Keybindings

| Key | Action |
| --- | --- |
| `Tab` / `Shift+Tab` | Cycle between Worktrees and Sessions |
| `Left` / `Right` | Switch Claude/Codex columns, or cycle setting values when settings are focused |
| `Up` / `Down` | Navigate items |
| `Enter` | Select / launch |
| `d` | Delete highlighted worktree or session |
| `r` | Rename highlighted session |
| `s` | Toggle the settings panel for the focused column |
| `Escape` | Cancel the current action |
| `q` | Quit |

### Worktrees

Highlight `+ New worktree`, enter a scope (`Right` or `Tab` to move to the feature ID), and press `Enter`. cx names the worktree `scope--feature-id` and the branch `scope/feature-id`. If a matching local branch exists, it is checked out; if a local `origin/<branch>` ref exists (from a prior fetch), cx branches from it; otherwise cx creates a new branch. cx never fetches from the remote — run `git fetch` first if you want upstream branches considered.

Press `d` to delete a worktree. Worktrees with uncommitted changes, unmerged branches, or an in-progress merge / rebase / cherry-pick are blocked from deletion — a force-delete prompt appears explaining why. A force-delete notification includes the pre-delete branch SHA so you can recover via `git branch <name> <sha>` or `git reflog`. Root worktrees cannot be deleted.

### Sessions

Highlight `+ New session` in either column, enter a name (letters, digits, spaces, underscores, and hyphens; must start with a letter or digit), and press `Enter`. Highlight the session and press `Enter` again to launch — cx suspends and hands you a clean terminal with Claude Code or Codex running. Exit the CLI (`Ctrl+D`, `exit`, etc.) to return to cx. Subsequent launches resume the same conversation.

Sessions are listed most-recently-used first. Active sessions show a green indicator and cannot be relaunched, renamed, or deleted while running. If a launch fails (for example because the CLI binary is missing), cx surfaces a notification and returns cleanly to the TUI.

### Settings

Press `s` from a session column to open its settings panel. Use `Left` / `Right` to cycle the highlighted value. Settings apply to the next launch.

**Claude Code**

| Setting | Values |
| --- | --- |
| Permission mode | `plan`, `dontAsk`, `default`, `acceptEdits`, `auto`, `bypassPermissions` |
| Model | `haiku`, `sonnet`, `opus` |
| Context | `200k`, `1M` |
| Effort | `low`, `medium`, `high`, `max` |
| Verbose | `OFF`, `ON` |
| Debug | `OFF`, `ON` |

**Codex**

| Setting | Values |
| --- | --- |
| Approval | `untrusted`, `on-request`, `never`, `full-auto`, `bypass` |
| Sandbox | `read-only`, `workspace-write`, `danger-full-access` |
| Model | `gpt-5.2`, `gpt-5.3-codex`, `gpt-5.4-mini`, `gpt-5.4` |
| Reasoning | `minimal`, `low`, `medium`, `high`, `xhigh` |
| Search | `OFF`, `ON` |

Codex `Approval = bypass` disables the sandbox entirely; `full-auto` implies `workspace-write`; the Sandbox setting only applies for the other approval modes. `Search = ON` combined with `Reasoning = minimal` is rejected by the Codex API, so cx drops `--search` for that launch and shows a warning.

### Status bar

The bar at the top shows the selected worktree's branch, ahead/behind counts, staged/unstaged/untracked file counts, and last commit message.

## Claude Code status line

This repository also ships `status-line/status_line.py` — a standalone script that adds a rich status line to Claude Code with Unicode progress bars. It shows the current directory and session name, the context window usage (with progress bar and token counts), and the 5-hour rate-limit usage with countdown to reset. No dependencies beyond the Python 3 standard library.

To install it:

1. Copy `status-line/status_line.py` somewhere on your machine.
2. Add the following to your Claude Code `~/.claude/settings.json`:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "python3 /path/to/status_line.py"
     }
   }
   ```

## License

MIT. See [`LICENSE`](LICENSE).
