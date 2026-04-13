"""Textual TUI for worktree and AI session management."""

import os
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

from rich.color import ColorType as RichColorType
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color as TextualColor
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, ListView, Static

try:
    _CX_VERSION = _pkg_version("cx")
except PackageNotFoundError:
    _CX_VERSION = "dev"

# Monkey-patch Color.from_rich_color to preserve ANSI default colors.
# Textual bug: from_rich_color calls get_truecolor(theme, foreground=True)
# for ALL colors, converting Color.default() bgcolor to the theme's
# foreground color (e.g. rgb(217,217,217) on MONOKAI) instead of preserving
# the default/transparent semantics.
_original_from_rich_color = TextualColor.from_rich_color.__func__

@classmethod  # type: ignore[misc]
def _patched_from_rich_color(cls, rich_color, theme=None):
    if rich_color is not None and rich_color.type == RichColorType.DEFAULT:
        return cls(0, 0, 0, ansi=-1)
    return _original_from_rich_color(cls, rich_color, theme)

TextualColor.from_rich_color = _patched_from_rich_color

from cx import claude, codex, state, worktree as wt_mod
from cx.worktree import BranchDeleteError, BranchNotMergedError, DirtyWorktreeError
from cx.config import get_current_branch
from cx.models import CodexSessionEntry, SessionEntry, WorktreeEntry
from cx.widgets.codex_session_panel import CodexSessionPanel
from cx.widgets.codex_settings_panel import CodexSettingsPanel
from cx.widgets.session_panel import SessionPanel
from cx.widgets.settings_panel import SettingsPanel
from cx.widgets.status_bar import StatusBar
from cx.widgets.worktree_panel import (
    NEW_WORKTREE_SENTINEL,
    WorktreeDeselected,
    WorktreeHighlighted,
    WorktreePanel,
)


class CxxApp(App):
    """Worktree and AI session manager."""

    CSS_PATH = "styles.tcss"
    TITLE = "cx"
    ENABLE_COMMAND_PALETTE = False
    NOTIFICATION_TIMEOUT = 3

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("tab", "focus_next", "Next", show=True, priority=True),
        Binding("shift+tab", "focus_previous", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__(ansi_color=True)
        self.theme = "textual-ansi"
        # Default the "last session side" to whichever tool is actually
        # installed, so tab-from-worktrees lands on a usable pane.
        if claude.IS_INSTALLED:
            self._last_session_side = "#session-list"
        elif codex.IS_INSTALLED:
            self._last_session_side = "#codex-session-list"
        else:
            self._last_session_side = "#session-list"  # unreachable anyway

    async def on_event(self, event) -> None:
        """Discard all mouse events."""
        from textual import events
        if isinstance(event, (events.MouseDown, events.MouseUp, events.MouseMove,
                              events.Click, events.MouseScrollDown, events.MouseScrollUp)):
            event.prevent_default()
            event.stop()
            return
        await super().on_event(event)

    def compose(self) -> ComposeResult:
        yield Static(f"[bold] cx[/] [dim](v{_CX_VERSION})[/]", id="title-bar")
        yield StatusBar()
        yield WorktreePanel()
        with Horizontal(id="session-columns"):
            with Vertical(id="claude-column"):
                yield SessionPanel()
                yield SettingsPanel(id="claude-settings")
            with Vertical(id="codex-column"):
                yield CodexSessionPanel()
                yield CodexSettingsPanel(id="codex-settings")
        yield Footer()

    def on_mount(self) -> None:
        self._update_panel_height()
        # Drop left/right/enter from ListView instances so our panel-level
        # arrow + enter bindings can own those footer slots. Left/right would
        # inherit from ScrollableContainer's scroll_*; ListView's own
        # enter binding is show=False and would hog the dedup slot in
        # active_bindings, preventing our "Select"/"Accept" labels from
        # appearing in the footer.
        for lv in self.query(ListView):
            for k in ("left", "right", "enter"):
                lv._bindings.key_to_bindings.pop(k, None)
        # Drop enter from Input instances for the same reason. We re-fire
        # Input.action_submit() from the panel's action_enter_accept to keep
        # submission behavior identical. Dynamically-mounted rename Inputs
        # get this treatment in each panel's _show_rename_input.
        for inp in self.query(Input):
            inp._bindings.key_to_bindings.pop("enter", None)
        # If load_state() quarantined a corrupt file on startup, surface it.
        notice = state.take_quarantine_notice()
        if notice is not None:
            path, backup, cause = notice
            self.notify(
                f"State file was corrupt ({type(cause).__name__}); "
                f"quarantined to {backup.name}. Starting fresh.",
                severity="warning",
                timeout=10,
            )
        try:
            wt_list = self.query_one("#worktree-list")
            wt_list.focus()
        except Exception:
            pass

    def _refocus_list(self, selector: str) -> None:
        """Re-focus and re-highlight a ListView after suspend/resume."""
        lv = self.query_one(selector, ListView)
        lv.focus()
        current_index = lv.index
        if current_index is None:
            return
        # ListView.index is a plain reactive (no always_update), so assigning
        # the same value is a no-op. Bounce through None to force watch_index
        # to fire and reapply the highlight via the public API.
        lv.index = None
        lv.index = current_index

    def _update_panel_height(self) -> None:
        """Sync panel heights across columns."""
        wt = self.query_one(WorktreePanel).content_height()
        self.query_one(WorktreePanel).styles.height = wt + 2

        claude_sess = self.query_one(SessionPanel)
        codex_sess = self.query_one(CodexSessionPanel)
        max_sess = max(claude_sess.content_height(), codex_sess.content_height(), 1)
        claude_sess.styles.height = max_sess + 2
        codex_sess.styles.height = max_sess + 2

        claude_set = self.query_one("#claude-settings", SettingsPanel)
        codex_set = self.query_one("#codex-settings", CodexSettingsPanel)
        max_set = max(claude_set.content_height(), codex_set.content_height(), 1)
        claude_set.styles.height = max_set + 2
        codex_set.styles.height = max_set + 2

    _WORKTREE_PANE = "#worktree-list"
    _SESSION_PANES = ("#session-list", "#codex-session-list")
    _SESSION_LEFT = "#session-list"
    _SESSION_RIGHT = "#codex-session-list"

    def _focused_id(self) -> str | None:
        """Return the CSS id selector of the focused widget, if any."""
        f = self.focused
        if f is None:
            return None
        return f"#{f.id}" if f.id else None

    def _available_session_sides(self) -> list[str]:
        """Session pane ids that are actually usable, in column order."""
        sides: list[str] = []
        if claude.IS_INSTALLED:
            sides.append(self._SESSION_LEFT)
        if codex.IS_INSTALLED:
            sides.append(self._SESSION_RIGHT)
        return sides

    def action_focus_next(self) -> None:
        """Move focus between worktrees and the last-active usable session pane."""
        fid = self._focused_id()
        if fid == self._WORKTREE_PANE:
            wt_list = self.query_one(self._WORKTREE_PANE, ListView)
            highlighted = wt_list.highlighted_child
            if highlighted is None or highlighted.name == NEW_WORKTREE_SENTINEL:
                return
            available = self._available_session_sides()
            if not available:
                return
            target = (
                self._last_session_side
                if self._last_session_side in available
                else available[0]
            )
            self.query_one(target).focus()
        elif fid in self._SESSION_PANES:
            self.query_one(self._WORKTREE_PANE).focus()

    def action_focus_previous(self) -> None:
        """Move focus using the same two-stop cycle as Tab."""
        self.action_focus_next()

    def action_focus_left(self) -> None:
        """Move focus from Codex sessions to Claude sessions."""
        if not claude.IS_INSTALLED:
            return
        if self._focused_id() == self._SESSION_RIGHT:
            self._last_session_side = self._SESSION_LEFT
            self.query_one(self._SESSION_LEFT).focus()

    def action_focus_right(self) -> None:
        """Move focus from Claude sessions to Codex sessions."""
        if not codex.IS_INSTALLED:
            return
        if self._focused_id() == self._SESSION_LEFT:
            self._last_session_side = self._SESSION_RIGHT
            self.query_one(self._SESSION_RIGHT).focus()

    def _focused_panel_is_modal(self) -> bool:
        """True if the focused widget is inside a panel in a modal state
        (creating/confirming/renaming). Walks up from the focused widget to
        find the nearest panel that exposes an `is_modal` property."""
        node = self.focused
        while node is not None:
            if getattr(node, "is_modal", False):
                return True
            node = node.parent
        return False

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Gate footer/binding visibility per focused pane.

        Note: left/right routing between session panes is owned by the
        panels themselves (SessionPanel.right_arrow, CodexSessionPanel
        .left_arrow), not by app-level bindings — so this method only
        gates the app's own `quit`, `focus_next`, and `toggle_settings`.
        """
        fid = self._focused_id()
        session_or_settings = (
            "#session-list", "#settings-list",
            "#codex-session-list", "#codex-settings-list",
        )
        settings_panes = ("#settings-list", "#codex-settings-list")
        # During any panel-modal state (creating / confirming / renaming),
        # suppress all app-level bindings — the panel exposes its own `esc`
        # binding and the footer should show only that.
        if self._focused_panel_is_modal():
            if action in ("focus_next", "focus_previous", "toggle_settings", "quit"):
                return False
        if action == "toggle_settings":
            return fid in session_or_settings
        if action == "focus_next":
            # Tab is a no-op in settings — hide it there.
            if fid in settings_panes:
                return False
            # On Worktrees with neither tool installed, tab has no target.
            if fid == self._WORKTREE_PANE and not self._available_session_sides():
                return False
        return True

    def action_toggle_settings(self) -> None:
        """Toggle focus between a session pane and its paired settings."""
        fid = self._focused_id()
        pairs = {
            "#session-list": "#settings-list",
            "#settings-list": "#session-list",
            "#codex-session-list": "#codex-settings-list",
            "#codex-settings-list": "#codex-session-list",
        }
        target = pairs.get(fid)
        if target:
            self.query_one(target).focus()

    def on_worktree_deselected(self, event: WorktreeDeselected) -> None:
        """Clear session panels and status bar when no worktree is selected."""
        self.query_one(SessionPanel).clear_sessions()
        self.query_one(CodexSessionPanel).clear_sessions()
        self.query_one(StatusBar).update(" Select a worktree")
        self._update_panel_height()

    def on_worktree_highlighted(self, event: WorktreeHighlighted) -> None:
        """Update session panels and status bar when worktree selection changes."""
        self.query_one(SessionPanel).update_sessions(event.wt_name, event.path)
        self.query_one(CodexSessionPanel).update_sessions(event.wt_name, event.path)
        self.query_one(StatusBar).refresh_status(event.branch, event.path)
        self._update_panel_height()

    def on_worktree_panel_new_worktree_requested(
        self, event: WorktreePanel.NewWorktreeRequested
    ) -> None:
        """Create a new worktree from inline input."""
        try:
            wt_path, branch_name, source = wt_mod.create_worktree(event.scope, event.feature_id)
        except Exception as e:
            self.notify(f"Failed to create worktree: {e}", severity="error")
            wt_panel = self.query_one(WorktreePanel)
            wt_panel.refresh_worktrees()
            self.query_one("#worktree-list").focus()
            return

        dir_name = f"{event.scope}--{event.feature_id}"
        now = datetime.now(timezone.utc)
        try:
            base_branch = get_current_branch()
        except Exception:
            base_branch = "unknown"

        with state.modify_state() as s:
            s.worktrees[dir_name] = WorktreeEntry(
                path=wt_path,
                branch=branch_name,
                base_branch=base_branch,
                created_at=now,
            )

        self.query_one(WorktreePanel).refresh_worktrees()
        self._update_panel_height()
        if source == "remote":
            self.notify(f"Created worktree from remote branch: {dir_name}")
        elif source == "local":
            self.notify(f"Created worktree from local branch: {dir_name}")
        else:
            self.notify(f"Created worktree: {dir_name}")

    def on_worktree_panel_delete_worktree_confirmed(
        self, event: WorktreePanel.DeleteWorktreeConfirmed
    ) -> None:
        """Delete a worktree after inline confirmation."""
        branch_error: BranchDeleteError | None = None
        deleted_sha: str | None = None
        try:
            deleted_sha = wt_mod.remove_worktree(
                str(event.path), event.branch, force=event.force,
            )
        except DirtyWorktreeError:
            self.query_one(WorktreePanel).show_force_confirm(
                event.wt_name, reason="Uncommitted changes.",
            )
            return
        except BranchNotMergedError:
            self.query_one(WorktreePanel).show_force_confirm(event.wt_name)
            return
        except BranchDeleteError as w:
            # Worktree was removed but the branch was not — continue with
            # state cleanup and warn the user.
            branch_error = w
        except Exception as e:
            self.notify(f"Failed to remove worktree: {e}", severity="error")
            return

        with state.modify_state() as s:
            keys_to_remove = [
                name for name, entry in s.worktrees.items()
                if Path(entry.path) == event.path
            ]
            for key in keys_to_remove:
                s.worktrees.pop(key, None)
            s.worktrees.pop(event.wt_name, None)

        self.query_one(WorktreePanel).refresh_worktrees()
        self._update_panel_height()
        if branch_error is not None:
            self.notify(
                f"Deleted worktree: {event.wt_name} "
                f"(branch '{branch_error.branch}' kept: {branch_error.stderr.strip()})",
                severity="warning",
                timeout=8,
            )
        elif event.force and deleted_sha is not None and event.branch is not None:
            self.notify(
                f"Deleted worktree: {event.wt_name} "
                f"(branch '{event.branch}' was {deleted_sha}; "
                f"recover: git branch {event.branch} {deleted_sha})"
            )
        else:
            self.notify(f"Deleted worktree: {event.wt_name}")

    def on_session_panel_new_session_requested(
        self, event: SessionPanel.NewSessionRequested
    ) -> None:
        """Create a new session and refresh the list."""
        session_id = claude.generate_session_id()
        now = datetime.now(timezone.utc)

        with state.modify_state() as s:
            if event.wt_name not in s.worktrees:
                branch = event.wt_name
                base_branch = "unknown"
                for dw in wt_mod.discover_worktrees():
                    if dw.path == event.wt_path:
                        branch = dw.branch or event.wt_name
                        break
                s.worktrees[event.wt_name] = WorktreeEntry(
                    path=event.wt_path,
                    branch=branch,
                    base_branch=base_branch,
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
        self.set_timer(0.1, lambda: self._refocus_list("#session-list"))
        self.notify(f"Created session: {event.name}")

    def on_session_panel_launch_session_requested(
        self, event: SessionPanel.LaunchSessionRequested
    ) -> None:
        """Launch/resume a Claude Code session, then return to TUI."""
        resume = claude.session_has_history(event.session_id)
        settings_args = self.query_one("#claude-settings", SettingsPanel).get_claude_args()
        args = claude.build_session_args(
            event.session_id, name=event.session_name, extra_args=settings_args,
            resume=resume,
        )

        # Claude active-detection is registry-driven (cx.claude.get_active_session_ids
        # reads Claude's own $CLAUDE_CONFIG_DIR/sessions/*.json), so cx
        # does not need to mark the session as active in its own state.

        spawn_error: Exception | None = None
        launched = False
        try:
            with self.suspend():
                os.system("clear")
                try:
                    claude.run_claude(args, event.wt_path)
                    launched = True
                except (FileNotFoundError, PermissionError, OSError) as e:
                    spawn_error = e
                os.system("clear")
        finally:
            # Bump last_accessed only when the launch actually happened —
            # failed spawns must not reshuffle ordering.
            if launched:
                now = datetime.now(timezone.utc)
                with state.modify_state() as s:
                    for wt in s.worktrees.values():
                        for session in wt.sessions:
                            if session.session_id == event.session_id:
                                session.last_accessed = now
                                break

        if spawn_error is not None:
            self.notify(
                f"Failed to launch claude: {spawn_error}",
                severity="error",
                timeout=8,
            )

        session_panel = self.query_one(SessionPanel)
        if session_panel._current_wt_name and session_panel._current_wt_path:
            session_panel.update_sessions(
                session_panel._current_wt_name,
                session_panel._current_wt_path,
            )
        self.set_timer(0.1, lambda: self._refocus_list("#session-list"))

    def on_session_panel_delete_session_confirmed(
        self, event: SessionPanel.DeleteSessionConfirmed
    ) -> None:
        """Soft-delete a session after inline confirmation."""
        with state.modify_state() as s:
            wt = s.worktrees.get(event.wt_name)
            if wt:
                wt.sessions = [ss for ss in wt.sessions if ss.session_id != event.session_id]

        session_panel = self.query_one(SessionPanel)
        if session_panel._current_wt_name and session_panel._current_wt_path:
            session_panel.update_sessions(
                session_panel._current_wt_name,
                session_panel._current_wt_path,
            )
        self._update_panel_height()
        self.notify(f"Removed session: {event.session_name}")

    def on_session_panel_rename_session_requested(
        self, event: SessionPanel.RenameSessionRequested
    ) -> None:
        """Rename a session in state."""
        renamed = False
        with state.modify_state() as s:
            wt = s.worktrees.get(event.wt_name)
            if wt:
                for session in wt.sessions:
                    if session.session_id == event.session_id:
                        session.name = event.new_name
                        renamed = True
                        break

        if not renamed:
            self.notify("Session not found", severity="warning")
            return

        session_panel = self.query_one(SessionPanel)
        if session_panel._current_wt_name and session_panel._current_wt_path:
            session_panel.update_sessions(
                session_panel._current_wt_name,
                session_panel._current_wt_path,
            )

        lv = session_panel.query_one("#session-list", ListView)
        for i, child in enumerate(lv.children):
            if getattr(child, "_session_id", None) == event.session_id:
                lv.index = i
                break
        self.call_after_refresh(lv.focus)
        self.notify(f"Renamed: {event.old_name} → {event.new_name}")

    def on_codex_session_panel_new_session_requested(
        self, event: CodexSessionPanel.NewSessionRequested
    ) -> None:
        """Create a new Codex session and refresh the list."""
        placeholder_id = codex.generate_placeholder_id()
        now = datetime.now(timezone.utc)

        with state.modify_state() as s:
            if event.wt_name not in s.worktrees:
                branch = event.wt_name
                base_branch = "unknown"
                for dw in wt_mod.discover_worktrees():
                    if dw.path == event.wt_path:
                        branch = dw.branch or event.wt_name
                        break
                s.worktrees[event.wt_name] = WorktreeEntry(
                    path=event.wt_path,
                    branch=branch,
                    base_branch=base_branch,
                    created_at=now,
                )
            s.worktrees[event.wt_name].codex_sessions.append(
                CodexSessionEntry(
                    thread_id=placeholder_id,
                    name=event.name,
                    created_at=now,
                    last_accessed=now,
                )
            )

        codex_panel = self.query_one(CodexSessionPanel)
        codex_panel.update_sessions(event.wt_name, event.wt_path)
        self._update_panel_height()
        self.set_timer(0.1, lambda: self._refocus_list("#codex-session-list"))
        self.notify(f"Created Codex session: {event.name}")

    def on_codex_session_panel_launch_session_requested(
        self, event: CodexSessionPanel.LaunchSessionRequested
    ) -> None:
        """Launch/resume a Codex session, then return to TUI."""
        is_new = codex.is_placeholder(event.thread_id)
        settings_args = self.query_one("#codex-settings", CodexSettingsPanel).get_codex_args()

        if is_new:
            args = codex.build_session_args(extra_args=settings_args)
        else:
            args = codex.build_resume_args(event.thread_id, extra_args=settings_args)

        # Mark the session as owned by this cx pid before suspending.
        # codex_session_panel reads owner_pid and validates /proc to
        # render the green dot; cx runs codex synchronously under
        # App.suspend(), so /proc/<cx_pid> being alive is a reliable
        # liveness proxy for the codex child.
        cx_pid = os.getpid()
        with state.modify_state() as s:
            for wt in s.worktrees.values():
                for session in wt.codex_sessions:
                    if session.thread_id == event.thread_id:
                        session.owner_pid = cx_pid
                        break

        # Snapshot rollout files so we can diff post-launch to authoritatively
        # find the new thread id (SQLite is only a fallback).
        before_snapshot = codex.snapshot_rollouts() if is_new else set()
        before_ts = int(datetime.now(timezone.utc).timestamp()) if is_new else 0

        spawn_error: Exception | None = None
        launched = False
        try:
            with self.suspend():
                os.system("clear")
                try:
                    codex.run_codex(args, event.wt_path)
                    launched = True
                except (FileNotFoundError, PermissionError, OSError) as e:
                    spawn_error = e
                os.system("clear")
        finally:
            now = datetime.now(timezone.utc)
            # Clear owner_pid and update last_accessed only on successful launch.
            with state.modify_state() as s:
                for wt in s.worktrees.values():
                    for session in wt.codex_sessions:
                        if session.thread_id == event.thread_id:
                            session.owner_pid = None
                            if launched:
                                session.last_accessed = now
                            break

        if spawn_error is not None:
            self.notify(
                f"Failed to launch codex: {spawn_error}",
                severity="error",
                timeout=8,
            )

        # Promote placeholder → real thread id using the rollout-file diff.
        promotion_failed = False
        if is_new and launched:
            real_thread_id = codex.discover_thread_id_from_rollouts(
                before_snapshot, cwd=event.wt_path
            )
            if real_thread_id is None:
                # Fallback: SQLite, excluding thread ids already owned by
                # other cx sessions so we can't double-bind.
                current = state.load_state()
                owned: set[str] = {
                    s.thread_id
                    for wt in current.worktrees.values()
                    for s in wt.codex_sessions
                    if not codex.is_placeholder(s.thread_id)
                }
                real_thread_id = codex.discover_thread_id_from_db(
                    event.wt_path, before_ts, exclude_ids=owned
                )
            if real_thread_id is not None:
                with state.modify_state() as s:
                    for wt in s.worktrees.values():
                        for session in wt.codex_sessions:
                            if session.thread_id == event.thread_id:
                                session.thread_id = real_thread_id
                                break
            else:
                promotion_failed = True

        if promotion_failed:
            self.notify(
                "Could not find the new Codex thread. Session will remain "
                "unresumable until you retry.",
                severity="warning",
                timeout=8,
            )

        codex_panel = self.query_one(CodexSessionPanel)
        if codex_panel._current_wt_name and codex_panel._current_wt_path:
            codex_panel.update_sessions(
                codex_panel._current_wt_name,
                codex_panel._current_wt_path,
            )
        self.set_timer(0.1, lambda: self._refocus_list("#codex-session-list"))

    def on_codex_session_panel_delete_session_confirmed(
        self, event: CodexSessionPanel.DeleteSessionConfirmed
    ) -> None:
        """Soft-delete a Codex session after inline confirmation."""
        with state.modify_state() as s:
            wt = s.worktrees.get(event.wt_name)
            if wt:
                wt.codex_sessions = [
                    ss for ss in wt.codex_sessions
                    if ss.thread_id != event.thread_id
                ]

        codex_panel = self.query_one(CodexSessionPanel)
        if codex_panel._current_wt_name and codex_panel._current_wt_path:
            codex_panel.update_sessions(
                codex_panel._current_wt_name,
                codex_panel._current_wt_path,
            )
        self._update_panel_height()
        self.notify(f"Removed Codex session: {event.session_name}")

    def on_codex_session_panel_rename_session_requested(
        self, event: CodexSessionPanel.RenameSessionRequested
    ) -> None:
        """Rename a Codex session in state."""
        renamed = False
        with state.modify_state() as s:
            wt = s.worktrees.get(event.wt_name)
            if wt:
                for session in wt.codex_sessions:
                    if session.thread_id == event.thread_id:
                        session.name = event.new_name
                        renamed = True
                        break

        if not renamed:
            self.notify("Session not found", severity="warning")
            return

        codex_panel = self.query_one(CodexSessionPanel)
        if codex_panel._current_wt_name and codex_panel._current_wt_path:
            codex_panel.update_sessions(
                codex_panel._current_wt_name,
                codex_panel._current_wt_path,
            )

        lv = codex_panel.query_one("#codex-session-list", ListView)
        for i, child in enumerate(lv.children):
            if getattr(child, "_codex_thread_id", None) == event.thread_id:
                lv.index = i
                break
        self.call_after_refresh(lv.focus)
        self.notify(f"Renamed: {event.old_name} → {event.new_name}")


def main() -> None:
    """Run the TUI."""
    app = CxxApp()
    app.run()
