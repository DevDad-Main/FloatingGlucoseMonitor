#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import timezone
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
    Trend.DOWN_FAST: "\u2b07",
    Trend.DOWN_SLOW: "\u2198",
    Trend.STABLE: "\u27a1",
    Trend.UP_SLOW: "\u2197",
    Trend.UP_FAST: "\u2b06",
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
REFRESH_SECS = 60  # Current glucose every 1 minute
GRAPH_REFRESH_SECS = 300  # Graph every 5 minutes

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
    "0": ["███", "█ █", "█ █", "█ █", "███"],
    "1": ["  █", "  █", "  █", "  █", "  █"],
    "2": ["███", "  █", "███", "█  ", "███"],
    "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"],
    "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"],
    "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"],
    "9": ["███", "█ █", "███", "  █", "███"],
    ".": ["   ", "   ", "   ", "   ", " · "],
}


def make_big_text(text: str) -> str:
    lines = [""] * 5
    for ch in text:
        pattern = DIGITS.get(ch, DIGITS["0"])
        for i in range(5):
            lines[i] += pattern[i] + " "
    return "\n".join(lines)


def make_chart(values, timestamps=None):
    if not values or len(values) < 2:
        return ""
    height = 8
    n = len(values)
    raw_mn, raw_mx = min(values), max(values)
    mn, mx = int(raw_mn), int(raw_mx)
    rng = mx - mn if mx != mn else 1

    def value_row(v):
        return round((mx - int(v)) / rng * (height - 1))

    grid = [[" " for _ in range(n)] for _ in range(height)]

    for i in range(n - 1):
        r = value_row(values[i])
        nr = value_row(values[i + 1])
        if nr < r:
            grid[r][i] = "╱"
        elif nr > r:
            grid[r][i] = "╲"
        else:
            grid[r][i] = "─"

    r_last = value_row(values[-1])
    grid[r_last][n - 1] = "•"

    label_width = max(len(str(mx)), len(str(mn)))
    y_labels = []
    for r in range(height):
        v = round(mx - (r / (height - 1)) * rng) if rng > 0 else mx
        y_labels.append(f"{v}".rjust(label_width))

    lines = []
    for r in range(height):
        lines.append(y_labels[r] + " " + "".join(grid[r]))

    if timestamps and len(timestamps) == n:
        times = [t.astimezone().strftime("%H:%M") for t in timestamps]
        tick_step = max(1, n // 6)
        x_buf = " " * (label_width + 1)
        col = 0
        for idx in range(0, n, tick_step):
            label = times[idx]
            if col <= idx:
                gap = idx - col
                x_buf += " " * gap + label
                col = idx + len(label)
        lines.append(x_buf)

    return "\n".join(lines)


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
    use_mmol = reactive(False)
    history = reactive(list)
    show_graph = reactive(False)
    history_times = reactive(list)

    def compose(self):
        with Vertical(classes="main"):
            with Horizontal(classes="big_row"):
                yield Static(make_big_text("88"), id="big_value", classes="big_value")
            with Horizontal(classes="compact_row"):
                yield Static("", id="compact_val", classes="compact_val")
            yield Static("", id="trend_label", classes="trend_label")
            yield Static("", id="chart", classes="chart")

    def on_mount(self):
        self.styles.width = "100%"
        self._apply_theme()

    def _apply_theme(self):
        t = getattr(self.app, "_theme", DEFAULT_THEME)
        self.styles.background = t.get("bg", "#1e1e2e")
        for w in self.query(".trend_label"):
            w.styles.color = t.get("muted", "#585b70")
        for w in self.query(".chart"):
            w.styles.color = t.get("accent", "#f9e2af")

    def _safe(self, wid):
        try:
            return self.query_one(f"#{wid}", Static)
        except Exception:
            return None

    def watch_value_mgdl(self, val):
        if val is None:
            return
        t = getattr(self.app, "_theme", DEFAULT_THEME)
        display = (
            f"{self.value_mmol:.1f}"
            if self.use_mmol and self.value_mmol is not None
            else str(val)
        )
        clr = color_for(val, t)
        unit = "mmol/L" if self.use_mmol else "mg/dL"
        trend_char = TREND_GLYPH.get(self.trend, "")
        label = TREND_LABEL.get(self.trend, "")

        w = self._safe("big_value")
        if w:
            w.update(make_big_text(display))
            w.styles.color = clr

        w = self._safe("compact_val")
        if w:
            w.update(f"{display} {trend_char}  {unit}  {label}")
            w.styles.color = clr

        w = self._safe("trend_label")
        if w:
            info = f"{display} {trend_char}  {unit}  {label}"
            w.update(info.lstrip())
            w.styles.color = t.get("muted", "#585b70")

    def watch_use_mmol(self, val):
        if self.value_mgdl is not None:
            self.watch_value_mgdl(self.value_mgdl)

    def watch_history(self, vals):
        if self.show_graph:
            self._render_chart()

    def watch_show_graph(self, val):
        big_row = self.query_one(".big_row")
        compact_row = self.query_one(".compact_row")
        trend_label = self.query_one("#trend_label")
        chart = self.query_one("#chart")
        if val:
            big_row.styles.display = "none"
            compact_row.styles.display = "block"
            trend_label.styles.display = "none"
            chart.styles.display = "block"
            self._render_chart()
        else:
            big_row.styles.display = "block"
            compact_row.styles.display = "none"
            trend_label.styles.display = "block"
            chart.styles.display = "none"

    def _render_chart(self):
        w = self._safe("chart")
        if not w:
            return
        if self.show_graph and self.history and len(self.history) >= 2:
            w.update(make_chart(self.history, self.history_times))
        else:
            w.update("")


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
    }

    .main {
        align: center middle;
        width: 100%;
    }

    .big_row {
        align: center middle;
        height: auto;
    }

    .compact_row {
        align: center middle;
        height: 1;
        display: none;
    }

    .compact_val {
        text-style: bold;
        content-align: center middle;
    }

    .big_value {
        text-style: bold;
        content-align: center middle;
    }

    .chart {
        color: #f9e2af;
        content-align: center middle;
        width: 100%;
        height: 10;
        display: none;
    }

    .trend_label {
        color: #585b70;
        content-align: center middle;
        width: 100%;
        height: 1;
    }

    Header { display: none; }
    Footer { display: none; }
    """

    BINDINGS = [
        ("u", "toggle_unit", "Unit"),
        ("r", "refresh", "Refresh"),
        ("g", "toggle_graph", "Graph"),
        ("l", "login", "Login"),
        ("t", "reload_theme", "Theme"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._theme = {**DEFAULT_THEME, **(config.get("theme") or {})}
        self.client = None
        self._running = True
        self._fetch_in_progress = False
        self._last_graph_fetch = 0
        self._config_mtime = self._get_config_mtime()

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
        self._fetch_in_progress = True
        self._set_status("fetching\u2026")
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
        pid = None

        # A value of 0 means the graph will be fetched immediately
        # after the first successful glucose reading.
        last_graph_fetch = 0.0

        # Authenticate and retrieve the patient once before polling.
        try:
            self.call_from_thread(
                self._set_status,
                "Authenticating…",
            )

            self.client.authenticate()
            patients = self.client.get_patients()

            if not patients:
                self.call_from_thread(
                    self._set_status,
                    "No patients found - share from LibreLink app to LibreLinkUp",
                )
                self._fetch_in_progress = False
                return

            pid = patients[0].patient_id

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"

            self.call_from_thread(
                self._set_status,
                f"Authentication failed: HTTP {code}",
            )

            self._fetch_in_progress = False
            return

        except Exception as e:
            self.call_from_thread(
                self._set_status,
                f"Authentication failed: {str(e)[:60]}",
            )

            self._fetch_in_progress = False
            return

        while self._running:
            self._fetch_in_progress = True

            try:
                latest = self.client.latest(pid)

                if latest:
                    # Only update the current glucose reading here.
                    self.call_from_thread(
                        self._update_display,
                        latest,
                    )

                    backoff = REFRESH_SECS

                    # Fetch graph history less frequently.
                    now = time.monotonic()

                    if now - last_graph_fetch >= GRAPH_REFRESH_SECS:
                        try:
                            graph_data = self.client.graph(pid)

                            if graph_data:
                                self.call_from_thread(
                                    self._update_graph,
                                    graph_data,
                                )

                                last_graph_fetch = now

                        except requests.exceptions.HTTPError as graph_error:
                            graph_code = (
                                graph_error.response.status_code
                                if graph_error.response is not None
                                else None
                            )

                            # Do not let a graph error stop the current
                            # glucose reading from being displayed.
                            if graph_code in (429, 430):
                                self.call_from_thread(
                                    self._set_status,
                                    "Graph request rate limited",
                                )

                        except requests.exceptions.RequestException:
                            pass

                        except Exception:
                            pass

                else:
                    self.call_from_thread(
                        self._set_status,
                        "No glucose data",
                    )

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else None

                if code == 401:
                    self.call_from_thread(
                        self._set_status,
                        "Session expired, signing in again…",
                    )

                    try:
                        self.client.authenticate()
                        latest = self.client.latest(pid)

                        if latest:
                            self.call_from_thread(
                                self._update_display,
                                latest,
                            )

                            backoff = REFRESH_SECS

                    except Exception as auth_error:
                        self.call_from_thread(
                            self._set_status,
                            f"Re-authentication failed: {str(auth_error)[:60]}",
                        )

                elif code in (429, 430):
                    for remaining in range(backoff, 0, -1):
                        if not self._running:
                            return

                        self.call_from_thread(
                            self._set_status,
                            f"Rate limited, retry in {remaining}s",
                        )

                        time.sleep(1)

                    backoff = min(backoff * 2, 600)

                    self.call_from_thread(
                        self._set_status,
                        "Retrying…",
                    )

                    continue

                else:
                    display_code = code if code is not None else "?"

                    self.call_from_thread(
                        self._set_status,
                        f"HTTP {display_code}",
                    )

            except requests.exceptions.RequestException as e:
                self.call_from_thread(
                    self._set_status,
                    f"Network error: {str(e)[:60]}",
                )

            except Exception as e:
                self.call_from_thread(
                    self._set_status,
                    str(e)[:80],
                )

            finally:
                self._fetch_in_progress = False

            # Current glucose refresh interval.
            for _ in range(REFRESH_SECS):
                if not self._running:
                    return

                self._reload_theme_if_changed()
                time.sleep(1)

    def _update_display(self, latest):
        gw = self._glucose

        gw.value_mgdl = latest.value_in_mg_per_dl
        gw.value_mmol = latest.value_in_mg_per_dl / 18.0182
        gw.trend = latest.trend

    def _update_graph(self, graph_data):
        gw = self._glucose
        recent = graph_data[-40:]

        gw.history = [reading.value_in_mg_per_dl for reading in recent]
        gw.history_times = [reading.timestamp for reading in recent]

    def _set_status(self, msg):
        if msg and hasattr(self, "_glucose"):
            try:
                w = self._glucose.query_one("#trend_label", Static)
                w.update(msg)
            except Exception:
                pass

    @staticmethod
    def _get_config_mtime():
        try:
            return os.path.getmtime(CONFIG_PATH)
        except OSError:
            return 0

    def _reload_theme_if_changed(self):
        mtime = self._get_config_mtime()
        if mtime and mtime != self._config_mtime:
            self._config_mtime = mtime
            self.call_from_thread(self._apply_theme_now)

    def _apply_theme_now(self):
        self.config = load_config()
        self._theme = {**DEFAULT_THEME, **(self.config.get("theme") or {})}

        self.screen.styles.background = self._theme.get("bg", "#1e1e2e")
        self.screen.styles.border = ("solid", self._theme.get("accent", "#f9e2af"))

        if hasattr(self, "_glucose"):
            self._glucose._apply_theme()
            if self._glucose.value_mgdl is not None:
                self._glucose.watch_value_mgdl(self._glucose.value_mgdl)

    def action_reload_theme(self):
        self._apply_theme_now()

    def action_login(self):
        self._running = False
        self.push_screen(LoginScreen())

    def action_toggle_graph(self):
        if hasattr(self, "_glucose"):
            gw = self._glucose
            if not gw.show_graph:
                self._resize_window(760, 340)
                self.set_timer(0.15, self._show_graph)
            else:
                self._resize_window(419, 178)
                gw.show_graph = False

    def _show_graph(self):
        if hasattr(self, "_glucose"):
            self._glucose.show_graph = True

    @staticmethod
    def _resize_window(w, h):
        try:
            subprocess.run(
                ["i3-msg", f'[instance="glucose-monitor"] resize set {w} {h}'],
                capture_output=True,
                timeout=2,
            )
        except Exception:
            pass

    def action_toggle_unit(self):
        if hasattr(self, "_glucose"):
            self._glucose.use_mmol = not self._glucose.use_mmol

    def action_refresh(self):
        if self._fetch_in_progress:
            return
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
