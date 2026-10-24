"""Lull —— 桌面歌词层。

结构：
    MediaWatcher  → 读系统媒体会话（歌名/进度/封面/歌曲 ID）
    LyricStore    → 按 ID 取歌词，带缓存
    HTTP 服务     → 把数据和界面喂给本地页面，也接受拖动/锁定指令
    歌词窗口      → 透明、置顶、可点穿的浮层
    托盘          → 锁定/解锁、显示/隐藏、退出
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time
import urllib.request

os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
                      "--disable-gpu --no-sandbox")

import webview
from PIL import Image, ImageDraw

from core.paths import app_dir

APP_DIR = app_dir()

from core.audio import AudioLevel
from core.lyrics import LyricStore
from core.server import start_server
from core.settings import Settings
from core.smtc import MediaWatcher
from core.tray import LullTrayIcon

PORT = 48710
WINDOW_TITLE = "Lull"
# pywebview 的 frameless 窗口会固定少 16×32；设置里存实际尺寸，创建时补回。
WINDOW_BORDER_W = 16
WINDOW_BORDER_H = 32
PANEL_TITLE = "Lull 设置"
CARD_TITLE = "Lull 正在播放"
CARD_W, CARD_H = 360, 148

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
KEY_COLOR = 0x00000000
EDIT_ALPHA = 132

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.MonitorFromPoint.restype = wt.HANDLE
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.c_void_p]
user32.GetMonitorInfoW.restype = wt.BOOL


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_bool

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "LullDesktopLyrics"
_mutex_handle = None


def acquire_single_instance() -> bool:
    """Windows 上 SO_REUSEADDR 允许多个进程绑同一个端口，靠端口判断不住。
    用命名互斥体才靠谱。
    """
    global _mutex_handle
    if _mutex_handle:
        kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.get_last_error()
    if err == ERROR_ALREADY_EXISTS:
        if _mutex_handle:
            kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
        return False
    return _mutex_handle is not None


def _startup_watchdog(controller) -> None:
    """WebView2 偶尔会在启动阶段卡住；超时后主动退出，避免永远 Not Responding。"""
    time.sleep(30)
    if controller.hwnd:
        return
    try:
        path = os.path.join(APP_DIR, "error.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                "startup watchdog: WebView2 window was not ready after 30s\n"
            )
    except Exception:
        pass
    os._exit(2)


def activate_running_instance() -> bool:
    """已经有一个实例时，把它的主页叫出来，而不是静默退出。"""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/panel",
            data=b'{"action":"show"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener.open(request, timeout=1.5).read()
        return True
    except Exception:
        return False


def default_position(width: int, height: int) -> tuple[int, int]:
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    return (sw - width) // 2, sh - height - 96


def center_position(width: int, height: int) -> tuple[int, int]:
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    return (sw - width) // 2, (sh - height) // 2


def cursor_work_area():
    """光标所在显示器的工作区 + 光标位置（已排除任务栏）。"""
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    monitor = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return (0, 0, user32.GetSystemMetrics(0),
                user32.GetSystemMetrics(1), pt.x, pt.y)
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom, pt.x, pt.y


def card_position(width: int, height: int) -> tuple[int, int]:
    """贴着托盘所在一侧弹出，并按光标靠左/靠右对齐。"""
    left, top, right, bottom, cx, cy = cursor_work_area()
    margin = 10
    if cx > (left + right) // 2:
        x = min(cx - width + 30, right - width - margin)
    else:
        x = max(cx - 30, left + margin)
    # 卡片放在光标（托盘图标）上方，避开任务栏，也不会盖住刚点的图标。
    y = cy - height - 12
    x = max(left + margin, min(x, right - width - margin))
    y = max(top + margin, min(y, bottom - height - margin))
    return int(x), int(y)


def set_toolwindow(hwnd: int) -> None:
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    # APPWINDOW 会强行保留任务栏按钮；必须和 TOOLWINDOW 一起清掉。
    ex = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)


def round_window(hwnd: int, width: int, height: int) -> None:
    """Win11 交给 DWM 圆角；Win10 退回到圆角窗口区域。"""
    try:
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 33, ctypes.byref(pref),
                ctypes.sizeof(pref)) == 0:
            return
    except Exception:
        pass
    try:
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, width + 1, height + 1, 18, 18)
        if rgn:
            user32.SetWindowRgn(ctypes.c_void_p(hwnd), rgn, True)
    except Exception:
        pass


def find_window(title: str) -> int | None:
    """按标题在当前进程里找窗口句柄（pywebview 的内部对象跨线程拿不到）。"""
    pid = os.getpid()
    found: list[int] = []

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid:
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value == title:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


def make_transparent(hwnd: int) -> None:
    """把窗体背景涂成纯黑，再用色键把黑色抠掉。

    WebView2 在这种状态下不绘制自己的背景，页面 body 透明就会露出窗体，
    窗体再被色键抠掉 —— 于是只剩页面里真正画出来的东西。
    """
    try:
        from System.Windows.Forms import Application
        from System.Drawing import Color
        for form in Application.OpenForms:
            try:
                if form.Text == WINDOW_TITLE:
                    form.BackColor = Color.Black
            except Exception:
                pass
    except Exception:
        pass

    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    user32.SetLayeredWindowAttributes(hwnd, KEY_COLOR, 255, LWA_COLORKEY)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)


def set_layer_mode(hwnd: int, locked: bool) -> None:
    """锁定：抠掉纯黑，只剩文字。
    解锁：整块变成半透明深色，看得见边界，整块都能按住拖。
    """
    if locked:
        user32.SetLayeredWindowAttributes(hwnd, KEY_COLOR, 255, LWA_COLORKEY)
    else:
        user32.SetLayeredWindowAttributes(hwnd, 0, EDIT_ALPHA, LWA_ALPHA)


def set_clickthrough(hwnd: int, enabled: bool) -> None:
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_TOOLWINDOW
    ex &= ~WS_EX_APPWINDOW
    if enabled:
        ex |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    else:
        ex &= ~WS_EX_TRANSPARENT
        ex &= ~WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)


class Controller:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.hwnd: int | None = None
        self.lyric_window = None
        self.panel_window = None
        self.panel_hwnd: int | None = None
        self.card_window = None
        self.card_hwnd: int | None = None
        self.tray = None
        self.audio = None
        self.lyric_visible = True
        self.card_visible = False
        self.card_x = 0
        self.card_y = 0
        self.card_move_ok = None
        self.card_move_error = None
        self._card_closed_at = 0.0
        self._dragging = False

    def start_drag(self, hwnd: int | None = None):
        target = hwnd or self.hwnd
        if not target or self._dragging:
            return
        self._dragging = True
        threading.Thread(target=self._drag_loop, args=(target,), daemon=True).start()

    def _drag_loop(self, hwnd: int):
        """自己跟着鼠标走，不走系统的拖动循环。

        系统的 WM_NCLBUTTONDOWN 方式要求那一刻左键正按着，
        但从页面 mousedown 到这里已经隔了一次 HTTP 往返，手可能已经松了。
        """
        pt = wt.POINT()
        r = wt.RECT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        dx, dy = r.left - pt.x, r.top - pt.y
        try:
            while user32.GetAsyncKeyState(0x01) & 0x8000:
                user32.GetCursorPos(ctypes.byref(pt))
                user32.SetWindowPos(ctypes.c_void_p(hwnd), 0, pt.x + dx, pt.y + dy, 0, 0,
                                    SWP_NOSIZE | SWP_NOZORDER)
                time.sleep(0.008)
        finally:
            self._dragging = False
            if hwnd == self.hwnd:
                self.save_window_position()

    def recenter(self):
        if not self.lyric_window:
            return
        snap = self.settings.snapshot()
        x, y = center_position(int(snap["width"]), int(snap["height"]))
        try:
            self.lyric_window.move(x, y)
            self.settings.update({"x": x, "y": y})
        except Exception:
            pass

    def panel_action(self, action: str):
        win = self.panel_window
        if not win:
            return
        try:
            if action == "hide":
                win.hide()
            elif action == "show":
                win.show()
            else:
                win.hide()
        except Exception:
            pass

    def rect(self):
        if not self.hwnd:
            return None
        r = wt.RECT()
        ok = user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return {"ok": ok, "l": r.left, "t": r.top, "r": r.right, "b": r.bottom}

    # ---------- 托盘卡片 ----------
    def set_lyrics_visible(self, visible: bool):
        self.lyric_visible = bool(visible)
        if not self.lyric_window:
            return
        try:
            if self.lyric_visible:
                self.lyric_window.show()
            else:
                self.lyric_window.hide()
        except Exception:
            pass

    def toggle_visibility(self):
        self.set_lyrics_visible(not self.lyric_visible)

    def show_card(self):
        win = self.card_window
        if not win or self.card_visible:
            return

        x, y = card_position(CARD_W, CARD_H)
        try:
            win.show()
            win.resize(CARD_W, CARD_H)
        except Exception:
            return
        self.card_visible = True

        hwnd = self.card_hwnd or find_window(CARD_TITLE)
        self.card_hwnd = hwnd
        if hwnd:
            try:
                # resize 会用 WinForms 的 Location，所以位置要在 resize 之后按物理像素放。
                self.card_x, self.card_y = x, y
                self.card_move_ok = bool(user32.SetWindowPos(
                    ctypes.c_void_p(hwnd), 0, x, y, 0, 0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE))
                set_toolwindow(hwnd)
                r = wt.RECT()
                user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
                round_window(hwnd, r.right - r.left, r.bottom - r.top)
                user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            except Exception as exc:
                self.card_move_error = repr(exc)
        try:
            win.evaluate_js("window.cardShown && window.cardShown()")
        except Exception:
            pass

    def hide_card(self):
        if not self.card_visible:
            return
        self.card_visible = False
        self._card_closed_at = time.time()
        try:
            self.card_window.hide()
        except Exception:
            pass

    def toggle_card(self):
        if self.card_visible:
            self.hide_card()
        elif time.time() - self._card_closed_at > 0.25:
            self.show_card()

    def open_panel(self):
        try:
            self.panel_window.show()
            self.panel_window.restore()
        except Exception:
            pass
        self.hide_card()

    def quit(self):
        try:
            if self.tray:
                self.tray.visible = False
        except Exception:
            pass
        try:
            if self.audio:
                self.audio.stop()
        except Exception:
            pass
        os._exit(0)

    def set_locked(self, locked: bool):
        self.settings.update({"locked": bool(locked)})
        if locked:
            self.save_window_position()
        if self.hwnd:
            set_clickthrough(self.hwnd, bool(locked))
            set_layer_mode(self.hwnd, bool(locked))
        if self.lyric_window:
            try:
                self.lyric_window.evaluate_js(
                    f"window.setEditing && window.setEditing({str(not locked).lower()})")
            except Exception:
                pass

    def resize_lyric(self, width: int, height: int):
        """整体缩放歌词窗口，保持左上角不动。"""
        width, height = int(width), int(height)
        if not self.hwnd:
            self.settings.update({"width": width, "height": height})
            return
        r = wt.RECT()
        user32.GetWindowRect(ctypes.c_void_p(self.hwnd), ctypes.byref(r))
        user32.SetWindowPos(
            ctypes.c_void_p(self.hwnd), 0, int(r.left), int(r.top),
            width, height, SWP_NOZORDER | SWP_NOACTIVATE)
        self.settings.update({"width": width, "height": height})

    def refresh_tray_icon(self):
        """调色板的 accent 变了就重画 L，不用重启。"""
        if not self.tray:
            return
        try:
            self.tray.icon = make_tray_icon(
                self.settings.snapshot().get("accent"))
        except Exception:
            pass

    def save_window_position(self):
        if not self.hwnd:
            return
        r = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        self.settings.update({"x": int(r.left), "y": int(r.top)})


def start_lyric_worker(watcher: MediaWatcher, store: LyricStore) -> None:
    """后台盯着当前歌曲，没歌词就去拉，不阻塞界面。"""

    def loop():
        last_key = None
        while True:
            try:
                m = watcher.snapshot()
                if m["available"] and (m["title"] or m["song_id"]):
                    key = (m["song_id"], m["title"], m["artist"])
                    if key != last_key:
                        last_key = key
                        store.get(m["song_id"], m["title"], m["artist"], m["duration"])
            except Exception:
                pass
            time.sleep(0.6)

    threading.Thread(target=loop, daemon=True, name="lyric-worker").start()


def make_tray_icon(accent: str | None = None) -> Image.Image:
    """粗体 L：比 16px 下的月牙更有识别度。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    try:
        raw = (accent or "#a996ff").lstrip("#")
        color = tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    except Exception:
        color = (169, 150, 255, 255)
    lum = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    outline = (12, 12, 18, 255) if lum > 140 else (245, 243, 255, 255)

    def draw_l(offset: int, width: int, fill) -> None:
        x0, y0, x1, y1 = 25 + offset, 14 + offset, 25 + offset, 44 + offset
        x2 = 48 + offset
        d.line([(x0, y0), (x1, y1), (x2, y1)], fill=fill, width=width,
               joint="curve")
        r = width // 2
        d.ellipse((x0 - r, y0 - r, x0 + r, y0 + r), fill=fill)
        d.ellipse((x2 - r, y1 - r, x2 + r, y1 + r), fill=fill)

    draw_l(2, 18, (0, 0, 0, 90))
    draw_l(0, 20, outline)
    draw_l(0, 15, color)
    return img


def _trace(msg: str) -> None:
    try:
        path = os.path.join(APP_DIR, "startup.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def main() -> None:
    try:
        open(os.path.join(APP_DIR, "startup.log"),
             "w", encoding="utf-8").close()
    except Exception:
        pass
    _trace("main start")
    started = False
    waited_for_old = False
    for _ in range(6):
        if acquire_single_instance():
            started = True
            break
        # 上一次退出可能还没完全释放互斥体：先叫现有实例，等不到再重试接管。
        waited_for_old = True
        if activate_running_instance():
            return
        time.sleep(0.4)

    if not started:
        user32.MessageBoxW(
            None,
            "Lull 已经在运行，但没有响应。\n"
            "请在任务管理器里结束 pythonw.exe，然后再启动一次。",
            "Lull", 0x00000030)
        return

    if waited_for_old:
        # 互斥体释放不代表 WebView2 的临时进程已经退干净；给旧进程一点收尾时间，
        # 避免新实例在启动阶段撞上旧的浏览器进程。
        time.sleep(1.2)
    _trace("mutex acquired")

    settings = Settings()
    watcher = MediaWatcher()
    watcher.start()

    audio = None
    if os.environ.get("LULL_NO_AUDIO") != "1":
        audio = AudioLevel()
        audio.start()

    store = LyricStore()
    controller = Controller(settings)
    controller.audio = audio
    start_server(watcher, store, settings, controller, PORT, audio)
    start_lyric_worker(watcher, store)
    _trace("server ready")

    snap = settings.snapshot()
    width, height = int(snap["width"]), int(snap["height"])
    sx, sy = snap["x"], snap["y"]
    if sx is None or sy is None:
        sx, sy = default_position(width, height)

    lyric_window = webview.create_window(
        WINDOW_TITLE,
        f"http://127.0.0.1:{PORT}/lyric.html",
        width=width + WINDOW_BORDER_W,
        height=height + WINDOW_BORDER_H,
        x=int(sx),
        y=int(sy),
        frameless=True,
        on_top=True,
        shadow=False,
        focus=False,
        resizable=False,
        text_select=False,
        transparent=True,
        background_color="#010203",
    )
    controller.lyric_window = lyric_window

    panel_w, panel_h = 500, 690
    panel_x = (user32.GetSystemMetrics(0) - panel_w) // 2
    panel_y = max(40, (user32.GetSystemMetrics(1) - panel_h) // 2)

    panel_window = webview.create_window(
        PANEL_TITLE,
        f"http://127.0.0.1:{PORT}/panel.html",
        width=panel_w,
        height=panel_h,
        x=panel_x,
        y=panel_y,
        frameless=True,
        on_top=True,
        resizable=False,
        hidden=True,
        easy_drag=False,
        draggable=False,
        background_color="#0c0b10",
        text_select=False,
    )
    controller.panel_window = panel_window

    card_window = webview.create_window(
        CARD_TITLE,
        f"http://127.0.0.1:{PORT}/card.html",
        width=CARD_W,
        height=CARD_H,
        x=0,
        y=0,
        frameless=True,
        on_top=True,
        resizable=False,
        hidden=True,
        easy_drag=False,
        draggable=False,
        background_color="#0A0910",
        text_select=False,
    )
    controller.card_window = card_window
    _trace("windows created")

    def apply_window_style():
        _trace("apply window style start")
        # WebView2 刚起来时改分层属性容易死锁，等页面稳定一点再动窗口样式。
        time.sleep(2.5)
        hwnd = find_window(WINDOW_TITLE)
        _trace("window found")
        controller.hwnd = hwnd
        if hwnd:
            make_transparent(hwnd)
            _trace("transparent ready")
            locked = bool(settings.snapshot().get("locked", True))
            set_clickthrough(hwnd, locked)
            set_layer_mode(hwnd, locked)
            _trace("clickthrough ready")
        card_hwnd = find_window(CARD_TITLE)
        if card_hwnd:
            controller.card_hwnd = card_hwnd
            set_toolwindow(card_hwnd)
            r = wt.RECT()
            user32.GetWindowRect(ctypes.c_void_p(card_hwnd), ctypes.byref(r))
            round_window(card_hwnd, r.right - r.left, r.bottom - r.top)
        _trace("apply window style done")

    def center_panel():
        time.sleep(1.0)
        hwnd = find_window(PANEL_TITLE)
        if not hwnd:
            return
        controller.panel_hwnd = hwnd
        set_toolwindow(hwnd)
        r = wt.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if w <= 0 or h <= 0:
            return
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), 0,
                            max(0, (sw - w) // 2), max(0, (sh - h) // 2),
                            0, 0, SWP_NOSIZE | SWP_NOZORDER)

    def on_gui_ready(window):
        _trace("gui ready")
        threading.Thread(target=apply_window_style, daemon=True).start()
        threading.Thread(target=center_panel, daemon=True).start()

        def on_loaded(*_):
            locked = bool(settings.snapshot().get("locked", True))
            try:
                window.evaluate_js(
                    f"window.setEditing && window.setEditing({str(not locked).lower()})")
            except Exception:
                pass

        try:
            window.events.loaded += on_loaded
        except Exception:
            pass

    def update_tooltip(icon):
        last = None
        while True:
            try:
                m = watcher.snapshot()
                if m["available"] and m["title"]:
                    state = "播放中" if m["playing"] else "已暂停"
                    text = f"Lull · {state} · {m['title']} — {m['artist']}"
                else:
                    text = "Lull · 没有正在播放的音乐"
                if text != last:
                    last = text
                    icon.title = text[:120]
            except Exception:
                pass
            time.sleep(1.0)

    def start_tray():
        _trace("tray start")
        icon = LullTrayIcon(
            "Lull",
            make_tray_icon(settings.snapshot().get("accent")),
            "Lull 桌面歌词",
            controller.toggle_visibility,
            controller.toggle_card,
        )
        controller.tray = icon
        threading.Thread(target=update_tooltip, args=(icon,), daemon=True,
                         name="tray-tooltip").start()
        _trace("tray icon run")
        icon.run()

    threading.Thread(target=start_tray, daemon=True, name="tray").start()
    threading.Thread(target=_startup_watchdog, args=(controller,), daemon=True,
                     name="startup-watchdog").start()
    _trace("webview start")
    webview.start(on_gui_ready, (lyric_window,), debug=False)


def run() -> None:
    try:
        main()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "error.log"),
                  "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        raise


if __name__ == "__main__":
    run()
