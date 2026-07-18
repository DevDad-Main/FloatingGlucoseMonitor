import os
from dataclasses import dataclass

from pylibrelinkup.models.data import Trend

CONFIG_PATH = os.path.expanduser("~/.config/glucose-monitor/config.json")
KEYRING_SERVICE = "glucose-monitor"

LOW = 70
HIGH = 180
REFRESH_SECS = 60
GRAPH_REFRESH_SECS = 300
GRAPH_POINTS_PER_HOUR = 12

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

REGION_HELP = "Options: US, EU, EU2, AE, AP, AU, CA, DE, FR, JP, LA, RU (Poland → EU)"

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


@dataclass
class GraphData:
    history: list
    times: list
