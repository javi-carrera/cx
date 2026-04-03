"""cxx — Textual TUI for Claude Code worktree and session management."""

from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Static

from cx import claude, state, worktree as wt_mod
from cx.models import SessionEntry, WorktreeEntry
from cx.widgets.session_panel import SessionPanel
from cx.widgets.status_bar import StatusBar
from cx.widgets.worktree_panel import WorktreeDeselected, WorktreeHighlighted, WorktreePanel


class CxxApp(App):
    """Claude Code worktree & session manager."""

    CSS_PATH = "styles.tcss"
    TITLE = "cx"
    ENABLE_COMMAND_PALETTE = False
    NOTIFICATION_TIMEOUT = 3

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("tab", "focus_next", "Switch Panel", show=True),
        Binding("shift+tab", "focus_previous", show=False),
        Binding("left", "focus_worktrees", "← Worktrees", show=False),
        Binding("right", "focus_sessions", "→ Sessions", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Claude Code Worktree Manager[/]",
            id="title-bar",
        )
        with Horizontal(id="panels"):
            yield WorktreePanel()
            yield SessionPanel()
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._update_panel_height()
        # Focus the worktree list
        try:
            wt_list = self.query_one("#worktree-list")
            wt_list.focus()
        except Exception:
            pass

    def _update_panel_height(self) -> None:
        """Set #panels height to fit the currently visible lists."""
        wt = self.query_one(WorktreePanel).content_height()
        session = self.query_one(SessionPanel).content_height()
        max_items = max(wt, session, 1)
        # +2 for panel border (top + bottom)
        self.query_one("#panels").styles.height = max_items + 2

    def action_focus_worktrees(self) -> None:
        self.query_one("#worktree-list").focus()

    def action_focus_sessions(self) -> None:
        self.query_one("#session-list").focus()

    # --- Worktree events ---

    def on_worktree_deselected(self, event: WorktreeDeselected) -> None:
        """Clear session panel and status bar when no worktree is selected."""
        self.query_one(SessionPanel).clear_sessions()
        self.query_one(StatusBar).update(" Select a worktree")
        self._update_panel_height()

    def on_worktree_highlighted(self, event: WorktreeHighlighted) -> None:
        """Update session panel and status bar when worktree selection changes."""
        session_panel = self.query_one(SessionPanel)
        status_bar = self.query_one(StatusBar)

        session_panel.update_sessions(event.wt_name, event.path)
        status_bar.refresh_status(event.branch, event.path)
        self._update_panel_height()

    def on_worktree_panel_new_worktree_requested(
        self, event: WorktreePanel.NewWorktreeRequested
    ) -> None:
        """Create a new worktree from inline input."""
        try:
            wt_path, branch_name = wt_mod.create_worktree(event.scope, event.feature_id)
        except Exception as e:
            self.notify(f"Failed to create worktree: {e}", severity="error")
            return

        dir_name = f"{event.scope}--{event.feature_id}"
        now = datetime.now(timezone.utc)

        with state.modify_state() as s:
            s.worktrees[dir_name] = WorktreeEntry(
                path=wt_path,
                branch=branch_name,
                base_branch="dev",
                created_at=now,
            )

        self.query_one(WorktreePanel).refresh_worktrees()
        self._update_panel_height()
        self.notify(f"Created worktree: {dir_name}")

    def on_worktree_panel_delete_worktree_confirmed(
        self, event: WorktreePanel.DeleteWorktreeConfirmed
    ) -> None:
        """Delete a worktree after inline confirmation."""
        try:
            wt_mod.remove_worktree(event.wt_name, event.branch)
        except Exception as e:
            self.notify(f"Failed to remove worktree: {e}", severity="error")
            return

        with state.modify_state() as s:
            s.worktrees.pop(event.wt_name, None)

        self.query_one(WorktreePanel).refresh_worktrees()
        self._update_panel_height()
        self.notify(f"Deleted worktree: {event.wt_name}")

    # --- Session events ---

    def on_session_panel_new_session_requested(
        self, event: SessionPanel.NewSessionRequested
    ) -> None:
        """Create a new session and refresh the list."""
        session_id = claude.generate_session_id()
        now = datetime.now(timezone.utc)

        with state.modify_state() as s:
            if event.wt_name not in s.worktrees:
                s.worktrees[event.wt_name] = WorktreeEntry(
                    path=event.wt_path,
                    branch=event.wt_name,
                    base_branch="dev",
                    created_at=now,
                )
            s.worktrees[event.wt_name].sessions.append(
                SessionEntry(
                    session_id=session_id,
                    name=event.name,
                    created_at=now,
                    last_accessed=now,
                )
            )

        session_panel = self.query_one(SessionPanel)
        session_panel.update_sessions(event.wt_name, event.wt_path)
        self._update_panel_height()
        self.notify(f"Created session: {event.name}")

    def on_session_panel_launch_session_requested(
        self, event: SessionPanel.LaunchSessionRequested
    ) -> None:
        """Launch/resume a Claude Code session, then return to TUI."""
        with state.modify_state() as s:
            for wt in s.worktrees.values():
                for session in wt.sessions:
                    if session.session_id == event.session_id:
                        session.last_accessed = datetime.now(timezone.utc)
                        break

        args = claude.build_resume_args(event.session_id, name=event.session_name)
        with self.suspend():
            import os
            os.system("clear")
            claude.run_claude(args, event.wt_path)

        # Refresh session panel to update active indicators
        session_panel = self.query_one(SessionPanel)
        if session_panel._current_wt_name and session_panel._current_wt_path:
            session_panel.update_sessions(
                session_panel._current_wt_name,
                session_panel._current_wt_path,
            )

    def on_session_panel_delete_session_confirmed(
        self, event: SessionPanel.DeleteSessionConfirmed
    ) -> None:
        """Soft-delete a session after inline confirmation."""
        with state.modify_state() as s:
            wt = s.worktrees.get(event.wt_name)
            if wt:
                wt.sessions = [ss for ss in wt.sessions if ss.name != event.session_name]

        session_panel = self.query_one(SessionPanel)
        if session_panel._current_wt_name and session_panel._current_wt_path:
            session_panel.update_sessions(
                session_panel._current_wt_name,
                session_panel._current_wt_path,
            )
        self._update_panel_height()
        self.notify(f"Removed session: {event.session_name}")


def main() -> None:
    """Entry point for cxx."""
    app = CxxApp()
    app.run()
