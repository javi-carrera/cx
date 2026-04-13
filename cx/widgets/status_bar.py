"""Status bar for the selected worktree's git status."""

from pathlib import Path

from textual import work
from textual.widgets import Static

from cx import git
from cx.colors import ACCENT, CYAN, GREEN, RED, YELLOW


class StatusBar(Static):
    """Git status display for the selected worktree."""

    def on_mount(self) -> None:
        self.border_title = "Status"
        self.update(" Select a worktree")

    def refresh_status(self, branch: str | None, path: Path) -> None:
        """Refresh status for the given worktree."""
        display_branch = branch or "detached"
        self.update(f" {display_branch} │ ...")
        self._fetch_status(display_branch, path)

    @work(exclusive=True, group="status-bar")
    async def _fetch_status(self, branch: str, path: Path) -> None:
        """Fetch and render git status."""
        status = await git.get_worktree_status(path)

        parts = [f" [{ACCENT}]{branch}[/]"]

        if status.ahead > 0 or status.behind > 0:
            ab = []
            if status.ahead > 0:
                ab.append(f"[{YELLOW}]↑{status.ahead}[/]")
            if status.behind > 0:
                ab.append(f"[{RED}]↓{status.behind}[/]")
            parts.append(" ".join(ab))

        file_parts = []
        if status.staged > 0:
            file_parts.append(f"[{GREEN}]+{status.staged}[/]")
        if status.unstaged > 0:
            file_parts.append(f"[{YELLOW}]~{status.unstaged}[/]")
        if status.untracked > 0:
            file_parts.append(f"[{CYAN}]?{status.untracked}[/]")
        if file_parts:
            parts.append(" ".join(file_parts))
        else:
            parts.append(f"[{GREEN}]clean[/]")

        if status.last_commit:
            parts.append(f"[dim]{status.last_commit}[/]")

        self.update(" │ ".join(parts))
