"""本地设置，存成 json，跟着程序走。"""

import json
import math
import os
import re
import threading
import time

from core.paths import app_dir

ROOT = app_dir()
PATH = os.path.join(ROOT, "settings.json")

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULTS = {
    "style": "glow",
    "font_size": 30,
    "sub_size": 15,
    "opacity": 0.92,
    "width": 804,
    "height": 100,
    "x": None,
    "y": None,
    "locked": True,
    "show_translation": True,
    "show_next": True,
    "ink": None,
    "accent": None,
    "surface": None,
    "rhythm": "off",
    "rhythm_opacity": 1.0,
    "rhythm_color": None,
}

STYLES = frozenset({"glow", "editorial", "quiet", "rail"})
RHYTHMS = frozenset({"off", "wave", "steps", "hairline", "breath", "mirror"})
_INVALID = object()


def _coerce_number(value, lo, hi, integer: bool):
    if isinstance(value, bool):
        return _INVALID
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return _INVALID
    if not math.isfinite(number):
        return _INVALID
    number = max(lo, min(hi, number))
    return int(round(number)) if integer else round(number, 3)


def _sanitize_value(key: str, value):
    if key == "style":
        return value if isinstance(value, str) and value in STYLES else _INVALID
    if key in {"locked", "show_translation", "show_next"}:
        return value if isinstance(value, bool) else _INVALID
    if key in {"ink", "accent", "surface", "rhythm_color"}:
        if value is None:
            return None
        if isinstance(value, str) and HEX_COLOR.match(value.strip()):
            return value.strip().lower()
        return _INVALID
    if key == "rhythm":
        return value if isinstance(value, str) and value in RHYTHMS else _INVALID
    if key == "rhythm_opacity":
        return _coerce_number(value, 0.1, 1.0, False)
    if key in {"x", "y"}:
        if value is None:
            return None
        return _coerce_number(value, -100_000, 100_000, True)
    if key == "font_size":
        return _coerce_number(value, 18, 54, True)
    if key == "sub_size":
        return _coerce_number(value, 11, 30, True)
    if key == "opacity":
        return _coerce_number(value, 0.3, 1.0, False)
    if key == "width":
        return _coerce_number(value, 300, 7680, True)
    if key == "height":
        return _coerce_number(value, 100, 2160, True)
    return _INVALID


def sanitize_patch(patch: dict) -> dict:
    """只保留已知字段，并把值限制在界面允许的范围内。"""
    clean = {}
    if not isinstance(patch, dict):
        return clean
    for key, value in patch.items():
        if key not in DEFAULTS:
            continue
        normalized = _sanitize_value(key, value)
        if normalized is not _INVALID:
            clean[key] = normalized
    return clean


class Settings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self._data.update(sanitize_patch(saved))
        except Exception:
            pass

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def update(self, patch: dict) -> dict:
        clean = sanitize_patch(patch)
        if not clean:
            return {}
        with self._lock:
            self._data.update(clean)
            data = dict(self._data)
            try:
                temp_path = PATH + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, PATH)
            except Exception:
                try:
                    os.remove(PATH + ".tmp")
                except OSError:
                    pass
        return clean
