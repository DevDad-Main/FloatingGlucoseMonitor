# Floating Glucose Monitor

<p align="center">
  A clean floating terminal interface for viewing live FreeStyle LibreLinkUp glucose readings on Linux.
</p>

<p align="center">
  <img src="glucose.jpg" alt="Floating Glucose Monitor showing mg/dL" width="48%">
  <img src="glucose-mmol.jpg" alt="Floating Glucose Monitor showing mmol/L" width="48%">
</p>

<p align="center">
  <strong>Live readings · Trend indicators · Glucose history · mg/dL and mmol/L</strong>
</p>

---

## Overview

**Floating Glucose Monitor** is a lightweight floating-window TUI for displaying live FreeStyle LibreLinkUp glucose readings.

It is designed primarily for Linux desktops running i3wm and uses:

* [Textual](https://textual.textualize.io/) for the terminal interface
* [pylibrelinkup](https://github.com/ivallesp/pylibrelinkup) for LibreLinkUp data
* `kitty` for the floating terminal window
* The system keyring for secure password storage

> This is an unofficial community/personal project and is not affiliated with Abbott or FreeStyle Libre.

## Features

* Large, easy-to-read glucose display
* Glucose trend arrows: `↑` `↗` `→` `↘` `↓`
* Color-coded glucose values

  * Green for values in range
  * Red for low values
  * Orange for high values
* Recent glucose history graph
* Toggle between `mg/dL` and `mmol/L`
* Automatic glucose refresh
* Less-frequent history refresh to reduce API usage
* LibreLinkUp region selection
* Catppuccin Mocha-inspired interface
* Password storage through the operating system keyring
* Floating-window integration for i3wm

## Requirements

* Python 3.10 or newer
* A LibreLinkUp account
* A FreeStyle Libre user sharing data through LibreLinkUp
* Linux
* [i3wm](https://i3wm.org/)
* [kitty](https://sw.kovidgoyal.net/kitty/)
* A supported system keyring

## Installation

Clone the repository:

```bash
git clone https://github.com/DevDad-Main/FloatingGlucoseMonitor.git
cd FloatingGlucoseMonitor
```

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required packages:

```bash
pip install textual pylibrelinkup keyring requests
```

Make the scripts executable:

```bash
chmod +x run.sh toggle.sh diagnose.sh
```

## Usage

Launch or toggle the floating monitor:

```bash
./toggle.sh
```

You can also launch the application directly:

```bash
./run.sh
```

On the first launch, enter:

* Your LibreLinkUp email address
* Your LibreLinkUp password
* Your LibreLinkUp region

For users in Poland, select:

```text
EU
```

Your password is stored using the system keyring rather than being written directly to the configuration file.

## Controls

| Key | Action                           |
| :-: | -------------------------------- |
| `u` | Toggle between mg/dL and mmol/L  |
| `g` | Toggle the glucose history graph |
| `r` | Refresh the glucose data         |
| `l` | Open the login screen            |
| `q` | Quit                             |

## i3wm Keybind

Add the following line to your i3 configuration:

```text
bindsym $mod+Shift+g exec --no-startup-id /full/path/to/FloatingGlucoseMonitor/toggle.sh
```

Replace the path with the actual location of the repository.

Reload your i3 configuration after making the change:

```text
$mod+Shift+r
```

## Refresh Behaviour

By default:

* The latest glucose reading is requested every 60 seconds.
* Graph history can be refreshed less frequently to reduce LibreLinkUp API usage.
* Authentication and patient discovery are performed once at startup where possible.
* The application uses exponential backoff when it encounters a rate limit.

The intervals can be adjusted in `glucose.py`:

```python
REFRESH_SECS = 60
GRAPH_REFRESH_SECS = 300
```

The example above refreshes:

* Current glucose every 1 minute
* Graph history every 5 minutes

## Project Files

| File               | Purpose                                                      |
| ------------------ | ------------------------------------------------------------ |
| `glucose.py`       | Main Textual application                                     |
| `run.sh`           | Activates the virtual environment and starts the application |
| `toggle.sh`        | Opens or toggles the floating kitty window                   |
| `diagnose.sh`      | Tests LibreLinkUp API regions and connectivity               |
| `glucose.jpg`      | Screenshot showing the mg/dL interface                       |
| `glucose-mmol.jpg` | Screenshot showing the mmol/L interface                      |

## Configuration

The application stores its configuration at:

```text
~/.config/glucose-monitor/config.json
```

The configuration file may contain:

* LibreLinkUp email address
* Selected API region
* Theme overrides

The password is stored separately through the system keyring.

## Troubleshooting

### No patients found

Make sure the Libre user has shared their glucose data with the LibreLinkUp account used by the application.

### Rate-limited requests

Avoid repeatedly pressing the manual refresh key.

> NOTE: The defaults are optimized to not hit rate limits, 
Increasing these values may also help:

```python
REFRESH_SECS = 90
GRAPH_REFRESH_SECS = 300
```

### Keyring errors

Install a compatible keyring backend for your Linux desktop environment. Depending on your distribution, you may need packages related to GNOME Keyring, Secret Service, or KWallet.

### Incorrect region

Run:

```bash
./diagnose.sh
```

You can then test the available LibreLinkUp API regions.

## Security

* Passwords are stored through the operating system keyring.
* Passwords are not intentionally stored in the JSON configuration file.
* Do not commit personal credentials or configuration files to the repository.

Consider adding the following entries to `.gitignore`:

```gitignore
venv/
__pycache__/
*.pyc
.env
config.json
```

## Disclaimer

This project is intended for informational and convenience purposes only.

It is not a medical device and must not be used as the sole basis for medical decisions. Always use official FreeStyle Libre applications and approved glucose-monitoring equipment for treatment decisions.

## License

This project is licensed under the [MIT License](LICENSE).
