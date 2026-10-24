"""独立进程：抓系统输出、算 5 段频谱，按 JSON 行输出。

放在子进程里是为了把 WASAPI/COM 和 numpy 完全隔离在 pywebview 进程之外，
避免音频库把主进程的 GIL/COM 卡住。

stdout 每行：
    {"v": 0~1, "bands": [5 个 0~1], "spectrum": true}
没有 soundcard 时退回 pycaw 总响度，bands 全填同一个值，spectrum 为 false。
"""

import json
import math
import os
import sys
import time
import traceback

BLOCK = 2048
LOW_HZ = 30.0
HIGH_HZ = 12000.0
BAND_COUNT = 32
BANDS = [
    (LOW_HZ * (HIGH_HZ / LOW_HZ) ** (i / BAND_COUNT),
     LOW_HZ * (HIGH_HZ / LOW_HZ) ** ((i + 1) / BAND_COUNT))
    for i in range(BAND_COUNT)
]


def clamp(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def emit(level: float, bands: list[float], spectrum: bool) -> None:
    sys.stdout.write(json.dumps({
        "v": round(clamp(level), 3),
        "bands": [round(clamp(b), 3) for b in bands],
        "spectrum": bool(spectrum),
    }) + "\n")
    sys.stdout.flush()


def spectrum_loop() -> None:
    import numpy as np
    import soundcard as sc

    speaker = sc.default_speaker()
    if speaker is None:
        raise RuntimeError("no default speaker")

    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
    if mic is None:
        raise RuntimeError("no loopback device")

    rate = 48000
    try:
        recorder = mic.recorder(samplerate=rate, channels=2, blocksize=BLOCK)
    except Exception:
        try:
            rate = 44100
            recorder = mic.recorder(samplerate=rate, channels=2, blocksize=BLOCK)
        except Exception:
            recorder = mic.recorder(samplerate=rate, channels=1, blocksize=BLOCK)

    window = np.hanning(BLOCK)
    freqs = np.fft.rfftfreq(BLOCK, 1.0 / rate)
    nyquist = rate / 2.0
    # 像网页那样：每个柱子直接采一个对数频率点对应的 FFT bin，不按区间平均，
    # 低频不会因为区间比频率分辨率还窄而出现空洞。
    bin_idxs = [
        min(len(freqs) - 1,
            max(0, int(round(((lo + hi) * 0.5 / nyquist) * (len(freqs) - 1)))))
        for lo, hi in BANDS
    ]
    centers = [(lo + hi) * 0.5 for lo, hi in BANDS]
    # 高频自然比低频弱，做一点固定倾斜，不用逐段 AGC
    tilts = [max(0.5, min(2.0, (c / 1000.0) ** 0.15)) for c in centers]
    smooth = [0.0] * len(BANDS)
    overall = 0.0

    with recorder as rec:
        while True:
            data = rec.record(numframes=BLOCK)
            mono = np.asarray(data, dtype=np.float32)
            if mono.ndim > 1:
                mono = mono.mean(axis=1)
            mono = mono - float(mono.mean())
            mag = np.abs(np.fft.rfft(mono * window))
            rms = float(np.sqrt(np.mean(mono ** 2)))
            silent = rms < 0.0005

            for i, bin_idx in enumerate(bin_idxs):
                if silent:
                    level = 0.0
                else:
                    energy = float(mag[bin_idx]) / (BLOCK / 2)
                    energy *= tilts[i]
                    db = 20.0 * math.log10(energy + 1e-8)
                    # 固定映射，保留动态范围；不再按每段自己的峰值拉满
                    level = clamp((db + 65.0) / 45.0) ** 1.25
                if level > smooth[i]:
                    smooth[i] += (level - smooth[i]) * 0.8
                else:
                    smooth[i] += (level - smooth[i]) * 0.25

            rdb = 20.0 * math.log10(rms + 1e-8)
            target = 0.0 if silent else clamp((rdb + 45.0) / 45.0)
            if target > overall:
                overall += (target - overall) * 0.8
            else:
                overall += (target - overall) * 0.18

            emit(overall, smooth, True)


def peak_loop() -> None:
    """没有 soundcard 时的降级：只读总峰值，bands 全相同。"""
    import ctypes
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

    ctypes.windll.ole32.CoInitializeEx(None, 0x0)  # MTA
    device = AudioUtilities.GetSpeakers()
    interface = device._dev.Activate(
        IAudioMeterInformation._iid_, CLSCTX_ALL, None)
    meter = cast(interface, POINTER(IAudioMeterInformation))
    level = 0.0
    while True:
        peak = max(0.0, min(1.0, float(meter.GetPeakValue())))
        target = peak ** 0.7
        if target > level:
            level += (target - level) * 0.55
        else:
            level += (target - level) * 0.14
        emit(level, [level] * len(BANDS), False)
        time.sleep(0.05)


def main() -> None:
    try:
        spectrum_loop()
    except Exception:
        traceback.print_exc()
        try:
            peak_loop()
        except Exception:
            traceback.print_exc()
            os._exit(1)


if __name__ == "__main__":
    main()
