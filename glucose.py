#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta

import requests
from pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, Header, Footer

from chart_renderer import render_chart
from config import (
    color_for,
    get_password,
    load_config,
    save_config,
    store_password,
    thresholds,
)
from constants import (
    CONFIG_PATH,
    DEFAULT_THEME,
    GRAPH_POINTS_PER_HOUR,
    GRAPH_REFRESH_SECS,
    REFRESH_SECS,
    TREND_GLYPH,
    TREND_LABEL,
    GraphData,
    make_big_text,
)
from screens import LoginScreen


class GlucoseWidget(Static):
    value_mgdl = reactive(None)
    value_mmol = reactive(None)
    trend = reactive(None)
    use_mmol = reactive(False)
    graph_data = reactive(None)
    show_graph = reactive(False)
    avg_mgdl = reactive(None)
    tir_pct = reactive(None)
    delta_mgdl = reactive(None)

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

    def _safe_any(self, selector):
        try:
            return self.query_one(selector)
        except Exception:
            return None

    def watch_value_mgdl(self, val):
        if val is None:
            return
        t = getattr(self.app, "_theme", DEFAULT_THEME)
        lo, hi = thresholds(getattr(self.app, "config", {}))
        display = (
            f"{self.value_mmol:.1f}"
            if self.use_mmol and self.value_mmol is not None
            else str(val)
        )
        clr = color_for(val, t, lo, hi)
        unit = "mmol/L" if self.use_mmol else "mg/dL"
        trend_char = TREND_GLYPH.get(self.trend, "")
        label = TREND_LABEL.get(self.trend, "")

        w = self._safe("big_value")
        if w:
            w.update(make_big_text(display))
            w.styles.color = clr

        extras = []
        if self.delta_mgdl is not None and self.show_graph:
            delta = self.delta_mgdl
            if self.use_mmol:
                delta = round(delta / 18.0182, 1)
            sign = "+" if delta >= 0 else ""
            extras.append(f"{sign}{delta}")

        if self.avg_mgdl is not None and self.show_graph:
            if self.use_mmol:
                extras.append(f"{self.avg_mgdl / 18.0182:.1f} avg")
            else:
                extras.append(f"{self.avg_mgdl} avg")

        if self.tir_pct is not None and self.show_graph:
            extras.append(f"TIR {self.tir_pct}%")

        extras_str = "  ".join(extras)
        sep = f"  {extras_str}  " if extras_str else "  "

        age_str = ""
        app = self.app
        if hasattr(app, "_last_fetch_time") and app._last_fetch_time:
            elapsed = time.monotonic() - app._last_fetch_time
            if elapsed > 120:
                mins = int(elapsed // 60)
                age_str = f"  {mins}m ago"

        w = self._safe("compact_val")
        if w:
            w.update(f"{display} {trend_char}{sep}{unit}  {label}{age_str}")
            w.styles.color = clr

        w = self._safe("trend_label")
        if w:
            info = f"{display} {trend_char}{sep}{unit}  {label}{age_str}"
            w.update(info.lstrip())
            w.styles.color = t.get("muted", "#585b70")

    def watch_avg_mgdl(self, val):
        if self.value_mgdl is not None:
            self.watch_value_mgdl(self.value_mgdl)

    def watch_tir_pct(self, val):
        if self.value_mgdl is not None and self.show_graph:
            self.watch_value_mgdl(self.value_mgdl)

    def watch_use_mmol(self, val):
        if self.value_mgdl is not None:
            self.watch_value_mgdl(self.value_mgdl)
        self._render_chart()

    def watch_graph_data(self, data):
        if data and len(data.history) >= 2:
            self.avg_mgdl = round(sum(data.history) / len(data.history))
        else:
            self.avg_mgdl = None
        if self.show_graph:
            self.set_timer(0.0, self._render_chart)

    def watch_show_graph(self, val):
        big_val = self._safe("big_value")
        big_row = big_val.parent if big_val else None
        compact_row = self._safe_any(".compact_row")
        trend_label = self._safe("trend_label")
        chart = self._safe("chart")
        if val:
            if big_row:
                big_row.styles.display = "none"
            if compact_row:
                compact_row.styles.display = "block"
            if trend_label:
                trend_label.styles.display = "none"
            if chart:
                chart.display = True
        else:
            if big_row:
                big_row.styles.display = "block"
            if compact_row:
                compact_row.styles.display = "none"
            if trend_label:
                trend_label.styles.display = "block"
            if chart:
                chart.display = False
        if self.value_mgdl is not None:
            self.watch_value_mgdl(self.value_mgdl)
        self._render_chart()

    def _render_chart(self):
        w = self._safe("chart")
        if not w or not self.show_graph:
            return
        if self.graph_data and len(self.graph_data.history) >= 2:
            screen_width = getattr(self.app.screen.size, "width", 0)
            if screen_width <= 10:
                screen_width = getattr(self.app.size, "width", 80)
            avail = max(screen_width - 5, 10)
            lo, hi = thresholds(getattr(self.app, "config", {}))
            hours = getattr(self.app, "config", {}).get("graph_hours", 8)
            text = render_chart(
                self.graph_data.history,
                self.graph_data.times,
                width=avail,
                height=13,
                low_threshold=lo,
                high_threshold=hi,
                use_mmol=self.use_mmol,
                theme=getattr(self.app, "_theme", None),
                graph_hours=hours,
            )
            w.update(text)
        else:
            w.update("waiting for data…")


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
        content-align: left top;
        width: 100%;
        height: 14;
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
        ("h", "cycle_hours", "Hours"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._theme = {**DEFAULT_THEME, **(config.get("theme") or {})}
        self.client = None
        self._running = True
        self._fetch_in_progress = False
        self._config_mtime = self._get_config_mtime()
        self._last_fetch_time = 0.0
        self._full_graph_data = None

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
        last_graph_fetch = 0.0

        try:
            self.call_from_thread(self._set_status, "Authenticating\u2026")

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
            self._pid = pid

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            self.call_from_thread(
                self._set_status, f"Authentication failed: HTTP {code}"
            )
            self._fetch_in_progress = False
            return

        except Exception as e:
            self.call_from_thread(
                self._set_status, f"Authentication failed: {str(e)[:60]}"
            )
            self._fetch_in_progress = False
            return

        while self._running:
            self._fetch_in_progress = True

            try:
                try:
                    latest = self.client.latest(pid)

                    if latest:
                        self.call_from_thread(self._update_display, latest)
                        backoff = REFRESH_SECS
                    else:
                        self.call_from_thread(self._set_status, "No glucose data")

                except requests.exceptions.HTTPError as e:
                    code = e.response.status_code if e.response is not None else None

                    if code == 401:
                        self.call_from_thread(
                            self._set_status, "Session expired, signing in again\u2026"
                        )

                        try:
                            self.client.authenticate()
                            latest = self.client.latest(pid)

                            if latest:
                                self.call_from_thread(self._update_display, latest)
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
                                self._set_status, f"Rate limited, retry in {remaining}s"
                            )
                            time.sleep(1)

                        backoff = min(backoff * 2, 600)
                        self.call_from_thread(self._set_status, "Retrying\u2026")
                        continue

                    else:
                        display_code = code if code is not None else "?"
                        self.call_from_thread(
                            self._set_status, f"HTTP {display_code}"
                        )

                except requests.exceptions.RequestException as e:
                    self.call_from_thread(
                        self._set_status, f"Network error: {str(e)[:60]}"
                    )

                except Exception as e:
                    self.call_from_thread(self._set_status, str(e)[:80])

                now = time.monotonic()
                if now - last_graph_fetch >= GRAPH_REFRESH_SECS:
                    try:
                        graph_data = self.client.graph(pid)

                        if graph_data:
                            self.call_from_thread(self._update_graph, graph_data)
                            last_graph_fetch = now

                    except requests.exceptions.HTTPError as graph_error:
                        graph_code = (
                            graph_error.response.status_code
                            if graph_error.response is not None
                            else None
                        )

                        if graph_code in (429, 430):
                            self.call_from_thread(
                                self._set_status, "Graph request rate limited"
                            )

                    except requests.exceptions.RequestException:
                        pass

                    except Exception:
                        pass

            finally:
                self._fetch_in_progress = False

            for _ in range(REFRESH_SECS):
                if not self._running:
                    return
                self._reload_theme_if_changed()
                time.sleep(1)

    def _update_display(self, latest):
        gw = self._glucose
        new_val = latest.value_in_mg_per_dl

        last_val = getattr(gw, "_last_mgdl", None)
        if last_val is not None:
            gw.delta_mgdl = new_val - last_val
        else:
            gw.delta_mgdl = 0
        gw._last_mgdl = new_val

        lo, hi = thresholds(self.config)
        if last_val is not None:
            was_normal = last_val >= lo and last_val <= hi
            now_abnormal = new_val < lo or new_val > hi
            if not was_normal and now_abnormal:
                pass
            elif was_normal and now_abnormal:
                if new_val < lo:
                    msg = f"Low glucose: {new_val} mg/dL"
                else:
                    msg = f"High glucose: {new_val} mg/dL"
                subprocess.run(
                    ["notify-send", "-u", "critical", "Glucose Alert", msg],
                    timeout=2,
                )
            elif not was_normal and not now_abnormal:
                subprocess.run(
                    ["notify-send", "-u", "normal", "Glucose Alert", "Back in range"],
                    timeout=2,
                )

        gw.value_mgdl = new_val
        gw.value_mmol = new_val / 18.0182
        gw.trend = latest.trend
        self._last_fetch_time = time.monotonic()

    def _update_graph(self, graph_data):
        self._full_graph_data = graph_data
        self._slice_graph()

    def _slice_graph(self):
        gw = self._glucose
        lo, hi = thresholds(self.config)
        hours = self.config.get("graph_hours", 8)
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [r for r in self._full_graph_data if r.timestamp >= cutoff]
        vals = [reading.value_in_mg_per_dl for reading in recent]
        times = [reading.timestamp for reading in recent]

        if len(vals) >= 2:
            actual = (times[-1] - times[0]).total_seconds() / 3600
            if actual < hours - 1:
                self.notify(f"{hours}h: {actual:.0f}h of data", timeout=2)
            in_range = sum(1 for v in vals if lo <= v <= hi)
            gw.tir_pct = round(in_range / len(vals) * 100)
        else:
            gw.tir_pct = None

        gw.graph_data = GraphData(history=vals, times=times)

    def _set_status(self, msg):
        if not msg or not hasattr(self, "_glucose"):
            return
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
                self._resize_window(900, 400)
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

    def action_cycle_hours(self):
        cycle = [6, 8, 12]
        current = self.config.get("graph_hours", 8)
        try:
            idx = cycle.index(current)
        except ValueError:
            idx = -1
        new_hours = cycle[(idx + 1) % len(cycle)]
        self.config["graph_hours"] = new_hours
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
        except OSError:
            pass
        if hasattr(self, "_glucose") and self._full_graph_data:
            self._slice_graph()
            self._glucose._render_chart()
        elif hasattr(self, "_glucose"):
            self._glucose.graph_data = None

    def action_refresh(self):
        if self._fetch_in_progress:
            return
        if hasattr(self, "_glucose"):
            self._glucose.value_mgdl = None
            self._glucose.graph_data = None
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
