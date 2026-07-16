# FloatingGlucoseMonitor

A floating-window TUI for live FreeStyle LibreLinkUp glucose readings on Linux (i3wm). Built with [Textual](https://textual.textualize.io/) and [pylibrelinkup](https://github.com/ivallesp/pylibrelinkup).

## Features

- Big glucose value with trend arrow (↑ ↗ → ↘ ↓)
- Color-coded values: green (normal), red (low), orange (high)
- ASCII sparkline of recent readings
- mg/dL ↔ mmol/L toggle (`u` key)
- Auto-refresh every 60s
- Catppuccin-Mocha theme matching i3 config colors
- Password stored in system keyring (not on disk)

## Requirements

- Python 3.10+
- [i3wm](https://i3wm.org/) with `kitty` terminal

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install textual pylibrelinkup keyring
```

## Usage

```bash
./toggle.sh   # launch/toggle the floating window
```

Keybind (i3 config): `$mod+Shift+g`

From the TUI:
- `u` — toggle mg/dL / mmol/L
- `r` — force refresh
- `q` — quit

On first launch, enter your LibreLinkUp email, password, and region (US/EU/etc.).

## Files

| File | Purpose |
|------|---------|
| `glucose.py` | Main TUI application |
| `run.sh` | Launcher that activates the virtualenv |
| `toggle.sh` | i3 toggle script (launches `kitty --class glucose-monitor`) |
| `diagnose.sh` | Tests all API regions for connectivity |
## License

MIT
