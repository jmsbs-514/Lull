"""读取 Windows 系统媒体会话（SMTC）。

网易云原版不上报 SMTC，装上 BetterNCM + InfLink-rs 后才会出现。
没有会话时 state['available'] 为 False。
"""

import asyncio
import threading
from typing import Any

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as Manager,
)
from winrt.windows.storage.streams import DataReader

PLAYING = 4


def _enum_val(x):
    """winrt 枚举在不同版本里有时给 int 有时给枚举对象。"""
    try:
        return int(x)
    except (TypeError, ValueError):
        return getattr(x, "value", 0)


def _is_playing(session) -> bool:
    try:
        return _enum_val(session.get_playback_info().playback_status) == PLAYING
    except Exception:
        return False


def _pick_session(manager):
    """优先选正在播放的会话，其次当前会话，最后第一个。"""
    sessions = list(manager.get_sessions())
    if not sessions:
        return None
    for session in sessions:
        if _is_playing(session):
            return session
    try:
        current = manager.get_current_session()
    except Exception:
        current = None
    return current or sessions[0]


class MediaWatcher(threading.Thread):
    """后台线程常驻，每 0.4s 刷新一次快照。"""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="smtc-watcher")
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "available": False,
            "title": "",
            "artist": "",
            "album": "",
            "song_id": 0,
            "position": 0.0,
            "duration": 0.0,
            "last_updated": 0.0,
            "playing": False,
            "seq": 0,
        }
        self._cover: bytes | None = None
        self._cover_key: str = ""
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._manager = None

    # ---------- 对外 ----------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def cover(self) -> tuple[bytes | None, str]:
        with self._lock:
            return self._cover, self._cover_key

    # ---------- 内部 ----------
    def _set(self, **kw) -> None:
        with self._lock:
            self._state.update(kw)
            self._state["seq"] += 1

    def run(self) -> None:
        try:
            asyncio.run(self._loop())
        except Exception:
            pass

    async def _loop(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        manager = await Manager.request_async()
        self._manager = manager
        while True:
            try:
                await self._poll(manager)
            except Exception:
                pass
            await asyncio.sleep(0.4)

    async def _poll(self, manager) -> None:
        sessions = list(manager.get_sessions())
        if not sessions:
            if self.snapshot()["available"]:
                self._set(available=False, playing=False, title="", artist="",
                          song_id=0, position=0.0, duration=0.0)
            return

        session = _pick_session(manager)
        if session is None:
            return
        props = await session.try_get_media_properties_async()
        if props is None:
            return

        song_id = 0
        for g in props.genres:
            if g and g.startswith("NCM-"):
                try:
                    song_id = int(g[4:])
                except ValueError:
                    pass
                break

        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()

        try:
            last_updated = timeline.last_updated_time.timestamp()
        except Exception:
            last_updated = 0.0

        self._set(
            available=True,
            title=props.title or "",
            artist=props.artist or "",
            album=props.album_title or "",
            song_id=song_id,
            position=timeline.position.total_seconds(),
            duration=timeline.end_time.total_seconds(),
            last_updated=last_updated,
            playing=_enum_val(playback.playback_status) == PLAYING,
        )

        key = f"{props.title}|{props.artist}|{song_id}"
        if key != self._cover_key and props.thumbnail is not None:
            await self._grab_cover(props.thumbnail, key)

    # ---------- 播放控制 ----------
    def control(self, action: str, position: float | None = None) -> bool:
        """从 HTTP / 托盘线程发起的同步调用，投递到 watcher 的事件循环。"""
        loop = self._event_loop
        if loop is None or loop.is_closed():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._control(action, position), loop)
            return bool(future.result(timeout=2.5))
        except Exception:
            return False

    async def _control(self, action: str, position: float | None) -> bool:
        manager = self._manager
        if manager is None:
            return False
        session = _pick_session(manager)
        if session is None:
            return False
        try:
            if action == "toggle":
                ok = await session.try_toggle_play_pause_async()
            elif action == "next":
                ok = await session.try_skip_next_async()
            elif action == "prev":
                ok = await session.try_skip_previous_async()
            elif action == "seek":
                seconds = max(0.0, float(position or 0.0))
                # winrt 这里要的是 100ns tick，不是 timedelta。
                ok = await session.try_change_playback_position_async(
                    int(seconds * 10_000_000))
            else:
                return False
        except Exception:
            return False

        # 乐观更新，下一轮轮询会校正。
        if ok and action == "toggle":
            self._set(playing=not self.snapshot()["playing"])
        return bool(ok)

    async def _grab_cover(self, thumb, key: str) -> None:
        try:
            stream = await thumb.open_read_async()
            size = int(stream.size)
            if size <= 0 or size > 8 * 1024 * 1024:
                return
            reader = DataReader(stream)
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            with self._lock:
                self._cover = bytes(buf)
                self._cover_key = key
        except Exception:
            pass
