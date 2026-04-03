"""Git worktree operations via subprocess."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cx.config import get_repo_root, get_worktree_dir


@dataclass
class DiscoveredWorktree:
    """A worktree discovered from git worktree list."""

    path: Path
    commit: str
    branch: str | None
    is_root: bool


def validate_scope(scope: str) -> str:
    """Validate and return scope. Must be alphanumeric only."""
    if not scope:
        raise ValueError("Scope cannot be empty")
    if not re.match(r"^[a-zA-Z0-9]+$", scope):
        raise ValueError(f"Invalid scope (alphanumeric only): {scope}")
    return scope


def validate_feature_id(feature_id: str) -> str:
    """Validate and return feature ID. Alphanumeric + hyphens, no leading hyphen."""
    if not feature_id:
        raise ValueError("Feature ID cannot be empty")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$", feature_id):
        raise ValueError(
            f"Invalid feature ID (alphanumeric + hyphens, no leading hyphen): {feature_id}"
        )
    return feature_id


def discover_worktrees() -> list[DiscoveredWorktree]:
    """Discover all git worktrees via git worktree list --porcelain."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )

    repo_root = get_repo_root()
    worktrees: list[DiscoveredWorktree] = []
    current: dict[str, str] = {}

    for line in result.stdout.splitlines():
        if not line.strip():
            if current:
                path = Path(current["worktree"])
                branch_ref = current.get("branch")
                branch = (
                    branch_ref.removeprefix("refs/heads/") if branch_ref else None
                )
                worktrees.append(
                    DiscoveredWorktree(
                        path=path,
                        commit=current.get("HEAD", ""),
                        branch=branch,
                        is_root=(path == repo_root),
                    )
                )
                current = {}
        elif line.startswith("worktree "):
            current["worktree"] = line.split(" ", 1)[1]
        elif line.startswith("HEAD "):
            current["HEAD"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1]
        elif line == "detached":
            pass  # branch stays None

    # Handle last block (no trailing blank line)
    if current:
        path = Path(current["worktree"])
        branch_ref = current.get("branch")
        branch = branch_ref.removeprefix("refs/heads/") if branch_ref else None
        worktrees.append(
            DiscoveredWorktree(
                path=path,
                commit=current.get("HEAD", ""),
                branch=branch,
                is_root=(path == repo_root),
            )
        )

    return worktrees


def create_worktree(scope: str, feature_id: str) -> tuple[Path, str]:
    """Create a git worktree with scope--feature-id naming.

    Returns (worktree_path, branch_name).
    """
    scope = validate_scope(scope)
    feature_id = validate_feature_id(feature_id)

    dir_name = f"{scope}--{feature_id}"
    branch_name = f"{scope}/{feature_id}"
    wt_path = get_worktree_dir() / dir_name

    wt_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "-b", branch_name],
        check=True,
        capture_output=True,
        text=True,
    )
    return wt_path, branch_name


def remove_worktree(dir_name: str, branch: str | None = None) -> None:
    """Remove a git worktree and delete its branch."""
    wt_path = get_worktree_dir() / dir_name
    subprocess.run(
        ["git", "worktree", "remove", str(wt_path), "--force"],
        check=True,
        capture_output=True,
        text=True,
    )
    if branch:
        try:
            subprocess.run(
                ["git", "branch", "-D", branch],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            pass  # Branch may already be gone
