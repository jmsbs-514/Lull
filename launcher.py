"""Lull 的无控制台入口，负责记录启动阶段的导入异常。"""

import os
import traceback


def write_error() -> None:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        import main
    except Exception:
        write_error()
        raise
    else:
        main.run()
