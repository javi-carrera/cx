"""Settings panel for Claude Code launch options."""

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from cx import claude
from cx.colors import ACCENT, GREEN, RED

_CHANGE_GROUP = Binding.Group("Change", compact=True)


@dataclass
class Setting:
    """A single setting with a list of possible values."""

    name: str
    key: str
    values: list[str] = field(default_factory=list)
    index: int = 0

    @property
    def current(self) -> str:
        return self.values[self.index]

    def next(self) -> None:
        self.index = (self.index + 1) % len(self.values)

    def prev(self) -> None:
        self.index = (self.index - 1) % len(self.values)


DEFAULT_SETTINGS = [
    Setting("Permission mode", "permission_mode", ["plan", "dontAsk", "default", "acceptEdits", "auto", "bypassPermissions"], index=5),
    Setting("Model", "model", ["haiku", "sonnet", "opus"], index=2),
    Setting("Context", "context", ["200k", "1M"], index=1),
    Setting("Effort", "effort", ["low", "medium", "high", "max"], index=2),
    Setting("Verbose", "verbose", ["OFF", "ON"]),
    Setting("Debug", "debug", ["OFF", "ON"]),
]


def _format_value(setting: Setting) -> str:
    """Return a colorized setting value."""
    val = setting.current
    if val == "ON":
        return f"[{GREEN}]ON[/]"
    if val == "OFF":
        return f"[{RED}]OFF[/]"
    return f"[{ACCENT}]{val}[/]"


class SettingsPanel(Widget, can_focus=False):
    """Toggleable settings for Claude Code launches."""

    BORDER_TITLE = "Claude Code Settings"

    BINDINGS = [
        Binding("q", "app.quit", "Quit", show=True),
        Binding("s", "app.toggle_settings", "Settings", show=True),
        Binding("left", "cycle_prev", " ", show=True, priority=True, group=_CHANGE_GROUP),
        Binding("right", "cycle_next", " ", show=True, priority=True, group=_CHANGE_GROUP),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = [
            Setting(s.name, s.key, list(s.values), s.index)
            for s in DEFAULT_SETTINGS
        ]

    def compose(self) -> ComposeResult:
        yield Static(
            "Claude Code not installed",
            classes="empty-message",
            id="settings-empty",
        )
        yield ListView(id="settings-list")

    def on_mount(self) -> None:
        if not claude.IS_INSTALLED:
            # Inert: hide the list, show the "not installed" message, and
            # make the ListView unfocusable so `s` toggle never lands here
            # from anywhere (the session panel is also unfocusable, so this
            # is belt-and-suspenders).
            self.query_one("#settings-list", ListView).display = False
            self.query_one("#settings-list", ListView).can_focus = False
            return
        self.query_one("#settings-empty", Static).display = False
        self._rebuild_items()

    def content_height(self) -> int:
        if not claude.IS_INSTALLED:
            return 1
        return len(self._settings)

    def _rebuild_items(self) -> None:
        lv = self.query_one("#settings-list", ListView)
        lv.remove_children()
        items: list[ListItem] = []
        for setting in self._settings:
            item = ListItem(
                Horizontal(
                    Label(setting.name, classes="setting-name"),
                    Label(_format_value(setting), classes="setting-value"),
                ),
            )
            item._setting_key = setting.key
            items.append(item)
        lv.mount_all(items)
        lv.index = 0

    def _update_current_item(self) -> None:
        lv = self.query_one("#settings-list", ListView)
        if lv.index is None:
            return
        setting = self._settings[lv.index]
        item = lv.highlighted_child
        if item:
            value_label = item.query_one(".setting-value", Label)
            value_label.update(_format_value(setting))

    def action_cycle_prev(self) -> None:
        lv = self.query_one("#settings-list", ListView)
        if lv.index is None:
            return
        self._settings[lv.index].prev()
        self._update_current_item()

    def action_cycle_next(self) -> None:
        lv = self.query_one("#settings-list", ListView)
        if lv.index is None:
            return
        self._settings[lv.index].next()
        self._update_current_item()

    def get_setting(self, key: str) -> str:
        """Return the current value of a setting by key."""
        for s in self._settings:
            if s.key == key:
                return s.current
        return ""

    def get_claude_args(self) -> list[str]:
        """Build CLI args from the current settings."""
        args: list[str] = []
        pm = self.get_setting("permission_mode")
        if pm == "bypassPermissions":
            args.append("--dangerously-skip-permissions")
        else:
            args.extend(["--permission-mode", pm])
        model = self.get_setting("model")
        context = self.get_setting("context")
        if context == "1M":
            model = f"{model}[1m]"
        args.extend(["--model", model])
        args.extend(["--effort", self.get_setting("effort")])
        if self.get_setting("verbose") == "ON":
            args.append("--verbose")
        if self.get_setting("debug") == "ON":
            args.append("--debug")
        return args
