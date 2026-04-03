"""Status bar — bottom of the TUI showing git info for selected worktree."""

from pathlib import Path

from textual import work
from textual.widgets import Static

from cx import git


class StatusBar(Static):
    """Displays git status for the currently selected worktree."""

    def on_mount(self) -> None:
        self.border_title = "Status"
        self.update(" Select a worktree")

    def refresh_status(self, branch: str | None, path: Path) -> None:
        """Refresh status bar for the given worktree."""
        display_branch = branch or "detached"
        self.update(f" {display_branch} │ ...")
        self._fetch_status(display_branch, path)

    @work(exclusive=True, group="status-bar")
    async def _fetch_status(self, branch: str, path: Path) -> None:
        """Fetch and display git status."""
        status = await git.get_worktree_status(path)

        parts = [f" [bold #DA7756]{branch}[/]"]

        # Ahead/behind
        if status.ahead > 0 or status.behind > 0:
            ab = []
            if status.ahead > 0:
                ab.append(f"[#e5c07b]↑{status.ahead}[/]")
            if status.behind > 0:
                ab.append(f"[#e06c75]↓{status.behind}[/]")
            parts.append(" ".join(ab))

        # File status — compact symbols
        file_parts = []
        if status.staged > 0:
            file_parts.append(f"[#98c379]+{status.staged}[/]")
        if status.unstaged > 0:
            file_parts.append(f"[#e5c07b]~{status.unstaged}[/]")
        if status.untracked > 0:
            file_parts.append(f"[#56b6c2]?{status.untracked}[/]")
        if file_parts:
            parts.append(" ".join(file_parts))
        else:
            parts.append("[#98c379]clean[/]")

        # Last commit
        if status.last_commit:
            parts.append(f"[dim]{status.last_commit}[/]")

        self.update(" │ ".join(parts))
