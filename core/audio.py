"""系统音频频谱/响度，供桌面律动条使用。

真正的采集和 FFT 放在 `audio_helper.py` 子进程里：WASAPI/COM 和 numpy
完全不进入 pywebview 主进程，避免音频库卡住 GIL 或和 WinForms 的 COM 撞车。

对外只暴露 level() / bands()，后台线程负责启动、读取 JSON 行、看门狗重启。
"""

import json
import os
import subprocess
import sys
import threading
import time

CREATE_NO_WINDOW = 0x08000000
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_helper.py")
BAND_COUNT = 32


class AudioLevel(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="audio-level")
        self._lock = threading.Lock()
        self._level = 0.0
        self._bands = [0.0] * BAND_COUNT
        self.available = False
        self.spectrum = False
        self._proc = None
        self._stop = False
        self._last = 0.0

    def level(self) -> float:
        with self._lock:
            return self._level

    def bands(self) -> list[float]:
        with self._lock:
            return list(self._bands)

    def stop(self) -> None:
        self._stop = True
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass

    def _publish(self, level: float, bands, spectrum: bool) -> None:
        with self._lock:
            self._level = max(0.0, min(1.0, level))
            if isinstance(bands, list) and len(bands) == BAND_COUNT:
                self._bands = [max(0.0, min(1.0, float(b))) for b in bands]
            else:
                self._bands = [self._level] * BAND_COUNT
            self.spectrum = bool(spectrum)
            self.available = True

    def _watch(self, proc) -> None:
        while not self._stop and proc.poll() is None:
            time.sleep(1.0)
            if time.time() - self._last > 4.0:
                try:
                    proc.terminate()
                except Exception:
                    pass
                return

    def run(self) -> None:
        while not self._stop:
            proc = None
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", HELPER],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW,
                )
                self._proc = proc
                self._last = time.time()
                if self._stop:
                    proc.terminate()
                    break
                threading.Thread(
                    target=self._watch, args=(proc,), daemon=True,
                    name="audio-watchdog").start()

                for line in proc.stdout:
                    if self._stop:
                        break
                    try:
                        data = json.loads(line)
                        level = float(data.get("v", 0.0))
                        bands = data.get("bands")
                        spectrum = bool(data.get("spectrum", False))
                    except Exception:
                        continue
                    self._last = time.time()
                    self._publish(level, bands, spectrum)

                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self._proc = None

            with self._lock:
                self.available = False
                self.spectrum = False
                self._level = 0.0
                self._bands = [0.0] * BAND_COUNT

            if not self._stop:
                time.sleep(1.0)
