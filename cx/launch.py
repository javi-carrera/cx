"""cx — fire-and-forget Claude Code launcher."""

import os
import sys


def main() -> None:
    """Launch Claude Code in the current directory with bypass permissions."""
    try:
        os.system("clear")
        os.execvp("claude", ["claude", "--dangerously-skip-permissions"])
    except FileNotFoundError:
        print("Error: 'claude' not found on PATH", file=sys.stderr)
        sys.exit(1)
