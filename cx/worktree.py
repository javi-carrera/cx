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
    """Validate and return scope. Alphanumeric + hyphens, no leading/trailing hyphen."""
    if not scope:
        raise ValueError("Scope cannot be empty")
    if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", scope):
        raise ValueError(f"Invalid scope (alphanumeric + hyphens): {scope}")
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


def create_worktree(scope: str, feature_id: str) -> tuple[Path, str, str]:
    """Create a git worktree with scope--feature-id naming.

    Returns (worktree_path, branch_name, source) where source is
    "local", "remote", or "new".
    """
    scope = validate_scope(scope)
    feature_id = validate_feature_id(feature_id)

    dir_name = f"{scope}--{feature_id}"
    branch_name = f"{scope}/{feature_id}"
    wt_path = get_worktree_dir() / dir_name

    wt_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if branch already exists locally or on remote
    local = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True, text=True,
    )
    remote = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{branch_name}"],
        capture_output=True, text=True,
    )

    if local.returncode == 0:
        # Branch exists locally — check out into worktree
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), branch_name],
            check=True, capture_output=True, text=True,
        )
        source = "local"
    elif remote.returncode == 0:
        # Branch exists on remote — create local tracking branch
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch_name, f"origin/{branch_name}"],
            check=True, capture_output=True, text=True,
        )
        source = "remote"
    else:
        # New branch
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch_name],
            check=True, capture_output=True, text=True,
        )
        source = "new"

    return wt_path, branch_name, source


def _is_branch_merged(branch: str) -> bool:
    """Check whether a branch is merged into its upstream or HEAD."""
    # Try upstream first (what git branch -d checks)
    upstream = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
        capture_output=True,
        text=True,
    )
    target = upstream.stdout.strip() if upstream.returncode == 0 else "HEAD"
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch, target],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


class BranchNotMergedError(RuntimeError):
    """Raised when a branch deletion is blocked because it is not fully merged."""


class DirtyWorktreeError(RuntimeError):
    """Raised when a worktree has uncommitted changes."""


def _is_worktree_dirty(wt_path: str) -> bool:
    """Check whether a worktree has uncommitted changes (staged or unstaged)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=wt_path,
    )
    return bool(result.stdout.strip())


def remove_worktree(
    wt_path: str, branch: str | None = None, *, force: bool = False,
) -> None:
    """Remove a git worktree by its absolute path and delete its branch.

    Pre-checks for uncommitted changes and branch merge status before
    removing anything.  Pass *force=True* to skip all safety checks.
    """
    if not force:
        if _is_worktree_dirty(wt_path):
            raise DirtyWorktreeError(
                f"Worktree '{wt_path}' has uncommitted changes."
            )
        if branch:
            exists = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                capture_output=True,
                text=True,
            )
            if exists.returncode == 0 and not _is_branch_merged(branch):
                raise BranchNotMergedError(
                    f"Branch '{branch}' is not fully merged."
                )

    subprocess.run(
        ["git", "worktree", "remove", wt_path, "--force"],
        check=True,
        capture_output=True,
        text=True,
    )
    if branch:
        flag = "-D" if force else "-d"
        subprocess.run(
            ["git", "branch", flag, branch],
            capture_output=True,
            text=True,
        )
