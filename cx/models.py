"""Pydantic models for cx state."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class SessionEntry(BaseModel):
    """A Claude Code session within a worktree.

    Claude active-detection is driven by Claude's own per-PID registry
    under `$CLAUDE_CONFIG_DIR/sessions/*.json` (see :mod:`cx.claude`),
    so cx does not need to store a PID here. Older state files that
    happen to carry an `active_pid` field load fine — Pydantic's
    default extra-field policy ignores it.
    """

    session_id: str
    name: str
    created_at: datetime
    last_accessed: datetime


class CodexSessionEntry(BaseModel):
    """A Codex CLI session within a worktree."""

    thread_id: str  # "pending-<uuid>" until first launch, then real Codex thread UUID
    name: str
    created_at: datetime
    last_accessed: datetime
    # PID of the cx process that owns the currently-running launch.
    # cx runs its Codex child synchronously under App.suspend(), so the
    # owner cx's /proc entry is a reliable liveness marker — if cx dies
    # during the suspend, the entry disappears and the dot naturally
    # clears via prune_dead_pids. Not the child Codex pid.
    owner_pid: int | None = None


class WorktreeEntry(BaseModel):
    """A git worktree with associated sessions."""

    path: Path
    branch: str
    base_branch: str
    sessions: list[SessionEntry] = []
    codex_sessions: list[CodexSessionEntry] = []
    created_at: datetime


class CxState(BaseModel):
    """Root state object stored in .cx-state.json."""

    version: int = 3
    worktrees: dict[str, WorktreeEntry] = {}
