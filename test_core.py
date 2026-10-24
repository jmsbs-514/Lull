import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import core.settings as settings_module
from core.lyrics import parse_lrc
from core.settings import Settings, sanitize_patch
from core.smtc import MediaWatcher, PLAYING


class Props:
    def __init__(self, title):
        self.title = title
        self.artist = "Artist"
        self.album_title = "Album"
        self.genres = []
        self.thumbnail = None


class Timeline:
    position = SimpleNamespace(total_seconds=lambda: 10.0)
    end_time = SimpleNamespace(total_seconds=lambda: 100.0)
    last_updated_time = SimpleNamespace(timestamp=lambda: 0.0)


class Session:
    def __init__(self, title, status):
        self.props = Props(title)
        self.playback = SimpleNamespace(playback_status=status)

    async def try_get_media_properties_async(self):
        return self.props

    def get_playback_info(self):
        return self.playback

    def get_timeline_properties(self):
        return Timeline()


class Manager:
    def __init__(self, sessions, current=None):
        self.sessions = sessions
        self.current = current

    def get_sessions(self):
        return self.sessions

    def get_current_session(self):
        return self.current


class CoreTests(unittest.TestCase):
    def test_parse_lrc_sorts_and_strips_metadata(self):
        lines = parse_lrc(
            "[ti:Song]\n[00:12.50]second\n[00:01.25]first"
        )
        self.assertEqual(
            lines,
            [{"t": 1.25, "s": "first"}, {"t": 12.5, "s": "second"}],
        )

    def test_media_watcher_prefers_a_playing_session(self):
        paused = Session("PAUSED-APP", 1)
        playing = Session("PLAYING-APP", PLAYING)
        watcher = MediaWatcher()
        asyncio.run(watcher._poll(Manager([paused, playing])))
        self.assertEqual(watcher.snapshot()["title"], "PLAYING-APP")

    def test_settings_sanitize_colors(self):
        self.assertEqual(sanitize_patch({"ink": "#AbCdEf"}), {"ink": "#abcdef"})
        self.assertEqual(sanitize_patch({"accent": None}), {"accent": None})
        self.assertEqual(
            sanitize_patch({"rhythm_color": "#AbCdEf"}),
            {"rhythm_color": "#abcdef"})
        self.assertEqual(
            sanitize_patch({"rhythm_color": None}), {"rhythm_color": None})
        for bad in ("red", "#12345", "#GGGGGG", 123, ""):
            self.assertEqual(sanitize_patch({"surface": bad}), {})
            self.assertEqual(sanitize_patch({"rhythm_color": bad}), {})

    def test_settings_sanitize_rhythm_opacity(self):
        self.assertEqual(
            sanitize_patch({"rhythm_opacity": 0.5}), {"rhythm_opacity": 0.5})
        self.assertEqual(
            sanitize_patch({"rhythm_opacity": 0.1}), {"rhythm_opacity": 0.1})
        self.assertEqual(
            sanitize_patch({"rhythm_opacity": 0}), {"rhythm_opacity": 0.1})
        self.assertEqual(
            sanitize_patch({"rhythm_opacity": 1.5}), {"rhythm_opacity": 1.0})
        for bad in ("x", None):
            self.assertEqual(sanitize_patch({"rhythm_opacity": bad}), {})

    def test_settings_sanitize_styles(self):
        for style in ("glow", "editorial", "quiet", "rail"):
            self.assertEqual(sanitize_patch({"style": style}), {"style": style})
        self.assertEqual(sanitize_patch({"style": "capsule"}), {})

    def test_settings_sanitize_rhythm(self):
        self.assertEqual(sanitize_patch({"rhythm": "wave"}), {"rhythm": "wave"})
        self.assertEqual(sanitize_patch({"rhythm": "mirror"}), {"rhythm": "mirror"})
        for bad in ("nope", "", 1, None):
            self.assertEqual(sanitize_patch({"rhythm": bad}), {})

    def test_settings_sanitize_file_values(self):
        old_path = settings_module.PATH
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text(
                '{"width":"bad","opacity":999,"style":[1],"locked":"yes"}',
                encoding="utf-8",
            )
            settings_module.PATH = str(path)
            try:
                snapshot = Settings().snapshot()
            finally:
                settings_module.PATH = old_path
        self.assertEqual(snapshot["width"], 804)
        self.assertEqual(snapshot["opacity"], 1.0)
        self.assertEqual(snapshot["style"], "glow")
        self.assertTrue(snapshot["locked"])


if __name__ == "__main__":
    unittest.main()
