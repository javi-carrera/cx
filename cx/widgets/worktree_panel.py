"""Worktree panel — left side of the TUI."""

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView

from cx import worktree

NEW_WORKTREE_SENTINEL = "__new__"


class WorktreeHighlighted(Message):
    """Posted when a worktree is highlighted in the list."""

    def __init__(self, name: str, path: Path, branch: str | None, is_root: bool) -> None:
        super().__init__()
        self.wt_name = name
        self.path = path
        self.branch = branch
        self.is_root = is_root


class WorktreeDeselected(Message):
    """Posted when no real worktree is highlighted (e.g. sentinel)."""


class WorktreePanel(Widget, can_focus=False):
    """Left panel showing git worktrees."""

    BORDER_TITLE = "Worktrees"

    BINDINGS = [
        Binding("d", "delete_worktree", "Delete", show=True),
    ]

    class NewWorktreeRequested(Message):
        """Request to create a new worktree."""

        def __init__(self, scope: str, feature_id: str) -> None:
            super().__init__()
            self.scope = scope
            self.feature_id = feature_id

    class DeleteWorktreeConfirmed(Message):
        """Confirmed deletion of a worktree."""

        def __init__(self, name: str, path: Path, branch: str | None) -> None:
            super().__init__()
            self.wt_name = name
            self.path = path
            self.branch = branch

    def compose(self) -> ComposeResult:
        yield ListView(id="worktree-list")
        with Horizontal(id="wt-create-row", classes="inline-create"):
            yield Input(placeholder="scope", id="wt-scope")
            yield Input(placeholder="feature-id", id="wt-feature")

    def on_mount(self) -> None:
        self.border_title = "Worktrees"
        self.query_one("#wt-create-row").display = False
        self._confirm_item: ListItem | None = None
        self._confirm_original: str = ""
        self._confirm_yes: bool = False
        self.refresh_worktrees()

    def content_height(self) -> int:
        """Return total visible item count for height calculation."""
        lv = self.query_one("#worktree-list", ListView)
        count = sum(1 for c in lv.children if c.display)
        if self.query_one("#wt-create-row").display:
            count += 1
        return count

    @property
    def _is_creating(self) -> bool:
        return self.query_one("#wt-create-row").display

    def _get_sentinel(self) -> ListItem | None:
        lv = self.query_one("#worktree-list", ListView)
        for child in lv.children:
            if getattr(child, "name", None) == NEW_WORKTREE_SENTINEL:
                return child
        return None

    def _show_inline_inputs(self) -> None:
        sentinel = self._get_sentinel()
        if sentinel:
            sentinel.display = False
        self.query_one("#wt-create-row").display = True
        self.query_one("#wt-scope", Input).focus()

    def _hide_inline_inputs(self) -> None:
        self.query_one("#wt-create-row").display = False
        self.query_one("#wt-scope", Input).value = ""
        self.query_one("#wt-feature", Input).value = ""
        sentinel = self._get_sentinel()
        if sentinel:
            sentinel.display = True

    def refresh_worktrees(self) -> None:
        """Refresh the worktree list from git + state."""
        self.query_one("#wt-create-row").display = False
        self.query_one("#wt-scope", Input).value = ""
        self.query_one("#wt-feature", Input).value = ""

        discovered = worktree.discover_worktrees()

        lv = self.query_one("#worktree-list", ListView)
        lv.remove_children()

        # Sort: root first, then alphabetical
        discovered.sort(key=lambda w: (not w.is_root, w.path.name))

        items: list[ListItem] = []
        for wt in discovered:
            if wt.is_root:
                display_name = f"{wt.branch or 'detached'} (root)"
                key = "__root__"
            else:
                display_name = wt.path.name
                key = wt.path.name

            item = ListItem(Label(display_name), name=key)
            item._wt_path = wt.path
            item._wt_branch = wt.branch
            item._wt_is_root = wt.is_root
            items.append(item)

        # Add "+ New worktree" action item at the end
        new_item = ListItem(
            Label("[#DA7756]+ New worktree[/]"),
            name=NEW_WORKTREE_SENTINEL,
        )
        new_item._wt_path = Path()
        new_item._wt_branch = None
        new_item._wt_is_root = False
        items.append(new_item)

        lv.mount_all(items)
        lv.index = 0

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Prevent selecting the sentinel by wrapping around."""
        if self._is_creating:
            self._hide_inline_inputs()
        if self._is_confirming:
            self._cancel_confirm()
        if event.item is None:
            return
        if event.item.name == NEW_WORKTREE_SENTINEL:
            self.post_message(WorktreeDeselected())
            return
        self.post_message(
            WorktreeHighlighted(
                name=event.item.name or "",
                path=getattr(event.item, "_wt_path", Path()),
                branch=getattr(event.item, "_wt_branch", None),
                is_root=getattr(event.item, "_wt_is_root", False),
            )
        )

    # --- Inline confirm ---

    @property
    def _is_confirming(self) -> bool:
        return self._confirm_item is not None

    def _show_confirm(self, item: ListItem) -> None:
        self._confirm_item = item
        label = item.query_one(Label)
        self._confirm_original = str(label.render())
        self._confirm_yes = False
        # Replace Label with Horizontal layout for right-aligned confirm
        label.remove()
        name = item.name or ""
        item.mount(
            Horizontal(
                Label(f"Delete [bold]{name}[/]?", classes="confirm-label"),
                Label("", classes="confirm-choices"),
            )
        )
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
            h.remove()
            self._confirm_item.mount(Label(self._confirm_original))
        self._confirm_item = None
        self._confirm_original = ""
        self._confirm_yes = False

    def _accept_confirm(self) -> None:
        if not self._confirm_item:
            return
        item = self._confirm_item
        if self._confirm_yes:
            self.post_message(
                self.DeleteWorktreeConfirmed(
                    name=item.name or "",
                    path=getattr(item, "_wt_path", Path()),
                    branch=getattr(item, "_wt_branch", None),
                )
            )
        self._cancel_confirm()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle enter key on a list item."""
        if event.item is None:
            return
        if event.item.name == NEW_WORKTREE_SENTINEL:
            self._show_inline_inputs()
            return
        # Focus session panel on enter
        try:
            self.app.query_one("#session-list").focus()
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wt-scope":
            self.query_one("#wt-feature", Input).focus()
            return
        if event.input.id == "wt-feature":
            scope = self.query_one("#wt-scope", Input).value.strip()
            feature = event.input.value.strip()
            if not scope or not feature:
                self.notify("Both scope and feature ID are required", severity="warning")
                return
            if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", scope):
                self.notify("Invalid scope (alphanumeric + hyphens)", severity="error")
                return
            if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$", feature):
                self.notify("Invalid feature ID", severity="error")
                return
            self._hide_inline_inputs()
            self.post_message(self.NewWorktreeRequested(scope=scope, feature_id=feature))

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
        if self._is_creating:
            if event.key == "escape":
                self._hide_inline_inputs()
                self.query_one("#worktree-list", ListView).focus()
                event.stop()
                return
            scope = self.query_one("#wt-scope", Input)
            feature = self.query_one("#wt-feature", Input)
            if event.key == "right" and scope.has_focus and scope.cursor_position >= len(scope.value):
                feature.focus()
                event.stop()
                return
            if event.key == "left" and feature.has_focus and feature.cursor_position == 0:
                scope.focus()
                event.stop()
                return

    def action_delete_worktree(self) -> None:
        if self._is_confirming:
            self._cancel_confirm()
            return
        lv = self.query_one("#worktree-list", ListView)
        if lv.highlighted_child is None:
            return
        item = lv.highlighted_child
        if item.name == NEW_WORKTREE_SENTINEL:
            return
        if getattr(item, "_wt_is_root", False):
            self.notify("Cannot delete root worktree", severity="warning")
            return
        self._show_confirm(item)
