"""Codex CLI command builder and launcher."""

import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path

# Resolved once at import. See cx/claude.py for the rationale.
IS_INSTALLED: bool = shutil.which("codex") is not None

PLACEHOLDER_PREFIX = "pending-"
# rollout-YYYY-MM-DDTHH-MM-SS-<uuid>.jsonl
_ROLLOUT_NAME_RE = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-"
    r"(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"\.jsonl$"
)


def generate_placeholder_id() -> str:
    """Return a placeholder ID for a Codex session before first launch."""
    return f"{PLACEHOLDER_PREFIX}{uuid.uuid4()}"


def is_placeholder(thread_id: str) -> bool:
    """Return whether a thread ID is a pre-launch placeholder."""
    return thread_id.startswith(PLACEHOLDER_PREFIX)


def build_session_args(extra_args: list[str] | None = None) -> list[str]:
    """Build argv for a new Codex session."""
    return ["codex"] + (extra_args or [])


def build_resume_args(
    thread_id: str,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build argv for resuming a Codex session.

    `--` separates flags from the session id so an `extra_args` tail that
    ends in a flag expecting an optional value can't swallow the id.
    """
    return ["codex", "resume"] + (extra_args or []) + ["--", thread_id]


def _get_codex_home() -> Path:
    """Resolve Codex's state root ($CODEX_HOME, else ~/.codex)."""
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home)
    return Path.home() / ".codex"


def _get_codex_db() -> Path | None:
    """Resolve the Codex state database path.

    Codex honors `$CODEX_SQLITE_HOME` for the state DB root, falling
    back to `$CODEX_HOME` (then `~/.codex`) when unset. Mirror that
    resolution so cx can still find the DB on hosts where the operator
    has split rollouts and SQLite onto different paths.

    The filename is versioned (`state_5.sqlite` today), so glob for any
    `state_*.sqlite` and pick the newest one we can find.
    """
    sqlite_home_env = os.environ.get("CODEX_SQLITE_HOME")
    home = Path(sqlite_home_env) if sqlite_home_env else _get_codex_home()
    if not home.is_dir():
        return None
    candidates = sorted(home.glob("state_*.sqlite"))
    if not candidates:
        return None
    # Prefer the highest version suffix, then by mtime
    def _key(p: Path) -> tuple[int, float]:
        m = re.match(r"state_(\d+)\.sqlite$", p.name)
        version = int(m.group(1)) if m else 0
        return (version, p.stat().st_mtime)
    return sorted(candidates, key=_key, reverse=True)[0]


def _rollout_dir() -> Path:
    """Return the root directory of Codex rollout files."""
    return _get_codex_home() / "sessions"


def snapshot_rollouts() -> set[Path]:
    """Return the set of all rollout .jsonl files currently on disk.

    Callers take a snapshot before launch and diff after launch to find
    the new thread id without relying on SQLite timestamps or clock skew.
    """
    root = _rollout_dir()
    if not root.is_dir():
        return set()
    return {p for p in root.rglob("rollout-*.jsonl") if p.is_file()}


def discover_thread_id_from_rollouts(
    baseline: set[Path],
    cwd: Path | None = None,
) -> str | None:
    """Find the single new rollout file created since baseline.

    Optionally filters by the rollout's `cwd` field so unrelated Codex
    launches in other directories don't get misattributed. Returns None
    if zero or more than one candidate is found.
    """
    current = snapshot_rollouts()
    new_files = current - baseline
    if not new_files:
        return None

    candidates: list[tuple[Path, str]] = []
    for path in new_files:
        m = _ROLLOUT_NAME_RE.match(path.name)
        if not m:
            continue
        thread_id = m.group("uuid")
        if cwd is not None and not _rollout_cwd_matches(path, cwd):
            continue
        candidates.append((path, thread_id))

    if len(candidates) == 1:
        return candidates[0][1]
    # Zero or more than one: ambiguous. Picking the newest under a race
    # could mis-bind an unrelated concurrent Codex session to this cx
    # placeholder, so refuse instead and let the caller surface it.
    return None


def _rollout_cwd_matches(path: Path, cwd: Path) -> bool:
    """Check whether a rollout file's first SessionMeta event matches cwd.

    Rollouts begin with a single-line SessionMeta JSON object that
    includes the cwd the session was started in.
    """
    import json
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    return False
                # Codex writes SessionMeta on the first non-empty line; schema
                # across versions has used either top-level `cwd` or nested
                # payload — check both conservatively.
                meta_cwd = obj.get("cwd")
                if meta_cwd is None and isinstance(obj.get("payload"), dict):
                    meta_cwd = obj["payload"].get("cwd")
                if meta_cwd is None:
                    return False
                try:
                    return Path(meta_cwd).resolve() == cwd.resolve()
                except OSError:
                    return False
        return False
    except OSError:
        return False


def discover_thread_id_from_db(
    cwd: Path,
    after_timestamp: int,
    exclude_ids: set[str] | None = None,
) -> str | None:
    """Fallback: query Codex's SQLite index for a recently-created thread.

    Only used when the rollout-file snapshot approach can't find a match,
    e.g. because $CODEX_HOME/sessions is unreadable.
    """
    db_path = _get_codex_db()
    if not db_path:
        return None

    resolved_cwd = str(cwd.resolve())
    exclude_ids = exclude_ids or set()

    placeholders = ",".join("?" * len(exclude_ids)) if exclude_ids else ""
    where_exclude = f" AND id NOT IN ({placeholders})" if placeholders else ""
    query = (
        "SELECT id FROM threads "
        f"WHERE cwd = ? AND created_at >= ? AND source = 'cli'{where_exclude} "
        "ORDER BY created_at DESC LIMIT 1"
    )
    params = (resolved_cwd, after_timestamp, *exclude_ids)

    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, timeout=2
        )
    except sqlite3.OperationalError:
        return None
    try:
        row = conn.execute(query, params).fetchone()
        return row[0] if row else None
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()


def prune_dead_pids(pids: set[int]) -> set[int]:
    """Return the subset of PIDs currently alive."""
    alive: set[int] = set()
    for pid in pids:
        if pid <= 0:
            continue
        try:
            if Path(f"/proc/{pid}").exists():
                alive.add(pid)
        except OSError:
            continue
    return alive


def run_codex(args: list[str], cwd: Path) -> int:
    """Run Codex CLI in the given directory.

    Returns the exit code.
    """
    return subprocess.run(args, cwd=cwd).returncode
