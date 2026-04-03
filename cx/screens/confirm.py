"""Confirmation modal dialog."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmScreen(ModalScreen[bool]):
    """A yes/no confirmation dialog."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, message: str, confirm_label: str = "Delete") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-container"):
            yield Static("Confirm", classes="modal-title")
            yield Static(self._message)
            with Horizontal(classes="modal-buttons"):
                yield Button(self._confirm_label, variant="error", id="confirm-yes")
                yield Button("Cancel", variant="default", id="confirm-no")

    @on(Button.Pressed, "#confirm-yes")
    def on_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def on_cancel_btn(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
