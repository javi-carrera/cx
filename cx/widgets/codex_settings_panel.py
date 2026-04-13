"""Settings panel for Codex CLI launch options."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from cx import codex
from cx.widgets.settings_panel import _CHANGE_GROUP, Setting, _format_value

CODEX_DEFAULT_SETTINGS = [
    Setting("Approval", "approval", ["untrusted", "on-request", "never", "full-auto", "bypass"], index=4),
    Setting("Sandbox", "sandbox", ["read-only", "workspace-write", "danger-full-access"], index=1),
    Setting("Model", "model", ["gpt-5.2", "gpt-5.3-codex", "gpt-5.4-mini", "gpt-5.4"], index=3),
    Setting("Reasoning", "reasoning", ["minimal", "low", "medium", "high", "xhigh"], index=3),
    Setting("Search", "search", ["OFF", "ON"]),
]


class CodexSettingsPanel(Widget, can_focus=False):
    """Toggleable settings for Codex CLI launches."""

    BORDER_TITLE = "Codex Settings"

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
            for s in CODEX_DEFAULT_SETTINGS
        ]

    def compose(self) -> ComposeResult:
        yield Static(
            "Codex not installed",
            classes="empty-message",
            id="codex-settings-empty",
        )
        yield ListView(id="codex-settings-list")

    def on_mount(self) -> None:
        if not codex.IS_INSTALLED:
            # See cx/widgets/settings_panel.py on_mount for rationale.
            self.query_one("#codex-settings-list", ListView).display = False
            self.query_one("#codex-settings-list", ListView).can_focus = False
            return
        self.query_one("#codex-settings-empty", Static).display = False
        self._rebuild_items()

    def content_height(self) -> int:
        if not codex.IS_INSTALLED:
            return 1
        return len(self._settings)

    def _rebuild_items(self) -> None:
        lv = self.query_one("#codex-settings-list", ListView)
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
        lv = self.query_one("#codex-settings-list", ListView)
        if lv.index is None:
            return
        setting = self._settings[lv.index]
        item = lv.highlighted_child
        if item:
            value_label = item.query_one(".setting-value", Label)
            value_label.update(_format_value(setting))

    def action_cycle_prev(self) -> None:
        lv = self.query_one("#codex-settings-list", ListView)
        if lv.index is None:
            return
        self._settings[lv.index].prev()
        self._update_current_item()

    def action_cycle_next(self) -> None:
        lv = self.query_one("#codex-settings-list", ListView)
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

    def get_codex_args(self) -> list[str]:
        """Build CLI args from the current settings."""
        args: list[str] = []
        approval = self.get_setting("approval")
        if approval == "bypass":
            args.append("--dangerously-bypass-approvals-and-sandbox")
        elif approval == "full-auto":
            args.append("--full-auto")
        else:
            args.extend(["-a", approval])
            args.extend(["-s", self.get_setting("sandbox")])
        args.extend(["-m", self.get_setting("model")])
        reasoning = self.get_setting("reasoning")
        # Always pass reasoning explicitly so the UI value matches what runs,
        # even if Codex's default ever differs from "high".
        args.extend(["-c", f'model_reasoning_effort="{reasoning}"'])
        # --search is incompatible with reasoning=minimal: the Codex API
        # rejects the combination with a 400 ("web_search tool cannot be
        # used with reasoning.effort 'minimal'"). Drop --search silently
        # rather than launching a session that fails immediately — the
        # user explicitly picked minimal, so honor that and notify them
        # that search was skipped.
        if self.get_setting("search") == "ON":
            if reasoning == "minimal":
                self.notify(
                    "--search disabled: not supported with reasoning=minimal",
                    severity="warning",
                    timeout=5,
                )
            else:
                args.append("--search")
        return args
