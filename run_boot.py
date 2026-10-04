#!/usr/bin/env python3
"""源码运行入口：供 Windows 计划任务直接指向本文件。

    pythonw run_boot.py --boot

（打包成 EXE 后计划任务直接指向 EXE，不再需要本文件。）
"""

from maa_autoboot.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
