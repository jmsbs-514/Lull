"""本地 HTTP 服务：给界面提供静态文件和数据。

不用 pywebview 的 js_api —— pythonnet 序列化 WinForms 控件时会无限递归，
而且每秒读一次播放进度，走 fetch 比跨进程桥更稳，前端也能自己控制插值节奏。
"""

import json
import math
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core.settings import sanitize_patch

WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class Handler(BaseHTTPRequestHandler):
    watcher = None
    store = None
    settings = None
    controller = None
    audio = None

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/state":
            media = self.watcher.snapshot()
            entry = self.store.peek(media["song_id"], media["title"], media["artist"])
            self._json({"media": media, "lyrics": entry,
                        "settings": self.settings.snapshot()})
            return

        if path == "/api/level":
            value = 0.0
            bands = []
            spectrum = False
            try:
                if self.audio is not None:
                    value = float(self.audio.level())
                    bands = [float(x) for x in self.audio.bands()]
                    spectrum = bool(getattr(self.audio, "spectrum", False))
            except Exception:
                value = 0.0
                bands = []
                spectrum = False
            self._json({
                "v": round(max(0.0, min(1.0, value)), 3),
                "bands": [round(max(0.0, min(1.0, b)), 3) for b in bands],
                "spectrum": spectrum,
            })
            return

        if path == "/api/debug":
            self._json({
                "hwnd": self.controller.hwnd,
                "locked": self.settings.snapshot().get("locked"),
                "dragging": self.controller._dragging,
                "rect": self.controller.rect(),
                "x": self.settings.snapshot().get("x"),
                "y": self.settings.snapshot().get("y"),
                "lyrics_visible": getattr(self.controller, "lyric_visible", None),
                "card_visible": getattr(self.controller, "card_visible", None),
                "card_hwnd": getattr(self.controller, "card_hwnd", None),
                "card_x": getattr(self.controller, "card_x", None),
                "card_y": getattr(self.controller, "card_y", None),
                "card_move_ok": getattr(self.controller, "card_move_ok", None),
                "card_move_error": getattr(self.controller, "card_move_error", None),
                "audio_available": bool(getattr(self.audio, "available", False)),
                "audio_spectrum": bool(getattr(self.audio, "spectrum", False)),
                "audio_level": round(float(self.audio.level()), 3) if self.audio else 0.0,
            })
            return

        if path == "/api/cover":
            data, _ = self.watcher.cover()
            if not data:
                self._send(404, b"", "image/jpeg")
                return
            ctype = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
            self._send(200, data, ctype)
            return

        self._serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()

        if path == "/api/lock":
            locked = body.get("locked", True)
            if not isinstance(locked, bool):
                self._json({"ok": False, "error": "locked must be boolean"}, 400)
                return
            self.controller.set_locked(locked)
            self._json({"ok": True, "locked": locked})
            return

        if path == "/api/drag":
            self.controller.start_drag()
            self._json({"ok": True})
            return

        if path == "/api/settings":
            clean = sanitize_patch(body)
            rejected = sorted(set(body) - set(clean))
            if rejected:
                self._json({
                    "ok": False,
                    "error": "invalid settings",
                    "rejected": rejected,
                    "settings": self.settings.snapshot(),
                }, 400)
                return
            applied = self.settings.update(clean)
            if "accent" in applied:
                self.controller.refresh_tray_icon()
            if "locked" in applied:
                self.controller.set_locked(applied["locked"])
            self._json({"ok": True, "settings": self.settings.snapshot()})
            return

        if path == "/api/resize":
            clean = sanitize_patch({
                "width": body.get("width"),
                "height": body.get("height"),
            })
            if "width" not in clean or "height" not in clean:
                self._json({"ok": False, "error": "invalid size"}, 400)
                return
            self.controller.resize_lyric(clean["width"], clean["height"])
            self._json({"ok": True, "settings": self.settings.snapshot()})
            return

        if path == "/api/recenter":
            self.controller.recenter()
            self._json({"ok": True})
            return

        if path == "/api/panel":
            action = body.get("action", "toggle")
            if action == "drag":
                self.controller.start_drag(self.controller.panel_hwnd)
            else:
                self.controller.panel_action(action)
            self._json({"ok": True})
            return

        if path == "/api/control":
            action = body.get("action")
            if action not in ("toggle", "next", "prev", "seek"):
                self._json({"ok": False, "error": "invalid action"}, 400)
                return
            position = None
            if action == "seek":
                try:
                    position = float(body.get("position"))
                except (TypeError, ValueError):
                    self._json({"ok": False, "error": "invalid position"}, 400)
                    return
                if not math.isfinite(position) or position < 0:
                    self._json({"ok": False, "error": "invalid position"}, 400)
                    return
                duration = float(self.watcher.snapshot().get("duration") or 0)
                if duration > 0:
                    position = min(position, duration)
            ok = bool(self.watcher.control(action, position))
            self._json({"ok": ok})
            return

        if path == "/api/card":
            action = body.get("action", "toggle")
            if action == "show":
                self.controller.show_card()
            elif action == "hide":
                self.controller.hide_card()
            elif action == "toggle":
                self.controller.toggle_card()
            else:
                self._json({"ok": False, "error": "invalid action"}, 400)
                return
            self._json({"ok": True})
            return

        if path == "/api/visibility":
            action = body.get("action", "toggle")
            if action == "show":
                self.controller.set_lyrics_visible(True)
            elif action == "hide":
                self.controller.set_lyrics_visible(False)
            elif action == "toggle":
                self.controller.toggle_visibility()
            else:
                self._json({"ok": False, "error": "invalid action"}, 400)
                return
            self._json({"ok": True})
            return

        if path == "/api/quit":
            self._json({"ok": True})
            threading.Timer(0.1, self.controller.quit).start()
            return

        self._json({"ok": False, "error": "unknown endpoint"}, 404)

    def _serve_static(self, path: str):
        rel = "lyric.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_ROOT, rel))
        root = os.path.normcase(os.path.normpath(WEB_ROOT))
        full_key = os.path.normcase(full)
        try:
            inside_root = os.path.commonpath((root, full_key)) == root
        except ValueError:
            inside_root = False
        if not inside_root or not os.path.isfile(full):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def start_server(watcher, store, settings, controller, port: int = 48710,
                 audio=None) -> ThreadingHTTPServer:
    Handler.watcher = watcher
    Handler.store = store
    Handler.settings = settings
    Handler.controller = controller
    Handler.audio = audio
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True, name="http").start()
    return httpd
