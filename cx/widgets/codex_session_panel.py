"""Codex session panel for the TUI."""

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, Static

from cx import codex, state
from cx.colors import ACCENT, BORDER, DANGER, GREEN

NEW_SESSION_SENTINEL = "__new_codex_session__"
SESSION_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")


class CodexSessionPanel(Widget, can_focus=False):
    """Panel showing Codex CLI sessions for the selected worktree."""

    BORDER_TITLE = "Codex Sessions"

    BINDINGS = [
        Binding("q", "app.quit", "Quit", show=True),
        Binding("d", "delete_session", "Delete", show=True),
        Binding("r", "rename_session", "Rename", show=True),
        Binding("s", "app.toggle_settings", "Settings", show=True),
        Binding("tab", "app.focus_next", "Worktrees", show=True, priority=True),
        # Routed through a panel-local action so delete-confirm / rename can
        # intercept before focus changes to the Claude column.
        Binding("left", "left_arrow", "Claude Code", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=True),
        # Enter bindings: gated by check_action so only one shows at a time.
        Binding("enter", "enter_select", "Select", show=True),
        Binding("enter", "enter_accept", "Accept", show=True),
    ]

    class NewSessionRequested(Message):
        """Request to create a new Codex session."""

        def __init__(self, wt_name: str, wt_path: Path, name: str) -> None:
            super().__init__()
            self.wt_name = wt_name
            self.wt_path = wt_path
            self.name = name

    class DeleteSessionConfirmed(Message):
        """Confirmed deletion of a Codex session."""

        def __init__(self, wt_name: str, thread_id: str, session_name: str) -> None:
            super().__init__()
            self.wt_name = wt_name
            self.thread_id = thread_id
            self.session_name = session_name

    class LaunchSessionRequested(Message):
        """Request to launch/resume a Codex session."""

        def __init__(self, thread_id: str, session_name: str, wt_path: Path) -> None:
            super().__init__()
            self.thread_id = thread_id
            self.session_name = session_name
            self.wt_path = wt_path

    class RenameSessionRequested(Message):
        """Request to rename a Codex session."""

        def __init__(self, wt_name: str, thread_id: str, old_name: str, new_name: str) -> None:
            super().__init__()
            self.wt_name = wt_name
            self.thread_id = thread_id
            self.old_name = old_name
            self.new_name = new_name

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_wt_name: str | None = None
        self._current_wt_path: Path | None = None
        self._confirm_item: ListItem | None = None
        self._confirm_yes: bool = False
        self._rename_item: ListItem | None = None

    def compose(self) -> ComposeResult:
        empty_text = (
            "Codex not installed" if not codex.IS_INSTALLED
            else "Select a worktree"
        )
        yield Static(empty_text, classes="empty-message", id="codex-session-empty")
        yield ListView(id="codex-session-list")
        yield Input(placeholder="session name", id="codex-session-name", classes="inline-input")

    def on_mount(self) -> None:
        self.query_one("#codex-session-list", ListView).display = False
        self.query_one("#codex-session-name", Input).display = False
        if not codex.IS_INSTALLED:
            # Panel is inert: the empty "not installed" message is permanent,
            # the ListView never shows, and focus can never land here.
            self.query_one("#codex-session-list", ListView).can_focus = False

    def on_descendant_focus(self, event) -> None:
        """Re-apply index when session list gains focus."""
        lv = self.query_one("#codex-session-list", ListView)
        if lv.has_focus and lv.index is not None:
            idx = lv.index
            lv.index = None
            lv.index = idx

    def content_height(self) -> int:
        """Return total visible item count for height calculation."""
        lv = self.query_one("#codex-session-list", ListView)
        if not lv.display:
            return 1
        count = sum(1 for c in lv.children if c.display)
        if self.query_one("#codex-session-name", Input).display:
            count += 1
        return count

    @property
    def _is_creating(self) -> bool:
        return self.query_one("#codex-session-name", Input).display

    @property
    def _is_renaming(self) -> bool:
        return self._rename_item is not None

    @property
    def is_modal(self) -> bool:
        """True when the panel has a modal UI element (create/rename/confirm)."""
        return self._is_creating or self._is_renaming or self._is_confirming

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Gate footer visibility based on modal state and highlight."""
        from cx import claude
        on_sentinel = self._highlight_is_sentinel()
        if action in ("delete_session", "rename_session"):
            # Hidden during modal or when hovering "+ New session".
            return not self.is_modal and not on_sentinel
        if action == "left_arrow":
            # Hide when the Claude column is not installed — there's nothing
            # to cross to.
            if not claude.IS_INSTALLED:
                return False
            return not self.is_modal
        if action == "cancel":
            return self.is_modal
        if action == "enter_select":
            return not self.is_modal
        if action == "enter_accept":
            # Shown during any modal state (create/rename/confirm).
            return self.is_modal
        return True

    def _highlight_is_sentinel(self) -> bool:
        """True if the currently highlighted list item is the "+ New" sentinel."""
        try:
            lv = self.query_one("#codex-session-list", ListView)
        except Exception:
            return False
        child = lv.highlighted_child
        return child is not None and child.name == NEW_SESSION_SENTINEL

    def _get_sentinel(self) -> ListItem | None:
        lv = self.query_one("#codex-session-list", ListView)
        for child in lv.children:
            if getattr(child, "name", None) == NEW_SESSION_SENTINEL:
                return child
        return None

    def _show_inline_input(self) -> None:
        sentinel = self._get_sentinel()
        if sentinel:
            sentinel.display = False
        inp = self.query_one("#codex-session-name", Input)
        inp.display = True
        inp.focus()

    def _hide_inline_input(self) -> None:
        inp = self.query_one("#codex-session-name", Input)
        inp.value = ""
        inp.display = False
        sentinel = self._get_sentinel()
        if sentinel:
            sentinel.display = True

    def clear_sessions(self) -> None:
        """Reset session panel to empty state."""
        if not codex.IS_INSTALLED:
            return  # Inert — keep the "not installed" message.
        self._current_wt_name = None
        self._current_wt_path = None
        self._hide_inline_input()
        if self._is_renaming:
            self._cancel_rename()
        lv = self.query_one("#codex-session-list", ListView)
        lv.remove_children()
        lv.display = False
        self.query_one("#codex-session-empty", Static).display = True

    def _show_rename_input(self, item: ListItem) -> None:
        """Replace the session name label with an inline Input for renaming."""
        self._rename_item = item
        from textual.color import Color
        item.styles.background = Color(255, 255, 255, 0.3)
        current_name = (item.name or "").strip()
        h = item.query_one(Horizontal)
        name_label = h.query_one(".session-name", Label)
        name_label.display = False
        rename_input = Input(
            value=current_name,
            id="codex-session-rename",
            classes="inline-input",
            select_on_focus=False,
        )
        h.mount(rename_input, before=name_label)
        # Drop Input's built-in enter binding so the panel's enter_accept
        # binding can own the footer slot (see app.on_mount for rationale).
        rename_input._bindings.key_to_bindings.pop("enter", None)
        rename_input.focus()
        rename_input.cursor_position = len(current_name)

    def _cancel_rename(self) -> None:
        """Cancel rename and restore the original label."""
        if self._rename_item:
            self._rename_item.styles.background = None
            h = self._rename_item.query_one(Horizontal)
            try:
                h.query_one("#codex-session-rename", Input).remove()
            except NoMatches:
                pass
            h.query_one(".session-name", Label).display = True
        self._rename_item = None

    def update_sessions(self, wt_name: str, wt_path: Path) -> None:
        """Refresh the session list for the given worktree."""
        if not codex.IS_INSTALLED:
            return  # Inert — keep the "not installed" message.
        self._current_wt_name = wt_name
        self._current_wt_path = wt_path
        self.query_one("#codex-session-name", Input).value = ""
        self.query_one("#codex-session-name", Input).display = False

        current_state = state.load_state()
        wt_entry = current_state.worktrees.get(wt_name)
        sessions = wt_entry.codex_sessions if wt_entry else []

        lv = self.query_one("#codex-session-list", ListView)
        empty = self.query_one("#codex-session-empty", Static)

        lv.remove_children()
        empty.display = False
        lv.display = True

        items: list[ListItem] = []

        # Sort by last_accessed descending. "Active" is driven by the
        # cx-owned owner_pid on each session entry, validated against /proc,
        # so a crashed codex can't leave a permanent false dot.
        sorted_sessions = sorted(sessions, key=lambda s: s.last_accessed, reverse=True)
        for session in sorted_sessions:
            is_active = bool(
                session.owner_pid and codex.prune_dead_pids({session.owner_pid})
            )
            dot_color = GREEN if is_active else BORDER
            item = ListItem(
                Horizontal(
                    Label(session.name, classes="session-name"),
                    Label(f"[{dot_color}]●[/]", classes="session-indicator"),
                ),
                name=session.name,
            )
            item._codex_thread_id = session.thread_id
            item._is_active = is_active
            items.append(item)

        new_item = ListItem(
            Label(f"[{ACCENT}]+ New session[/]"),
            name=NEW_SESSION_SENTINEL,
        )
        new_item._codex_thread_id = None
        items.append(new_item)

        lv.mount_all(items)
        lv.index = 0

    @property
    def _is_confirming(self) -> bool:
        return self._confirm_item is not None

    def _show_confirm(self, item: ListItem) -> None:
        self._confirm_item = item
        self._confirm_yes = False
        h = item.query_one(Horizontal)
        name_label = h.query_one(".session-name", Label)
        indicator = h.query_one(".session-indicator", Label)
        name = item.name or ""
        name_label.update(f"Delete [bold]{name}[/]?")
        indicator.remove_class("session-indicator")
        indicator.add_class("confirm-choices")
        self._render_confirm()
        self.refresh_bindings()

    def _render_confirm(self) -> None:
        if not self._confirm_item:
            return
        choices = self._confirm_item.query_one(".confirm-choices", Label)
        # Layout: No (left) │ Yes (right). Directional arrows: left → No,
        # right → Yes. Noop when already on that side.
        if self._confirm_yes:
            choices.update(f"No │ [{DANGER}]Yes[/]")
        else:
            choices.update(f"[{DANGER}]No[/] │ Yes")

    def _cancel_confirm(self) -> None:
        if self._confirm_item:
            h = self._confirm_item.query_one(Horizontal)
            name_label = h.query_one(".session-name", Label)
            choices = h.query_one(".confirm-choices", Label)
            session_name = self._confirm_item.name or ""
            name_label.update(session_name)
            choices.remove_class("confirm-choices")
            choices.add_class("session-indicator")
            is_active = getattr(self._confirm_item, "_is_active", False)
            dot_color = GREEN if is_active else BORDER
            choices.update(f"[{dot_color}]●[/]")
        self._confirm_item = None
        self._confirm_yes = False
        self.refresh_bindings()

    def _accept_confirm(self) -> None:
        if not self._confirm_item:
            return
        item = self._confirm_item
        if self._confirm_yes:
            self._cancel_confirm()
            self.post_message(
                self.DeleteSessionConfirmed(
                    wt_name=self._current_wt_name or "",
                    thread_id=getattr(item, "_codex_thread_id", ""),
                    session_name=item.name or "",
                )
            )
        else:
            self._cancel_confirm()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Hide inline input when navigating away."""
        if self._is_creating:
            self._hide_inline_input()
        if self._is_confirming:
            self._cancel_confirm()
        if self._is_renaming:
            self._cancel_rename()
        # Footer visibility depends on whether we're on the sentinel.
        self.refresh_bindings()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle enter key on a list item."""
        if event.item is None:
            return
        if event.item.name == NEW_SESSION_SENTINEL:
            if not self._current_wt_name or not self._current_wt_path:
                return
            self._show_inline_input()
            return
        thread_id = getattr(event.item, "_codex_thread_id", None)
        if getattr(event.item, "_is_active", False):
            self.notify("Session is already active", severity="warning")
            return
        if thread_id and self._current_wt_path:
            self.post_message(
                self.LaunchSessionRequested(
                    thread_id=thread_id,
                    session_name=event.item.name or "",
                    wt_path=self._current_wt_path,
                )
            )

    def _validate_session_name(self, name: str) -> str | None:
        """Validate and return stripped name, or None with notification on failure."""
        name = name.strip()
        if not name:
            self.notify("Session name cannot be empty", severity="warning")
            return None
        if not SESSION_NAME_RE.match(name):
            self.notify("Invalid name (alphanumeric, spaces, hyphens, underscores)", severity="error")
            return None
        return name

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "codex-session-name":
            name = self._validate_session_name(event.input.value)
            if not name:
                return
            self._hide_inline_input()
            self.post_message(
                self.NewSessionRequested(
                    wt_name=self._current_wt_name,
                    wt_path=self._current_wt_path,
                    name=name,
                )
            )
        elif event.input.id == "codex-session-rename":
            name = self._validate_session_name(event.input.value)
            if not name:
                return
            item = self._rename_item
            old_name = (item.name or "") if item else ""
            self._cancel_rename()
            if item and name != old_name:
                self.post_message(
                    self.RenameSessionRequested(
                        wt_name=self._current_wt_name or "",
                        thread_id=getattr(item, "_codex_thread_id", ""),
                        old_name=old_name,
                        new_name=name,
                    )
                )
            else:
                # Keep focus on this pane when the rename handler is skipped.
                self.query_one("#codex-session-list", ListView).focus()

    def action_left_arrow(self) -> None:
        """Left arrow: directional in confirm (→ No), else move focus to Claude."""
        if self._is_confirming:
            if self._confirm_yes:
                self._confirm_yes = False
                self._render_confirm()
            return
        if self._is_renaming:
            return
        self.app.action_focus_left()

    def action_cancel(self) -> None:
        """Escape action: cancel create/rename/confirm modal state."""
        if self._is_confirming:
            self._cancel_confirm()
            return
        if self._is_renaming:
            self._cancel_rename()
            self.query_one("#codex-session-list", ListView).focus()
            return
        if self._is_creating:
            self._hide_inline_input()
            self.query_one("#codex-session-list", ListView).focus()
            return

    def action_enter_select(self) -> None:
        """Enter action: activate the highlighted list item. Delegates to the
        ListView's built-in select-cursor action, which posts ListView.Selected
        and triggers on_list_view_selected."""
        self.query_one("#codex-session-list", ListView).action_select_cursor()

    async def action_enter_accept(self) -> None:
        """Enter action during modal: accept confirm or submit focused input."""
        if self._is_confirming:
            self._accept_confirm()
            return
        inp = self.app.focused
        if isinstance(inp, Input):
            await inp.action_submit()

    def on_key(self, event) -> None:
        if self._is_renaming:
            if event.key == "escape":
                self._cancel_rename()
                self.query_one("#codex-session-list", ListView).focus()
                event.stop()
                return
        if self._is_confirming:
            # Directional arrows: left → No, right → Yes. Both arrows are
            # handled here during confirm — the panel's priority `left_arrow`
            # binding is disabled via check_action so it doesn't pre-empt us.
            if event.key == "left":
                if self._confirm_yes:
                    self._confirm_yes = False
                    self._render_confirm()
                event.stop()
                return
            if event.key == "right":
                if not self._confirm_yes:
                    self._confirm_yes = True
                    self._render_confirm()
                event.stop()
                return
            if event.key == "enter":
                self._accept_confirm()
                event.stop()
                return
            if event.key == "escape":
                self._cancel_confirm()
                event.stop()
                return
        if event.key == "escape" and self._is_creating:
            self._hide_inline_input()
            self.query_one("#codex-session-list", ListView).focus()
            event.stop()

    def action_delete_session(self) -> None:
        if self._is_renaming:
            self._cancel_rename()
            return
        if self._is_confirming:
            self._cancel_confirm()
            return
        if not self._current_wt_name:
            return
        lv = self.query_one("#codex-session-list", ListView)
        if lv.highlighted_child is None:
            return
        if lv.highlighted_child.name == NEW_SESSION_SENTINEL:
            return
        if getattr(lv.highlighted_child, "_is_active", False):
            self.notify("Cannot delete an active session", severity="warning")
            return
        self._show_confirm(lv.highlighted_child)

    def action_rename_session(self) -> None:
        if self._is_renaming:
            self._cancel_rename()
            return
        if self._is_creating or self._is_confirming:
            return
        if not self._current_wt_name:
            return
        lv = self.query_one("#codex-session-list", ListView)
        if lv.highlighted_child is None:
            return
        if lv.highlighted_child.name == NEW_SESSION_SENTINEL:
            return
        if getattr(lv.highlighted_child, "_is_active", False):
            self.notify("Cannot rename an active session", severity="warning")
            return
        self._show_rename_input(lv.highlighted_child)
