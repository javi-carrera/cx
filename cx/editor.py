"""Editor launcher for opening a worktree in Cursor or VSCode."""

import shutil
import subprocess
from pathlib import Path

_CANDIDATES = ("cursor", "code")


def find_editor() -> str | None:
    """Return the first available editor binary, or None."""
    for binary in _CANDIDATES:
        if shutil.which(binary):
            return binary
    return None


def open_in_editor(path: Path) -> str:
    """Open ``path`` in an available editor, detached from cx.

    Returns the binary name used. Raises FileNotFoundError if neither
    Cursor nor VSCode is on PATH.
    """
    editor = find_editor()
    if editor is None:
        raise FileNotFoundError(
            f"No editor found on PATH (tried: {', '.join(_CANDIDATES)})"
        )
    # start_new_session detaches from cx's process group so the GUI
    # editor survives cx exit and doesn't receive cx's signals.
    subprocess.Popen(
        [editor, str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return editor
