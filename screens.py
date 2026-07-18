from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from config import save_config, store_password
from constants import DEFAULT_THEME, REGION_HELP


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
