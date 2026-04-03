"""Pydantic models for cx state."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class SessionEntry(BaseModel):
    """A Claude Code session within a worktree."""

    session_id: str
    name: str
    created_at: datetime
    last_accessed: datetime


class WorktreeEntry(BaseModel):
    """A git worktree with associated Claude Code sessions."""

    path: Path
    branch: str
    base_branch: str
    sessions: list[SessionEntry] = []
    created_at: datetime


class CxState(BaseModel):
    """Root state object stored in .cx-state.json (v2)."""

    version: int = 2
    worktrees: dict[str, WorktreeEntry] = {}
