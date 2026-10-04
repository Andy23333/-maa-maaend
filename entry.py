#!/usr/bin/env python3
"""PyInstaller 打包入口。

    pyinstaller --onefile --windowed --name MaaAutoBoot --icon assets/icon.ico entry.py

打包后的 EXE：
- 无参数  -> 打开 GUI
- --boot  -> 静默执行开机流程（计划任务 Action 直接指向 EXE --boot）
"""

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()          # PyInstaller onefile 必需
    from maa_autoboot.cli import main
    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
