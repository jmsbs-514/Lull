"""歌词获取与解析。

优先用网易云歌曲 ID 精确取词（带翻译），拿不到时退回 LRCLIB 按歌名搜。
结果按歌曲 ID 缓存。
"""

import re
import threading
from typing import Any

import requests
import urllib3

urllib3.disable_warnings()

NCM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://music.163.com/",
    "Cookie": "appver=8.9.70; os=pc",
}

LINE_TAG = re.compile(r"\[(\d+):(\d{1,2}(?:[.:]\d+)?)\]")
META_TAG = re.compile(r"^\[(ti|ar|al|by|offset|re|ve|length):.*\]$", re.I)


def parse_lrc(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or META_TAG.match(raw):
            continue
        stamps = LINE_TAG.findall(raw)
        if not stamps:
            continue
        body = LINE_TAG.sub("", raw).strip()
        if not body:
            continue
        for mm, ss in stamps:
            try:
                sec = int(mm) * 60 + float(ss.replace(":", "."))
            except ValueError:
                continue
            out.append({"t": round(sec, 2), "s": body})
    out.sort(key=lambda x: x["t"])
    return out


def _dedup(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for ln in lines:
        k = (ln["t"], ln["s"])
        if k in seen:
            continue
        seen.add(k)
        out.append(ln)
    return out


def fetch_netease(song_id: int) -> dict[str, Any] | None:
    url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
    try:
        data = requests.get(url, headers=NCM_HEADERS, timeout=12).json()
    except Exception:
        return None
    if data.get("code") != 200:
        return None
    if data.get("pureMusic"):
        return {"source": "netease", "lines": [], "trans": [], "pure_music": True}

    lines = _dedup(parse_lrc((data.get("lrc") or {}).get("lyric", "") or ""))
    trans = _dedup(parse_lrc((data.get("tlyric") or {}).get("lyric", "") or ""))
    if not lines:
        return None
    return {"source": "netease", "lines": lines, "trans": trans, "pure_music": False}


def fetch_lrclib(title: str, artist: str, duration: float) -> dict[str, Any] | None:
    if not title:
        return None
    main_artist = artist.split("/")[0].strip() if artist else ""
    params = {"track_name": title, "artist_name": main_artist}
    if duration > 5:
        params["duration"] = int(round(duration))
    try:
        r = requests.get("https://lrclib.net/api/get", params=params,
                         timeout=12,
                         headers={"User-Agent": "Lull/0.1 (https://github.com/)"})
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception:
        return None
    body = d.get("syncedLyrics") or ""
    if not body:
        return None
    lines = _dedup(parse_lrc(body))
    if not lines:
        return None
    return {"source": "lrclib", "lines": lines, "trans": [], "pure_music": False}


class LyricStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        self._inflight: set[str] = set()

    @staticmethod
    def _key(song_id: int, title: str, artist: str) -> str:
        return f"{song_id}" if song_id else f"{title}|{artist}"

    def peek(self, song_id: int, title: str, artist: str) -> dict[str, Any] | None:
        with self._lock:
            return self._cache.get(self._key(song_id, title, artist))

    def has(self, song_id: int, title: str, artist: str) -> bool:
        return self.peek(song_id, title, artist) is not None

    def get(self, song_id: int, title: str, artist: str, duration: float) -> dict[str, Any]:
        key = self._key(song_id, title, artist)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            if key in self._inflight:
                return {"loading": True, "lines": [], "trans": [], "pure_music": False}
            self._inflight.add(key)
        try:
            data = None
            if song_id:
                data = fetch_netease(song_id)
            if data is None:
                data = fetch_lrclib(title, artist, duration)
            if data is None:
                data = {"source": "none", "lines": [], "trans": [], "pure_music": False}
            data["loading"] = False
            with self._lock:
                self._cache[key] = data
            return data
        finally:
            with self._lock:
                self._inflight.discard(key)
