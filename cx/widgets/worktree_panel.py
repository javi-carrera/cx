"""Git worktree panel for the TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView

from cx import worktree
from cx.colors import ACCENT, DANGER

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
    """Panel showing git worktrees."""

    BORDER_TITLE = "Worktrees"

    BINDINGS = [
        Binding("q", "app.quit", "Quit", show=True),
        Binding("d", "delete_worktree", "Delete", show=True),
        Binding("tab", "next_pane", "Sessions", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=True),
        # Enter bindings: two bindings with different labels, gated by
        # check_action so only one shows at a time — last in the footer.
        Binding("enter", "enter_select", "Select", show=True),
        Binding("enter", "enter_accept", "Accept", show=True),
    ]

    class NewWorktreeRequested(Message):
        """Request to create a new worktree."""

        def __init__(self, scope: str, feature_id: str) -> None:
            super().__init__()
            self.scope = scope
            self.feature_id = feature_id

    class DeleteWorktreeConfirmed(Message):
        """Confirmed deletion of a worktree."""

        def __init__(
            self, name: str, path: Path, branch: str | None, *, force: bool = False,
        ) -> None:
            super().__init__()
            self.wt_name = name
            self.path = path
            self.branch = branch
            self.force = force

    def compose(self) -> ComposeResult:
        yield ListView(id="worktree-list")
        with Horizontal(id="wt-create-row", classes="inline-create"):
            yield Input(placeholder="scope", id="wt-scope")
            yield Input(placeholder="feature", id="wt-feature")

    def on_mount(self) -> None:
        self.border_title = "Worktrees"
        self.query_one("#wt-create-row").display = False
        self._confirm_item: ListItem | None = None
        self._confirm_original: str = ""
        self._confirm_yes: bool = False
        self._confirm_force: bool = False
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

    @property
    def is_modal(self) -> bool:
        """True when the panel has a modal UI element (create input or confirm)."""
        return self._is_creating or self._is_confirming

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Gate footer visibility based on modal state and highlight."""
        on_sentinel = self._highlight_is_sentinel()
        if action == "delete_worktree":
            # Hidden during modal and on the "+ New worktree" sentinel.
            return not self.is_modal and not on_sentinel
        if action == "next_pane":
            # Hidden during modal (so the tab-Sessions label doesn't mislead
            # while we cycle between scope/feature inputs) and when on the
            # sentinel (app.action_focus_next already no-ops there).
            return not self.is_modal and not on_sentinel
        if action == "cancel":
            return self.is_modal
        if action == "enter_select":
            # Show "Select" in the selecting state (not modal).
            return not self.is_modal
        if action == "enter_accept":
            # Show "Accept" during creating or confirming.
            return self.is_modal
        return True

    def _highlight_is_sentinel(self) -> bool:
        """True if the currently highlighted list item is the "+ New" sentinel."""
        try:
            lv = self.query_one("#worktree-list", ListView)
        except Exception:
            return False
        child = lv.highlighted_child
        return child is not None and child.name == NEW_WORKTREE_SENTINEL

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

        new_item = ListItem(
            Label(f"[{ACCENT}]+ New worktree[/]"),
            name=NEW_WORKTREE_SENTINEL,
        )
        new_item._wt_path = Path()
        new_item._wt_branch = None
        new_item._wt_is_root = False
        items.append(new_item)

        lv.mount_all(items)
        lv.index = 0

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Cancel any modal state and notify the app about the new highlight."""
        if self._is_creating:
            self._hide_inline_inputs()
        if self._is_confirming:
            self._cancel_confirm()
        # Footer visibility depends on whether we're on the sentinel, so
        # refresh when the highlight moves.
        self.refresh_bindings()
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

    @property
    def _is_confirming(self) -> bool:
        return self._confirm_item is not None

    def _show_confirm(self, item: ListItem) -> None:
        self._confirm_item = item
        label = item.query_one(Label)
        self._confirm_original = str(label.render())
        self._confirm_yes = False
        label.remove()
        name = item.name or ""
        item.mount(
            Horizontal(
                Label(f"Delete [bold]{name}[/]?", classes="confirm-label"),
                Label("", classes="confirm-choices"),
            )
        )
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
            h.remove()
            self._confirm_item.mount(Label(self._confirm_original))
        self._confirm_item = None
        self._confirm_original = ""
        self._confirm_yes = False
        self._confirm_force = False
        self.refresh_bindings()

    def show_force_confirm(self, wt_name: str, reason: str = "Branch not merged.") -> None:
        """Show a force-delete confirmation with a given reason."""
        lv = self.query_one("#worktree-list", ListView)
        for child in lv.children:
            if child.name == wt_name:
                self._confirm_force = True
                self._confirm_item = child
                label = child.query_one(Label)
                self._confirm_original = str(label.render())
                self._confirm_yes = False
                label.remove()
                child.mount(
                    Horizontal(
                        Label(
                            f"[bold {DANGER}]{reason}[/] Force delete?",
                            classes="confirm-label",
                        ),
                        Label("", classes="confirm-choices"),
                    )
                )
                self._render_confirm()
                return

    def _accept_confirm(self) -> None:
        if not self._confirm_item:
            return
        item = self._confirm_item
        force = self._confirm_force
        if self._confirm_yes:
            self.post_message(
                self.DeleteWorktreeConfirmed(
                    name=item.name or "",
                    path=getattr(item, "_wt_path", Path()),
                    branch=getattr(item, "_wt_branch", None),
                    force=force,
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
        # Delegate to the app's tab-cycle logic so Enter lands on whichever
        # session pane is actually available (Claude if installed, else
        # Codex), and respects the user's last-chosen side.
        self.app.action_focus_next()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wt-scope":
            self.query_one("#wt-feature", Input).focus()
            return
        if event.input.id == "wt-feature":
            scope = self.query_one("#wt-scope", Input).value.strip()
            feature = event.input.value.strip()
            try:
                worktree.validate_scope(scope)
                worktree.validate_feature_id(feature)
            except ValueError as e:
                self.notify(str(e), severity="error")
                return
            self._hide_inline_inputs()
            self.query_one("#worktree-list", ListView).focus()
            self.post_message(self.NewWorktreeRequested(scope=scope, feature_id=feature))

    def on_key(self, event) -> None:
        if self._is_confirming:
            # Directional arrows: left → No (False), right → Yes (True).
            # Noop when already on that side.
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
        if self._is_creating:
            if event.key == "escape":
                self._hide_inline_inputs()
                self.query_one("#worktree-list", ListView).focus()
                event.stop()
                return
            scope = self.query_one("#wt-scope", Input)
            feature = self.query_one("#wt-feature", Input)
            if event.key == "tab":
                # Tab cycles between the two fields while creating. The
                # panel's priority `next_pane` binding is disabled during
                # modal via check_action, so the key arrives here.
                if scope.has_focus:
                    feature.focus()
                else:
                    scope.focus()
                event.stop()
                return
            if event.key == "right" and scope.has_focus and scope.cursor_position >= len(scope.value):
                feature.focus()
                event.stop()
                return
            if event.key == "left" and feature.has_focus and feature.cursor_position == 0:
                scope.focus()
                event.stop()
                return

    def action_next_pane(self) -> None:
        """Tab action: forward to app focus_next. Disabled during modal."""
        self.app.action_focus_next()

    def action_enter_select(self) -> None:
        """Enter action: activate the highlighted list item. Delegates to the
        ListView's built-in select-cursor action, which posts ListView.Selected
        and triggers on_list_view_selected."""
        self.query_one("#worktree-list", ListView).action_select_cursor()

    async def action_enter_accept(self) -> None:
        """Enter action during modal: accept confirm or submit focused input."""
        if self._is_confirming:
            self._accept_confirm()
            return
        inp = self.app.focused
        if isinstance(inp, Input):
            await inp.action_submit()

    def action_cancel(self) -> None:
        """Escape action: cancel modal (create/confirm)."""
        if self._is_confirming:
            self._cancel_confirm()
            return
        if self._is_creating:
            self._hide_inline_inputs()
            self.query_one("#worktree-list", ListView).focus()
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
