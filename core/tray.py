"""托盘图标。

pystray 默认把左右键都交给菜单；Lull 要的是左键切歌词、右键弹播放卡片，
所以只覆写通知处理，NIM 生命周期和 Explorer 重启恢复仍交给 pystray。
"""

import pystray

WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205


class LullTrayIcon(pystray.Icon):
    def __init__(self, name, image, title, on_left_click, on_right_click):
        super().__init__(name, image, title, menu=None)
        self._on_left_click = on_left_click
        self._on_right_click = on_right_click

    def _on_notify(self, wparam, lparam):
        if lparam == WM_LBUTTONUP:
            self._call(self._on_left_click)
        elif lparam == WM_RBUTTONUP:
            self._call(self._on_right_click)

    @staticmethod
    def _call(callback):
        try:
            callback()
        except Exception:
            pass
