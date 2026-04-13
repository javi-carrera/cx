"""Git worktree operations via subprocess."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cx.config import get_repo_root, get_worktree_dir


@dataclass
class DiscoveredWorktree:
    """A worktree parsed from ``git worktree list --porcelain``."""

    path: Path
    commit: str
    branch: str | None
    is_root: bool


def validate_scope(scope: str) -> str:
    """Validate and return a branch scope."""
    if not scope:
        raise ValueError("Scope cannot be empty")
    if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", scope):
        raise ValueError(f"Invalid scope (alphanumeric + hyphens): {scope}")
    return scope


def validate_feature_id(feature_id: str) -> str:
    """Validate and return a feature ID."""
    if not feature_id:
        raise ValueError("Feature ID cannot be empty")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$", feature_id):
        raise ValueError(
            f"Invalid feature ID (alphanumeric + hyphens, no leading hyphen): {feature_id}"
        )
    return feature_id


def discover_worktrees() -> list[DiscoveredWorktree]:
    """Return all git worktrees from ``git worktree list --porcelain``."""
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

    local = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True, text=True,
    )
    remote = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{branch_name}"],
        capture_output=True, text=True,
    )

    if local.returncode == 0:
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), branch_name],
            check=True, capture_output=True, text=True,
        )
        source = "local"
    elif remote.returncode == 0:
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch_name, f"origin/{branch_name}"],
            check=True, capture_output=True, text=True,
        )
        source = "remote"
    else:
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


class BranchDeleteError(RuntimeError):
    """Raised when the worktree was removed but the branch could not be deleted."""

    def __init__(self, branch: str, stderr: str) -> None:
        super().__init__(f"Branch '{branch}' was not deleted: {stderr.strip()}")
        self.branch = branch
        self.stderr = stderr


def _is_worktree_dirty(wt_path: str) -> bool:
    """Check whether a worktree has uncommitted changes (staged or unstaged)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=wt_path,
    )
    return bool(result.stdout.strip())


def _has_sequencer_state(wt_path: str) -> bool:
    """Check whether a worktree has an in-progress Git operation."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True, text=True, cwd=wt_path,
    )
    if result.returncode != 0:
        return False

    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = Path(wt_path) / git_dir

    sequencer_paths = (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-merge",
        "rebase-apply",
        "BISECT_LOG",
    )
    return any((git_dir / path).exists() for path in sequencer_paths)


def remove_worktree(
    wt_path: str, branch: str | None = None, *, force: bool = False,
) -> str | None:
    """Remove a git worktree by its absolute path and delete its branch.

    Pre-checks for uncommitted changes and branch merge status before
    removing anything.  Pass *force=True* to skip all safety checks.
    Returns the deleted branch's short SHA when a forced branch delete
    succeeds and the SHA could be captured; otherwise returns None.
    """
    if not force:
        if _is_worktree_dirty(wt_path):
            raise DirtyWorktreeError(
                f"Worktree '{wt_path}' has uncommitted changes."
            )
        if _has_sequencer_state(wt_path):
            raise DirtyWorktreeError(
                "Worktree has an in-progress merge/rebase/cherry-pick."
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

    remove_cmd = ["git", "worktree", "remove", wt_path]
    if force:
        remove_cmd.append("--force")
    # Dirty / sequencer / unmerged-branch cases are caught by the pre-checks
    # above; any failure here is something else (path not a worktree, locked,
    # permissions, concurrent race) and should surface git's own stderr.
    subprocess.run(
        remove_cmd,
        check=True,
        capture_output=True,
        text=True,
    )

    deleted_sha: str | None = None
    if branch:
        flag = "-D" if force else "-d"
        if force:
            # Capture before deletion so the UI can show a recovery command.
            sha_result = subprocess.run(
                ["git", "rev-parse", "--short", branch],
                capture_output=True,
                text=True,
            )
            if sha_result.returncode == 0:
                deleted_sha = sha_result.stdout.strip() or None
        result = subprocess.run(
            ["git", "branch", flag, branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise BranchDeleteError(branch, result.stderr)
    return deleted_sha
