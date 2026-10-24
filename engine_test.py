import asyncio, re, time, sys
import requests, urllib3
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as Manager,
)

urllib3.disable_warnings()
HEAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://music.163.com/",
    "Cookie": "appver=8.9.70; os=pc",
}

TAG = re.compile(r"\[(\d+):(\d{1,2}(?:\.\d+)?)\]")


def parse_lrc(text):
    """-> [(time_sec, line)]  sorted, 去掉纯元信息行"""
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        times = TAG.findall(raw)
        if not times:
            continue
        body = TAG.sub("", raw).strip()
        if not body:
            continue
        for mm, ss in times:
            out.append((int(mm) * 60 + float(ss), body))
    out.sort(key=lambda x: x[0])
    return out


def fetch_lyric(song_id):
    url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
    d = requests.get(url, headers=HEAD, timeout=15).json()
    lrc = parse_lrc((d.get("lrc") or {}).get("lyric", "") or "")
    trans = parse_lrc((d.get("tlyric") or {}).get("lyric", "") or "")
    tmap = {}
    for t, s in trans:
        tmap.setdefault(t, s)
    return lrc, tmap


def fmt(sec):
    return f"{int(sec)//60:02d}:{sec%60:05.2f}"


async def main():
    m = await Manager.request_async()
    s = m.get_sessions()[0]
    props = await s.try_get_media_properties_async()
    genres = list(props.genres)
    sid = None
    for g in genres:
        if g.startswith("NCM-"):
            sid = int(g[4:])
    print(f"♪ {props.title} — {props.artist}  (id={sid})")

    lrc, tmap = fetch_lyric(sid)
    print(f"  歌词 {len(lrc)} 行, 翻译 {len(tmap)} 条\n")

    for _ in range(8):
        pos = s.get_timeline_properties().position.total_seconds()
        idx = -1
        for i, (t, _) in enumerate(lrc):
            if t <= pos:
                idx = i
            else:
                break
        cur = lrc[idx][1] if idx >= 0 else "···"
        nxt = lrc[idx + 1][1] if idx + 1 < len(lrc) else ""
        tr = tmap.get(lrc[idx][0], "") if idx >= 0 else ""
        print(f"[{fmt(pos)}] {cur}")
        if tr:
            print(f"          {tr}")
        if nxt:
            print(f"      ·· {nxt}")
        await asyncio.sleep(1.5)


asyncio.run(main())
