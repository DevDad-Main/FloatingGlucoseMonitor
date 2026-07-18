import json
import os

import keyring

from constants import CONFIG_PATH, DEFAULT_THEME, HIGH, KEYRING_SERVICE, LOW


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    else:
        cfg = {}
    defaults = {
        "low_threshold": 70,
        "high_threshold": 180,
        "graph_hours": 8,
        "notification_unit": "mgdl",
    }
    changed = False
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed:
        save_config(cfg)
    return cfg


def save_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


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


def thresholds(cfg):
    return (
        cfg.get("low_threshold", LOW),
        cfg.get("high_threshold", HIGH),
    )


def color_for(val_mgdl: int, theme: dict, lo=LOW, hi=HIGH) -> str:
    if val_mgdl < lo:
        return theme.get("low", DEFAULT_THEME["low"])
    elif val_mgdl > hi:
        return theme.get("high", DEFAULT_THEME["high"])
    return theme.get("normal", DEFAULT_THEME["normal"])
