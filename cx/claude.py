"""Claude Code command builder and launcher."""

import subprocess
import uuid
from pathlib import Path

from cx.config import CLAUDE_FLAGS


def generate_session_id() -> str:
    """Generate a new UUID for a Claude Code session."""
    return str(uuid.uuid4())


def build_launch_args(session_id: str, name: str | None = None) -> list[str]:
    """Build argv list for launching a new Claude Code session."""
    args = ["claude"] + CLAUDE_FLAGS + ["--session-id", session_id]
    if name:
        args.extend(["--name", name])
    return args


def build_resume_args(session_id: str, name: str | None = None) -> list[str]:
    """Build argv list for resuming an existing Claude Code session.

    Uses --session-id instead of --resume so that stale session IDs
    start a new conversation rather than failing.
    """
    args = ["claude"] + CLAUDE_FLAGS + ["--session-id", session_id]
    if name:
        args.extend(["--name", name])
    return args


def get_active_session_ids() -> set[str]:
    """Return session IDs of currently running Claude Code processes."""
    import re

    try:
        result = subprocess.run(
            ["ps", "ax", "-o", "args"],
            capture_output=True,
            text=True,
        )
        active = set()
        pattern = re.compile(r"(?:--session-id|--resume)\s+([0-9a-f-]{36})")
        for line in result.stdout.splitlines():
            if "claude" in line:
                m = pattern.search(line)
                if m:
                    active.add(m.group(1))
        return active
    except Exception:
        return set()


def run_claude(args: list[str], cwd: Path) -> int:
    """Run Claude Code as a subprocess in the given directory.

    Returns the exit code.
    """
    return subprocess.run(args, cwd=cwd).returncode
