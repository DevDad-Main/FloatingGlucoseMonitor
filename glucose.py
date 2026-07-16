#!/usr/bin/env python3
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import keyring
import requests
from pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl
from pylibrelinkup.models.data import Trend

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, Header, Footer, Input, Label
from textual.screen import Screen

CONFIG_PATH = os.path.expanduser("~/.config/glucose-monitor/config.json")

TREND_GLYPH = {
    Trend.DOWN_FAST: "\u2B07",
    Trend.DOWN_SLOW: "\u2198",
    Trend.STABLE: "\u27A1",
    Trend.UP_SLOW: "\u2197",
    Trend.UP_FAST: "\u2B06",
}

TREND_LABEL = {
    Trend.DOWN_FAST: "dropping fast",
    Trend.DOWN_SLOW: "dropping",
    Trend.STABLE: "stable",
    Trend.UP_SLOW: "rising",
    Trend.UP_FAST: "rising fast",
}

LOW = 70
HIGH = 180
REFRESH_SECS = 60

DEFAULT_THEME = {
    "bg": "#1e1e2e",
    "fg": "#cdd6f4",
    "accent": "#f9e2af",
    "low": "#f38ba8",
    "high": "#fab387",
    "normal": "#a6e3a1",
    "muted": "#585b70",
    "surface": "#313244",
    "border": "#585b70",
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


KEYRING_SERVICE = "glucose-monitor"


def store_password(email: str, password: str):
    try:
        keyring.set_password(KEYRING_SERVICE, email, password)
    except Exception:
        pass


def get_password(email: str) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, email)
    except Exception:
        return None


def color_for(val_mgdl: int, theme: dict) -> str:
    if val_mgdl < LOW:
        return theme.get("low", DEFAULT_THEME["low"])
    elif val_mgdl > HIGH:
        return theme.get("high", DEFAULT_THEME["high"])
    return theme.get("normal", DEFAULT_THEME["normal"])



DIGITS = {
    '0': ["███", "█ █", "█ █", "█ █", "███"],
    '1': ["  █", "  █", "  █", "  █", "  █"],
    '2': ["███", "  █", "███", "█  ", "███"],
    '3': ["███", "  █", "███", "  █", "███"],
    '4': ["█ █", "█ █", "███", "  █", "  █"],
    '5': ["███", "█  ", "███", "  █", "███"],
    '6': ["███", "█  ", "███", "█ █", "███"],
    '7': ["███", "  █", "  █", "  █", "  █"],
    '8': ["███", "█ █", "███", "█ █", "███"],
    '9': ["███", "█ █", "███", "  █", "███"],
    '.': ["   ", "   ", "   ", "  █", "  █"],
}


def make_big_text(text: str) -> str:
    lines = [""] * 5
    for ch in text:
        pattern = DIGITS.get(ch, DIGITS['0'])
        for i in range(5):
            lines[i] += pattern[i] + " "
    return "\n".join(lines)


def make_chart(values, timestamps=None):
    if not values or len(values) < 2:
        return ""
    height = 4
    n = len(values)
    raw_mn, raw_mx = min(values), max(values)
    mn, mx = int(raw_mn), int(raw_mx)
    rng = mx - mn if mx != mn else 1

    def value_row(v):
        return round((mx - int(v)) / rng * (height - 1))

    cols = [(value_row(v), int(v)) for v in values]

    grid = [[' ' for _ in range(n)] for _ in range(height)]

    for i in range(n - 1):
        r, _ = cols[i]
        nr, _ = cols[i + 1]
        if nr < r:
            grid[r][i] = '╱'
        elif nr > r:
            grid[r][i] = '╲'
        else:
            grid[r][i] = '─'

    grid[cols[0][0]][0] = '·'
    grid[cols[-1][0]][n - 1] = '·'

    label_width = max(len(str(mx)), len(str(mn)))
    y_labels = []
    for r in range(height):
        v = round(mx - (r / (height - 1)) * rng) if rng > 0 else mx
        y_labels.append(f"{v}".rjust(label_width))

    lines = []
    for r in range(height):
        lines.append(y_labels[r] + " " + ''.join(grid[r]))

    if timestamps and len(timestamps) == n:
        times = []
        for t in timestamps:
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            times.append(t.astimezone().strftime("%H:%M"))

        tick_cols = []
        step = max(1, n // 5)
        for i in range(0, n, step):
            tick_cols.append(i)

        x_line = " " * (label_width + 1)
        col = 0
        for i in tick_cols:
            label = times[i]
            if col <= i:
                gap = i - col
                x_line += " " * gap + label
                col = i + len(label)
        lines.append(x_line)

    return '\n'.join(lines)


REGION_HELP = "Options: US, EU, EU2, AE, AP, AU, CA, DE, FR, JP, LA, RU (Poland → EU)"


class LoginScreen(Screen):
    def compose(self):
        yield Container(
            Static("Glucose Monitor", classes="title"),
            Static("Enter your LibreLinkUp credentials", classes="subtitle"),
            Label("Email", classes="field_label"),
            Input(placeholder="your@email.com", id="email_input"),
            Label("Password", classes="field_label"),
            Input(placeholder="password", password=True, id="pass_input"),
            Label(f"Region  {REGION_HELP}", classes="field_label"),
            Input(placeholder="EU", value="EU", id="region_input"),
            Static("", id="login_error"),
            Static("Ctrl+S to save  |  Ctrl+Q to quit", id="login_hint"),
            id="login_box",
        )

    def on_mount(self):
        self._apply_theme()
        self.query_one("#email_input", Input).focus()

    def _apply_theme(self):
        t = getattr(self.app, "_theme", DEFAULT_THEME)
        bg = t.get("bg", "#1e1e2e")
        fg = t.get("fg", "#cdd6f4")
        surface = t.get("surface", "#313244")
        accent = t.get("accent", "#f9e2af")
        muted = t.get("muted", "#585b70")
        self.styles.border = ("solid", accent)
        for w in self.query(".title"):
            w.styles.color = accent
        for w in self.query(".subtitle"):
            w.styles.color = muted
        for w in self.query("#login_hint"):
            w.styles.color = muted
        for w in self.query(".field_label"):
            w.styles.color = muted
        for inp in self.query(Input):
            inp.styles.background = surface
            inp.styles.color = fg
            inp.styles.border = ("solid", muted)

    def on_input_submitted(self, event: Input.Submitted):
        ids = ["email_input", "pass_input", "region_input"]
        for i, sel in enumerate(ids):
            if event.input.id == sel:
                if i < len(ids) - 1:
                    self.query_one(f"#{ids[i + 1]}", Input).focus()
                else:
                    self._do_save()

    def on_input_focused(self, event: Input.Focused):
        self.query_one("#login_error", Static).update("")

    def on_key(self, event):
        if event.key == "ctrl+s":
            self._do_save()
            return
        if event.key == "ctrl+q":
            self.app.exit()
            return

    def _do_save(self):
        email = self.query_one("#email_input", Input).value.strip()
        password = self.query_one("#pass_input", Input).value
        region = self.query_one("#region_input", Input).value.strip().upper()
        if not email or not password:
            self.query_one("#login_error", Static).update("Email and password required")
            return
        store_password(email, password)
        cfg = {**self.app.config, "email": email, "region": region}
        cfg.pop("password", None)
        save_config(cfg)
        self.app.config = cfg
        self.app.pop_screen()
        self.app.start_glucose()


class GlucoseWidget(Static):
    value_mgdl = reactive(None)
    value_mmol = reactive(None)
    trend = reactive(None)
    timestamp = reactive(None)
    use_mmol = reactive(False)
    history = reactive(list)
    show_graph = reactive(False)
    history_times = reactive(list)

    def compose(self):
        with Vertical(classes="main"):
            with Horizontal(classes="big_row"):
                yield Static(make_big_text("88"), id="big_value", classes="big_value")
                yield Static("", id="trend", classes="trend")
            yield Static("", id="trend_label", classes="trend_label")
            with Horizontal(classes="info"):
                yield Static("--", id="timeago", classes="timeago")
                yield Static("mg/dL", id="unit", classes="unit")
            yield Static("", id="chart", classes="chart")

    def on_mount(self):
        self.styles.width = "100%"
        self.styles.height = "100%"
        self._apply_theme()

    def _apply_theme(self):
        t = getattr(self.app, "_theme", DEFAULT_THEME)
        self.styles.background = t.get("bg", "#1e1e2e")
        for w in self.query(".trend_label"):
            w.styles.color = t.get("muted", "#585b70")
        for w in self.query(".timeago"):
            w.styles.color = t.get("muted", "#585b70")
        for w in self.query(".unit"):
            w.styles.color = t.get("muted", "#585b70")

    def _safe(self, wid):
        try:
            return self.query_one(f"#{wid}", Static)
        except Exception:
            return None

    def watch_value_mgdl(self, val):
        if val is None:
            w = self._safe("big_value")
            if w:
                w.update("")
            return
        t = getattr(self.app, "_theme", DEFAULT_THEME)
        display = f"{self.value_mmol:.1f}" if self.use_mmol and self.value_mmol is not None else str(val)
        clr = color_for(val, t)
        w = self._safe("big_value")
        if w:
            w.update(make_big_text(display))
            w.styles.color = clr

        trend_char = TREND_GLYPH.get(self.trend, "")
        w = self._safe("trend")
        if w:
            w.update(trend_char)
            w.styles.color = clr

        label = TREND_LABEL.get(self.trend, "")
        w = self._safe("trend_label")
        if w:
            w.update(label)
            w.styles.color = t.get("muted", "#585b70")

    def watch_timestamp(self, ts):
        w = self._safe("timeago")
        if not w:
            return
        if ts is None:
            w.update("--")
            return
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            text = "just now"
        elif mins < 60:
            text = f"{mins}m ago"
        else:
            text = f"{mins // 60}h{mins % 60}m ago"
        w.update(text)

    def watch_use_mmol(self, val):
        w = self._safe("unit")
        if w:
            w.update("mmol/L" if val else "mg/dL")
        if self.value_mgdl is not None:
            self.watch_value_mgdl(self.value_mgdl)

    def watch_history(self, vals):
        if self.show_graph:
            self._render_chart()

    def watch_show_graph(self, val):
        self._render_chart()

    def _render_chart(self):
        w = self._safe("chart")
        if not w:
            return
        if self.show_graph and self.history and len(self.history) >= 2:
            w.update(make_chart(self.history, self.history_times))
            w.styles.display = "block"
        else:
            w.update("")
            w.styles.display = "none"


class GlucoseApp(App):
    CSS = """
    Screen {
        background: #1e1e2e;
        border: solid #585b70;
        padding: 0;
    }

    #login_box {
        align: center middle;
        width: 100%;
        padding: 1 4;
        border: none;
    }

    .title {
        text-style: bold;
        color: #f9e2af;
        content-align: center middle;
        width: 100%;
        margin-bottom: 1;
    }

    .subtitle {
        color: #585b70;
        content-align: center middle;
        width: 100%;
        margin-bottom: 1;
    }

    .field_label {
        color: #585b70;
        margin-top: 1;
        margin-bottom: 0;
    }

    Input {
        background: #313244;
        color: #cdd6f4;
        border: solid #585b70;
        margin-bottom: 0;
        width: 100%;
    }

    Input:focus {
        border: solid #f9e2af;
    }

    #login_error {
        color: #f38ba8;
        margin-top: 1;
        content-align: center middle;
        width: 100%;
    }

    #login_hint {
        color: #585b70;
        margin-top: 1;
        content-align: center middle;
        width: 100%;
    }

    #glucose_box {
        layout: vertical;
        align: center middle;
        width: 100%;
        height: 100%;
    }

    .main {
        align: center middle;
        width: 100%;
        height: 100%;
    }

    .big_row {
        align: center middle;
        height: auto;
    }

    .trend {
        text-style: bold;
        content-align: center middle;
        height: auto;
        margin-left: 1;
    }

    .big_value {
        text-style: bold;
        content-align: center middle;
    }

    .chart {
        color: #f9e2af;
        content-align: center middle;
        width: 100%;
        height: 5;
        display: none;
    }

    .info {
        align: center middle;
        height: 1;
    }

    .trend_label {
        color: #585b70;
        content-align: center middle;
        width: 100%;
        height: 1;
    }

    .timeago {
        color: #585b70;
        margin-right: 2;
    }

    .unit {
        color: #585b70;
    }

    Header { display: none; }
    Footer { display: none; }
    """

    BINDINGS = [
        ("u", "toggle_unit", "Unit"),
        ("r", "refresh", "Refresh"),
        ("g", "toggle_graph", "Graph"),
        ("l", "login", "Login"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._theme = {**DEFAULT_THEME, **(config.get("theme") or {})}
        self.client = None
        self._running = True

    def compose(self):
        yield Header(show_clock=False)
        yield Container(id="glucose_box")
        yield Footer()

    def on_mount(self):
        self.screen.styles.background = self._theme.get("bg", "#1e1e2e")
        self.screen.styles.border = ("solid", self._theme.get("accent", "#f9e2af"))
        email = self.config.get("email")
        if email:
            pw = self.config.get("password")
            if pw:
                store_password(email, pw)
                self.config.pop("password", None)
                save_config(self.config)
        if not email:
            self.push_screen(LoginScreen())
        else:
            self.start_glucose()

    def start_glucose(self):
        box = self.query_one("#glucose_box")
        box.remove_children()
        gw = GlucoseWidget()
        box.mount(gw)
        self._glucose = gw
        threading.Thread(target=self._fetch_loop, daemon=True).start()

    def _fetch_loop(self):
        region = self.config.get("region", "US")
        try:
            api_url_enum = APIUrl[region.upper()]
        except KeyError:
            api_url_enum = APIUrl.US
        email = self.config.get("email", "")
        password = get_password(email) or ""
        self.client = PyLibreLinkUp(
            email=email,
            password=password,
            api_url=api_url_enum,
        )
        backoff = REFRESH_SECS
        while self._running:
            try:
                self.client.authenticate()
                patients = self.client.get_patients()
                if not patients:
                    self.call_from_thread(self._set_status, "No patients found - share from LibreLink app to LibreLinkUp")
                    time.sleep(REFRESH_SECS)
                    continue
                pid = patients[0].patient_id
                latest = self.client.latest(pid)
                if latest:
                    self.call_from_thread(self._update_display, latest, pid)
                    backoff = REFRESH_SECS
                else:
                    self.call_from_thread(self._set_status, "No glucose data")
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                if code == 430:
                    msg = f"Rate limited, retrying in {backoff}s"
                    self.call_from_thread(self._set_status, msg)
                    for _ in range(backoff):
                        if not self._running:
                            return
                        time.sleep(1)
                    backoff = min(backoff * 2, 600)
                    continue
                else:
                    self.call_from_thread(self._set_status, f"HTTP {code}")
            except Exception as e:
                self.call_from_thread(self._set_status, str(e)[:80])

            for _ in range(REFRESH_SECS):
                if not self._running:
                    return
                time.sleep(1)

    def _update_display(self, latest, pid):
        gw = self._glucose
        gw.value_mgdl = latest.value_in_mg_per_dl
        gw.value_mmol = latest.value
        gw.trend = latest.trend
        gw.timestamp = latest.timestamp
        try:
            graph_data = self.client.graph(pid)
            if graph_data:
                gw.history = [g.value_in_mg_per_dl for g in graph_data[-40:]]
                gw.history_times = [g.timestamp for g in graph_data[-40:]]
        except Exception:
            pass

    def _set_status(self, msg):
        if msg and hasattr(self, "_glucose"):
            try:
                w = self._glucose.query_one("#trend_label", Static)
                w.update(msg)
            except Exception:
                pass

    def action_login(self):
        self._running = False
        self.push_screen(LoginScreen())

    def action_toggle_graph(self):
        if hasattr(self, "_glucose"):
            self._glucose.show_graph = not self._glucose.show_graph

    def action_toggle_unit(self):
        if hasattr(self, "_glucose"):
            self._glucose.use_mmol = not self._glucose.use_mmol

    def action_refresh(self):
        if hasattr(self, "_glucose"):
            self._glucose.value_mgdl = None
            self._glucose.history = []
        if self._running:
            threading.Thread(target=self._fetch_loop, daemon=True).start()

    def action_quit(self):
        self._running = False
        self.exit()

    def on_unmount(self):
        self._running = False


def main():
    config = load_config()
    app = GlucoseApp(config)
    app.run()


if __name__ == "__main__":
    main()
