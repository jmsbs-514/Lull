"""运行目录与资源目录：开发时在项目根，冻结后在 exe 目录 / _MEIPASS。"""

import os
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return app_dir()
