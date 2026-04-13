"""Atomic JSON state file management with v1→v3 migration."""

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from pydantic import ValidationError

from cx.config import get_state_file
from cx.models import CxState


# Set by load_state() when it quarantines a corrupt file. Consumed once
# by the app on startup to surface a notification, then cleared.
_last_quarantine: tuple[Path, Path, Exception] | None = None


def take_quarantine_notice() -> tuple[Path, Path, Exception] | None:
    """Return and clear the last quarantine notice, if any.

    The app calls this once on startup so it can show a notification
    about recovered-from-corruption state.
    """
    global _last_quarantine
    notice = _last_quarantine
    _last_quarantine = None
    return notice


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


def _migrate_v2_to_v3(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate v2 state to v3 (add codex_sessions to worktrees)."""
    raw["version"] = 3
    for wt in raw.get("worktrees", {}).values():
        wt.setdefault("codex_sessions", [])
    return raw


def _parse_state(raw: dict[str, Any]) -> CxState:
    """Parse raw state into ``CxState``, running migrations in memory."""
    version = raw.get("version", 1)
    if version < 2:
        raw = _migrate_v1_to_v2(raw)
    if raw.get("version", 2) < 3:
        raw = _migrate_v2_to_v3(raw)
    return CxState.model_validate(raw)


def load_state(path: Path | None = None) -> CxState:
    """Load state from disk. Migrates v1→v3 automatically.

    This is strictly read-only — migrated state is returned in memory
    but never written back here. Persistence happens naturally on the
    next :func:`modify_state` call, which holds the flock. Writing from
    here would require either re-entering the flock (deadlock) or
    racing outside it (can clobber concurrent cx updates).

    On corruption, the bad file is quarantined and a fresh empty state
    is returned instead of raising — that keeps the TUI usable even when
    one hot-reload accidentally wrote garbage. The last quarantine is
    recorded for :func:`take_quarantine_notice` so the app can notify.
    """
    global _last_quarantine
    path = path or get_state_file()
    if not path.exists():
        return CxState()

    try:
        raw = json.loads(path.read_text())
        state = _parse_state(raw)
    except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as e:
        backup = path.with_suffix(f".corrupt-{int(time.time())}.json")
        try:
            path.rename(backup)
        except OSError:
            backup = path  # couldn't move it; note the failure anyway
        _last_quarantine = (path, backup, e)
        return CxState()

    return state


def save_state(state: CxState, path: Path | None = None) -> None:
    """Write state to disk atomically."""
    path = path or get_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique tmp name so concurrent writers don't stomp each other's temp file
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(state.model_dump_json(indent=2))
    os.replace(tmp, path)


@contextmanager
def modify_state(path: Path | None = None) -> Generator[CxState, None, None]:
    """Read-modify-write with an inter-process lock.

    Holds an exclusive flock on a sibling `.lock` file for the whole
    read→yield→save cycle so concurrent cx instances can't lose each
    other's updates.
    """
    path = path or get_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            state = load_state(path)
            yield state
            save_state(state, path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
