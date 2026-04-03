"""Constants and path resolution for cx."""

import subprocess
from pathlib import Path

CLAUDE_FLAGS = ["--dangerously-skip-permissions"]


def get_repo_root() -> Path:
    """Get the main repository root (not worktree root)."""
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    # --git-common-dir returns e.g. /workspace/.git → parent is repo root
    return Path(result.stdout.strip()).parent


def get_worktree_dir() -> Path:
    """Get the directory where worktrees are stored."""
    return get_repo_root() / ".claude" / "worktrees"


def get_state_file() -> Path:
    """Get the path to the state file."""
    return get_worktree_dir() / ".cx-state.json"


def get_current_branch() -> str:
    """Get the name of the currently checked-out branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
