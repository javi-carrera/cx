"""Claude Code command builder and launcher."""

import subprocess
import uuid
from pathlib import Path


def generate_session_id() -> str:
    """Generate a new UUID for a Claude Code session."""
    return str(uuid.uuid4())


def build_session_args(
    session_id: str,
    name: str | None = None,
    extra_args: list[str] | None = None,
    resume: bool = False,
) -> list[str]:
    """Build argv list for a Claude Code session.

    extra_args are inserted before the session flag (e.g. settings flags).
    Uses --resume for previously launched sessions, --session-id for new ones.
    """
    if resume:
        args = ["claude"] + (extra_args or []) + ["--resume", session_id]
    else:
        args = ["claude"] + (extra_args or []) + ["--session-id", session_id]
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
