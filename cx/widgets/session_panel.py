"""Session panel — right side of the TUI."""

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.containers import Horizontal
from textual.widgets import Input, Label, ListItem, ListView, Static

from cx import claude, state

NEW_SESSION_SENTINEL = "__new_session__"


class SessionPanel(Widget, can_focus=False):
    """Right panel showing sessions for the selected worktree."""

    BORDER_TITLE = "Sessions"

    BINDINGS = [
        Binding("d", "delete_session", "Delete", show=True),
    ]

    class NewSessionRequested(Message):
        """Request to create a new session."""

        def __init__(self, wt_name: str, wt_path: Path, name: str) -> None:
            super().__init__()
            self.wt_name = wt_name
            self.wt_path = wt_path
            self.name = name

    class DeleteSessionConfirmed(Message):
        """Confirmed deletion of a session."""

        def __init__(self, wt_name: str, session_id: str, session_name: str) -> None:
            super().__init__()
            self.wt_name = wt_name
            self.session_id = session_id
            self.session_name = session_name

    class LaunchSessionRequested(Message):
        """Request to launch/resume a Claude Code session."""

        def __init__(self, session_id: str, session_name: str, wt_path: Path) -> None:
            super().__init__()
            self.session_id = session_id
            self.session_name = session_name
            self.wt_path = wt_path

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_wt_name: str | None = None
        self._current_wt_path: Path | None = None
        self._confirm_item: ListItem | None = None
        self._confirm_yes: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Select a worktree", classes="empty-message", id="session-empty")
        yield ListView(id="session-list")
        yield Input(placeholder="session name", id="session-name", classes="inline-input")

    def on_mount(self) -> None:
        self.border_title = "Sessions"
        self.query_one("#session-list", ListView).display = False
        self.query_one("#session-name", Input).display = False

    def on_descendant_focus(self, event) -> None:
        """Re-apply index when session list gains focus."""
        lv = self.query_one("#session-list", ListView)
        if lv.has_focus and lv.index is not None:
            idx = lv.index
            lv.index = None
            lv.index = idx

    def content_height(self) -> int:
        """Return total visible item count for height calculation."""
        lv = self.query_one("#session-list", ListView)
        if not lv.display:
            return 1  # empty message
        count = sum(1 for c in lv.children if c.display)
        if self.query_one("#session-name", Input).display:
            count += 1
        return count

    @property
    def _is_creating(self) -> bool:
        return self.query_one("#session-name", Input).display

    def _get_sentinel(self) -> ListItem | None:
        lv = self.query_one("#session-list", ListView)
        for child in lv.children:
            if getattr(child, "name", None) == NEW_SESSION_SENTINEL:
                return child
        return None

    def _show_inline_input(self) -> None:
        sentinel = self._get_sentinel()
        if sentinel:
            sentinel.display = False
        inp = self.query_one("#session-name", Input)
        inp.display = True
        inp.focus()

    def _hide_inline_input(self) -> None:
        inp = self.query_one("#session-name", Input)
        inp.value = ""
        inp.display = False
        sentinel = self._get_sentinel()
        if sentinel:
            sentinel.display = True

    def clear_sessions(self) -> None:
        """Reset session panel to empty state."""
        self._current_wt_name = None
        self._current_wt_path = None
        self._hide_inline_input()
        lv = self.query_one("#session-list", ListView)
        lv.remove_children()
        lv.display = False
        self.query_one("#session-empty", Static).display = True

    def update_sessions(self, wt_name: str, wt_path: Path) -> None:
        """Refresh the session list for the given worktree."""
        self._current_wt_name = wt_name
        self._current_wt_path = wt_path
        self.query_one("#session-name", Input).value = ""
        self.query_one("#session-name", Input).display = False

        current_state = state.load_state()
        wt_entry = current_state.worktrees.get(wt_name)
        sessions = wt_entry.sessions if wt_entry else []

        lv = self.query_one("#session-list", ListView)
        empty = self.query_one("#session-empty", Static)

        lv.remove_children()
        empty.display = False
        lv.display = True

        items: list[ListItem] = []

        # Sort by last_accessed descending
        active_ids = claude.get_active_session_ids()
        sorted_sessions = sorted(sessions, key=lambda s: s.last_accessed, reverse=True)
        for session in sorted_sessions:
            is_active = session.session_id in active_ids
            dot_color = "#98c379" if is_active else "#555555"
            item = ListItem(
                Horizontal(
                    Label(session.name, classes="session-name"),
                    Label(f"[{dot_color}]●[/]", classes="session-indicator"),
                ),
                name=session.name,
            )
            item._session_id = session.session_id
            item._is_active = is_active
            items.append(item)

        # Always add "+ New session" at the end
        new_item = ListItem(
            Label("[#DA7756]+ New session[/]"),
            name=NEW_SESSION_SENTINEL,
        )
        new_item._session_id = None
        items.append(new_item)

        lv.mount_all(items)
        lv.index = 0

    # --- Inline confirm ---

    @property
    def _is_confirming(self) -> bool:
        return self._confirm_item is not None

    def _show_confirm(self, item: ListItem) -> None:
        self._confirm_item = item
        self._confirm_yes = False
        # Repurpose existing Horizontal labels
        h = item.query_one(Horizontal)
        name_label = h.query_one(".session-name", Label)
        indicator = h.query_one(".session-indicator", Label)
        name = item.name or ""
        name_label.update(f"Delete [bold]{name}[/]?")
        indicator.remove_class("session-indicator")
        indicator.add_class("confirm-choices")
        self._render_confirm()

    def _render_confirm(self) -> None:
        if not self._confirm_item:
            return
        choices = self._confirm_item.query_one(".confirm-choices", Label)
        if self._confirm_yes:
            choices.update("[#ff6b7c]Yes[/] │ No")
        else:
            choices.update("Yes │ [#ff6b7c]No[/]")

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
            dot_color = "#98c379" if is_active else "#555555"
            choices.update(f"[{dot_color}]●[/]")
        self._confirm_item = None
        self._confirm_yes = False

    def _accept_confirm(self) -> None:
        if not self._confirm_item:
            return
        item = self._confirm_item
        if self._confirm_yes:
            self._cancel_confirm()
            self.post_message(
                self.DeleteSessionConfirmed(
                    wt_name=self._current_wt_name or "",
                    session_id=getattr(item, "_session_id", ""),
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

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle enter key on a list item."""
        if event.item is None:
            return
        if event.item.name == NEW_SESSION_SENTINEL:
            if not self._current_wt_name or not self._current_wt_path:
                return
            self._show_inline_input()
            return
        # Launch/resume existing session
        session_id = getattr(event.item, "_session_id", None)
        if getattr(event.item, "_is_active", False):
            self.notify("Session is already active", severity="warning")
            return
        if session_id and self._current_wt_path:
            self.post_message(
                self.LaunchSessionRequested(
                    session_id=session_id,
                    session_name=event.item.name or "",
                    wt_path=self._current_wt_path,
                )
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "session-name":
            name = event.input.value.strip()
            if not name:
                self.notify("Session name cannot be empty", severity="warning")
                return
            if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$", name):
                self.notify("Invalid name (alphanumeric, spaces, hyphens, underscores)", severity="error")
                return
            self._hide_inline_input()
            self.post_message(
                self.NewSessionRequested(
                    wt_name=self._current_wt_name,
                    wt_path=self._current_wt_path,
                    name=name,
                )
            )

    def on_key(self, event) -> None:
        if self._is_confirming:
            if event.key == "left" or event.key == "right":
                self._confirm_yes = not self._confirm_yes
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
            self.query_one("#session-list", ListView).focus()
            event.stop()

    def action_delete_session(self) -> None:
        if self._is_confirming:
            self._cancel_confirm()
            return
        if not self._current_wt_name:
            return
        lv = self.query_one("#session-list", ListView)
        if lv.highlighted_child is None:
            return
        if lv.highlighted_child.name == NEW_SESSION_SENTINEL:
            return
        self._show_confirm(lv.highlighted_child)
