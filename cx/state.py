"""Atomic JSON state file management with v1→v2 migration."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from cx.config import get_state_file
from cx.models import CxState, SessionEntry, WorktreeEntry


def _migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate v1 state (flat sessions dict) to v2 (worktrees with sessions)."""
    worktrees: dict[str, Any] = {}
    for name, entry in raw.get("sessions", {}).items():
        worktrees[name] = {
            "path": entry["worktree_path"],
            "branch": entry["branch"],
            "base_branch": entry["base_branch"],
            "created_at": entry["created_at"],
            "sessions": [
                {
                    "session_id": entry["claude_session_id"],
                    "name": name,
                    "created_at": entry["created_at"],
                    "last_accessed": entry["last_accessed"],
                }
            ],
        }
    return {"version": 2, "worktrees": worktrees}


def load_state(path: Path | None = None) -> CxState:
    """Load state from disk. Migrates v1→v2 automatically."""
    path = path or get_state_file()
    if not path.exists():
        return CxState()

    raw = json.loads(path.read_text())

    if raw.get("version", 1) < 2:
        raw = _migrate_v1_to_v2(raw)
        state = CxState.model_validate(raw)
        save_state(state, path)
        return state

    return CxState.model_validate(raw)


def save_state(state: CxState, path: Path | None = None) -> None:
    """Atomically save state to disk."""
    path = path or get_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(state.model_dump_json(indent=2))
    os.replace(tmp, path)


@contextmanager
def modify_state(path: Path | None = None) -> Generator[CxState, None, None]:
    """Context manager for read-modify-write on state file."""
    path = path or get_state_file()
    state = load_state(path)
    yield state
    save_state(state, path)
