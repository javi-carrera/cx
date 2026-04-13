"""Claude Code command builder and launcher."""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

# Resolved once at import. If `claude` is installed mid-session, the user
# needs to restart cx — a reasonable trade for not re-running `which` on
# every keystroke / panel repaint.
IS_INSTALLED: bool = shutil.which("claude") is not None


def generate_session_id() -> str:
    """Return a new Claude Code session UUID."""
    return str(uuid.uuid4())


def build_session_args(
    session_id: str,
    name: str | None = None,
    extra_args: list[str] | None = None,
    resume: bool = False,
) -> list[str]:
    """Build argv for launching or resuming a Claude Code session.

    ``extra_args`` are inserted before the session flag.
    """
    if resume:
        args = ["claude"] + (extra_args or []) + ["--resume", session_id]
    else:
        args = ["claude"] + (extra_args or []) + ["--session-id", session_id]
    if name:
        args.extend(["--name", name])
    return args


def _claude_sessions_dir() -> Path:
    """Return $CLAUDE_CONFIG_DIR/sessions (claude's own pid-keyed registry)."""
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    return config_dir / "sessions"


def _pid_alive(pid: int) -> bool:
    """Return whether a process exists in /proc."""
    if pid <= 0:
        return False
    try:
        return Path(f"/proc/{pid}").exists()
    except OSError:
        return False


def get_active_session_ids() -> set[str]:
    """Return session IDs of currently running Claude Code sessions.

    Reads $CLAUDE_CONFIG_DIR/sessions/*.json — each file is keyed by PID
    and contains a sessionId for the running session. Files whose PID is
    no longer alive are treated as stale and ignored, so an abnormal
    exit can't leave a permanent false "active" dot.
    """
    sessions_dir = _claude_sessions_dir()
    if not sessions_dir.is_dir():
        return set()

    active: set[str] = set()
    try:
        for entry in sessions_dir.iterdir():
            if entry.suffix != ".json":
                continue
            try:
                pid = int(entry.stem)
            except ValueError:
                pid = -1
            if pid > 0 and not _pid_alive(pid):
                continue
            try:
                data = json.loads(entry.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            # Belt-and-suspenders: also check the pid stored inside the file.
            file_pid = data.get("pid")
            if isinstance(file_pid, int) and not _pid_alive(file_pid):
                continue
            sid = data.get("sessionId")
            if sid:
                active.add(sid)
    except OSError:
        pass
    return active


def run_claude(args: list[str], cwd: Path) -> int:
    """Run Claude Code in the given directory.

    Returns the exit code.
    """
    return subprocess.run(args, cwd=cwd).returncode


def session_has_history(session_id: str) -> bool:
    """Return whether a Claude Code session has history on disk."""
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    projects_dir = config_dir / "projects"
    if not projects_dir.is_dir():
        return False
    for project in projects_dir.iterdir():
        session_file = project / f"{session_id}.jsonl"
        if session_file.exists():
            return True
    return False
