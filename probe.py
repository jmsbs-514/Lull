import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time

import webview

OUT = sys.argv[1] if len(sys.argv) > 1 else "_probe.png"
LOG = open("_probe.log", "w", encoding="utf-8", buffering=1)

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
LWA_COLORKEY = 0x00000001
KEY_RGB = (0, 0, 0)
KEY_REF = KEY_RGB[0] | (KEY_RGB[1] << 8) | (KEY_RGB[2] << 16)


def find_window(title: str):
    pid = os.getpid()
    found = []

    def cb(hwnd, lp):
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


html = """
<body style="margin:0;background:transparent;height:100vh;
display:flex;flex-direction:column;align-items:center;justify-content:center;
font-family:'Microsoft YaHei UI',sans-serif;">
  <div style="font-size:15px;color:rgba(255,255,255,.55);margin-bottom:6px">
    愛愛愛し愛 — 中文翻译在这里
  </div>
  <div style="font-size:30px;color:#fff;font-weight:500;
    text-shadow:0 2px 10px rgba(0,0,0,.9)">今はただ愛したいだけ</div>
</body>
"""

win = webview.create_window(
    "probe", html=html,
    width=720, height=132, x=950, y=1060,
    frameless=True, on_top=True, shadow=False,
    transparent=True,
    background_color="#010203",
)


def tweak(window):
    time.sleep(0.9)
    hwnd = find_window("probe")
    LOG.write(f"hwnd={hwnd}\n")

    try:
        from System.Windows.Forms import Application
        from System.Drawing import Color
        forms = list(Application.OpenForms)
        LOG.write(f"open forms={len(forms)}\n")
        for f in forms:
            LOG.write(f"  form={f} bg={f.BackColor}\n")
            f.BackColor = Color.Black
            LOG.write(f"  set black, now {f.BackColor}\n")
    except Exception as e:
        LOG.write(f"forms err {type(e).__name__} {e}\n")

    if not hwnd:
        return
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    ok = user32.SetLayeredWindowAttributes(hwnd, KEY_REF, 255, LWA_COLORKEY)
    LOG.write(f"colorkey ok={ok} ref={KEY_REF:#x}\n")
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)


def shot():
    time.sleep(6)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    from PIL import ImageGrab
    ImageGrab.grab(all_screens=True).crop((880, 980, 1780, 1300)).save(OUT)
    os._exit(0)


threading.Thread(target=shot, daemon=True).start()
webview.start(tweak, (win,))
