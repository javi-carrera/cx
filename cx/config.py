"""Constants and path resolution for cx."""

import subprocess
from pathlib import Path


def get_repo_root() -> Path:
    """Return the main repository root, not the current worktree root."""
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    # --git-common-dir returns e.g. /workspace/.git → parent is repo root
    return Path(result.stdout.strip()).parent


def get_worktree_dir() -> Path:
    """Get the directory where worktrees are stored.

    Historically this was `.claude/worktrees/`, back when cx was Claude-
    only. Now that cx manages Codex sessions too, the `.claude/` scoping
    is semantically wrong — worktrees aren't Claude-specific anymore.
    Existing worktrees at the old path remain fully usable because
    discovery is driven by `git worktree list --porcelain` and is path-
    agnostic; they phase out naturally as branches merge.
    """
    return get_repo_root() / ".worktrees"


def get_state_file() -> Path:
    """Return the cx state file path."""
    return get_worktree_dir() / ".cx-state.json"


def get_current_branch() -> str:
    """Return the currently checked-out branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
