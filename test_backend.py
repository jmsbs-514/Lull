import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import core.settings as settings_module
from core.server import start_server
from core.settings import Settings


MEDIA = {
    "available": True,
    "title": "Song",
    "artist": "Artist",
    "album": "Album",
    "song_id": 123,
    "position": 12.5,
    "duration": 180.0,
    "last_updated": 0.0,
    "playing": True,
    "seq": 1,
}

LYRICS = {
    "source": "netease",
    "lines": [{"t": 10.0, "s": "line"}],
    "trans": [],
    "pure_music": False,
    "loading": False,
}


class FakeWatcher:
    def __init__(self):
        self.controls = []

    def snapshot(self):
        return dict(MEDIA)

    def cover(self):
        return None, ""

    def control(self, action, position=None):
        self.controls.append((action, position))
        return True


class FakeStore:
    def peek(self, *_):
        return dict(LYRICS)


class FakeController:
    def __init__(self):
        self.hwnd = 123
        self.panel_hwnd = 456
        self._dragging = False
        self.calls = []
        self.lyrics_visible = True

    def rect(self):
        return {"ok": 1, "l": 10, "t": 20, "r": 830, "b": 152}

    def set_locked(self, locked):
        self.calls.append(("locked", locked))

    def start_drag(self, hwnd=None):
        self.calls.append(("drag", hwnd or self.hwnd))

    def panel_action(self, action):
        self.calls.append(("panel", action))

    def recenter(self):
        self.calls.append(("recenter",))

    def resize_lyric(self, width, height):
        self.calls.append(("resize", width, height))

    def refresh_tray_icon(self):
        self.calls.append(("tray",))

    def show_card(self):
        self.calls.append(("card", "show"))

    def hide_card(self):
        self.calls.append(("card", "hide"))

    def toggle_card(self):
        self.calls.append(("card", "toggle"))

    def set_lyrics_visible(self, visible):
        self.lyrics_visible = bool(visible)
        self.calls.append(("visibility", self.lyrics_visible))

    def toggle_visibility(self):
        self.set_lyrics_visible(not self.lyrics_visible)

    def quit(self):
        self.calls.append(("quit",))


class FakeAudio:
    available = True
    spectrum = True

    def level(self):
        return 0.42

    def bands(self):
        return [round(i / 31, 3) for i in range(32)]


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_settings_path = settings_module.PATH
        settings_module.PATH = str(Path(self.temp.name) / "settings.json")
        self.settings = Settings()
        self.controller = FakeController()
        self.watcher = FakeWatcher()
        self.audio = FakeAudio()
        self.server = start_server(
            self.watcher, FakeStore(), self.settings, self.controller, 0,
            self.audio,
        )
        self.port = self.server.server_address[1]
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        settings_module.PATH = self.old_settings_path
        self.temp.cleanup()

    def request(self, path, body=None):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            response = self.opener.open(request, timeout=3)
            return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def json_request(self, path, body=None):
        status, payload, _ = self.request(path, body)
        return status, json.loads(payload.decode("utf-8"))

    def test_state_and_debug_endpoints_use_controller(self):
        status, state = self.json_request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["media"]["title"], "Song")
        self.assertEqual(state["lyrics"]["lines"][0]["s"], "line")

        status, debug = self.json_request("/api/debug")
        self.assertEqual(status, 200)
        self.assertEqual(debug["hwnd"], 123)
        self.assertEqual(debug["rect"]["r"], 830)

    def test_invalid_settings_are_rejected(self):
        status, payload = self.json_request(
            "/api/settings",
            {"opacity": 999, "width": "not-a-number", "style": 123},
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            payload["rejected"], ["style", "width"]
        )
        snapshot = self.settings.snapshot()
        self.assertEqual(snapshot["opacity"], 0.92)
        self.assertEqual(snapshot["width"], 804)
        self.assertEqual(snapshot["style"], "glow")

    def test_valid_settings_and_lock_are_applied(self):
        status, payload = self.json_request(
            "/api/settings", {"opacity": 0.6, "locked": False}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["settings"]["opacity"], 0.6)
        self.assertIn(("locked", False), self.controller.calls)

    def test_control_endpoints_call_the_controller(self):
        cases = [
            ("/api/drag", {}, ("drag", 123)),
            ("/api/recenter", {}, ("recenter",)),
            ("/api/panel", {"action": "drag"}, ("drag", 456)),
            ("/api/panel", {"action": "hide"}, ("panel", "hide")),
        ]
        for path, body, expected in cases:
            status, payload = self.json_request(path, body)
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertIn(expected, self.controller.calls)

    def test_control_endpoint_handles_actions_and_seek(self):
        for action in ("toggle", "next", "prev"):
            status, payload = self.json_request("/api/control", {"action": action})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
        self.assertEqual(
            self.watcher.controls,
            [("toggle", None), ("next", None), ("prev", None)],
        )

        status, payload = self.json_request(
            "/api/control", {"action": "seek", "position": 12.5})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.watcher.controls[-1], ("seek", 12.5))

        # 超过时长时夹到 duration
        self.json_request("/api/control", {"action": "seek", "position": 999})
        self.assertEqual(self.watcher.controls[-1], ("seek", 180.0))

        for invalid in (
            {"action": "nope"},
            {"action": "seek", "position": "x"},
            {"action": "seek", "position": -1},
        ):
            status, _ = self.json_request("/api/control", invalid)
            self.assertEqual(status, 400)

    def test_card_and_visibility_endpoints(self):
        for action in ("show", "hide", "toggle"):
            status, payload = self.json_request("/api/card", {"action": action})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
        self.assertIn(("card", "show"), self.controller.calls)
        self.assertIn(("card", "hide"), self.controller.calls)
        self.assertIn(("card", "toggle"), self.controller.calls)

        self.json_request("/api/visibility", {"action": "hide"})
        self.assertFalse(self.controller.lyrics_visible)
        self.json_request("/api/visibility", {"action": "show"})
        self.assertTrue(self.controller.lyrics_visible)
        self.json_request("/api/visibility", {"action": "toggle"})
        self.assertFalse(self.controller.lyrics_visible)

        status, _ = self.json_request("/api/card", {"action": "nope"})
        self.assertEqual(status, 400)
        status, _ = self.json_request("/api/visibility", {"action": "nope"})
        self.assertEqual(status, 400)

    def test_resize_endpoint(self):
        status, payload = self.json_request(
            "/api/resize", {"width": 900, "height": 160})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn(("resize", 900, 160), self.controller.calls)

        status, _ = self.json_request("/api/resize", {"width": "bad"})
        self.assertEqual(status, 400)

    def test_palette_settings_are_validated(self):
        status, payload = self.json_request(
            "/api/settings",
            {"ink": "#112233", "accent": None, "surface": "#AABBCC"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["settings"]["ink"], "#112233")
        self.assertIsNone(payload["settings"]["accent"])
        self.assertEqual(payload["settings"]["surface"], "#aabbcc")
        self.assertIn(("tray",), self.controller.calls)

        status, payload = self.json_request("/api/settings", {"ink": "red"})
        self.assertEqual(status, 400)
        self.assertIn("ink", payload["rejected"])

    def test_audio_level_endpoint(self):
        status, payload = self.json_request("/api/level")
        self.assertEqual(status, 200)
        self.assertAlmostEqual(payload["v"], 0.42, places=3)
        self.assertEqual(len(payload["bands"]), 32)
        self.assertAlmostEqual(payload["bands"][0], 0.0, places=3)
        self.assertTrue(payload["spectrum"])

    def test_static_files_are_served(self):
        status, payload, headers = self.request("/lyric.html")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Lull</title>", payload)
        self.assertIn("text/html", headers["Content-Type"])

        status, payload, headers = self.request("/card.html")
        self.assertEqual(status, 200)
        self.assertIn(b"/card.js", payload)
        self.assertIn("text/html", headers["Content-Type"])


if __name__ == "__main__":
    unittest.main()
