"""Settings panel — toggleable pane for Claude Code launch options."""

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView


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
    Setting("Permission mode", "permission_mode", ["bypassPermissions", "auto", "acceptEdits", "plan", "default", "dontAsk"]),
    Setting("Model", "model", ["opus", "sonnet", "haiku"]),
    Setting("Context", "context", ["1M", "200k"]),
    Setting("Effort", "effort", ["high", "low", "medium", "max"]),
    Setting("Verbose", "verbose", ["OFF", "ON"]),
    Setting("Debug", "debug", ["OFF", "ON"]),
]


def _format_value(setting: Setting) -> str:
    """Format a setting value with color."""
    val = setting.current
    if val == "ON":
        return "[#98c379]ON[/]"
    if val == "OFF":
        return "[#e06c75]OFF[/]"
    return f"[#DA7756]{val}[/]"


class SettingsPanel(Widget, can_focus=False):
    """Vertical list of toggleable settings for Claude Code launches."""

    BORDER_TITLE = "Settings"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = [
            Setting(s.name, s.key, list(s.values), s.index)
            for s in DEFAULT_SETTINGS
        ]

    def compose(self) -> ComposeResult:
        yield ListView(id="settings-list")

    def on_mount(self) -> None:
        self.border_title = "Settings"
        self._rebuild_items()

    def content_height(self) -> int:
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

    def on_key(self, event) -> None:
        lv = self.query_one("#settings-list", ListView)
        if not lv.has_focus or lv.index is None:
            return
        if event.key == "right":
            self._settings[lv.index].next()
            self._update_current_item()
            event.stop()
        elif event.key == "left":
            self._settings[lv.index].prev()
            self._update_current_item()
            event.stop()

    def get_setting(self, key: str) -> str:
        """Get the current value of a setting by key."""
        for s in self._settings:
            if s.key == key:
                return s.current
        return ""

    def get_claude_args(self) -> list[str]:
        """Build CLI args from current settings."""
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
