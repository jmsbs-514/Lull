"""Lull 的无控制台入口，负责记录启动阶段的导入异常。"""

import os
import sys
import traceback

from core.paths import app_dir


def write_error() -> None:
    path = os.path.join(app_dir(), "error.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    if "--audio-helper" in sys.argv:
        from core.audio_helper import main as helper_main
        helper_main()
        raise SystemExit(0)

    try:
        import main
    except Exception:
        write_error()
        raise
    else:
        main.run()
