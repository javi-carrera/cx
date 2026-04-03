"""Async git queries for TUI status display."""

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorktreeStatus:
    """Detailed git status for a worktree."""

    staged: int = 0
    unstaged: int = 0
    untracked: int = 0
    ahead: int = 0
    behind: int = 0
    branch: str = ""
    tracking: str = ""
    last_commit: str = ""

    @property
    def dirty(self) -> int:
        return self.staged + self.unstaged + self.untracked


async def get_file_status(path: Path) -> tuple[int, int, int]:
    """Count staged, unstaged, and untracked files."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(path), "status", "--porcelain",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    lines = stdout.decode().strip().splitlines()

    staged = 0
    unstaged = 0
    untracked = 0

    for line in lines:
        if len(line) < 2:
            continue
        x, y = line[0], line[1]
        if x == "?" and y == "?":
            untracked += 1
        elif x == "!" and y == "!":
            continue  # ignored files
        else:
            if x not in (" ", "?", "!"):
                staged += 1
            if y not in (" ", "?", "!"):
                unstaged += 1

    return staged, unstaged, untracked


async def get_ahead_behind(path: Path) -> tuple[int, int]:
    """Get commits ahead/behind upstream. Returns (0, 0) if no upstream."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(path),
        "rev-list", "--left-right", "--count", "HEAD...@{upstream}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return (0, 0)
    parts = stdout.decode().strip().split("\t")
    if len(parts) == 2:
        return (int(parts[0]), int(parts[1]))
    return (0, 0)


async def get_last_commit(path: Path) -> str:
    """Get the short last commit message."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(path), "log", "-1", "--format=%s",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return ""
    msg = stdout.decode().strip()
    if len(msg) > 60:
        return msg[:57] + "..."
    return msg


async def get_tracking_branch(path: Path) -> str:
    """Get the upstream tracking branch name. Empty if none."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(path),
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return ""
    return stdout.decode().strip()


async def get_worktree_status(path: Path) -> WorktreeStatus:
    """Get combined status for a worktree."""
    (staged, unstaged, untracked), (ahead, behind), tracking, last_commit = (
        await asyncio.gather(
            get_file_status(path),
            get_ahead_behind(path),
            get_tracking_branch(path),
            get_last_commit(path),
        )
    )
    return WorktreeStatus(
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        ahead=ahead,
        behind=behind,
        tracking=tracking,
        last_commit=last_commit,
    )
