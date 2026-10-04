"""命令行入口。

用法：
    maa-autoboot                # 打开 GUI（无参数默认行为）
    maa-autoboot --boot         # 静默执行（计划任务开机调用；遵守时间闸门）
    maa-autoboot --boot --force # 跳过时间闸门立即执行
    maa-autoboot --boot --dryrun# 演练：不启动程序、不关机
    maa-autoboot --install      # 安装/更新开机自启计划任务（需管理员）
    maa-autoboot --uninstall    # 卸载计划任务
    maa-autoboot --status       # 查看计划任务状态
"""

from __future__ import annotations

import argparse
import sys

from . import APP_NAME, __version__
from .config import load_config, logs_root
from .logutil import get_logger, setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=APP_NAME,
        description="MAA / MAAEnd 开机自动跑日常（无人值守 + 自动关机）")
    p.add_argument("--boot", action="store_true", help="静默执行开机流程")
    p.add_argument("--dryrun", action="store_true", help="演练模式：不实际启动/关机")
    p.add_argument("--force", action="store_true", help="跳过时间闸门立即执行")
    p.add_argument("--config", help="自定义配置文件路径")
    p.add_argument("--install", action="store_true", help="安装/更新开机自启计划任务")
    p.add_argument("--uninstall", action="store_true", help="卸载计划任务")
    p.add_argument("--status", action="store_true", help="查看计划任务状态")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return p


def _task_action(args) -> int:
    from . import schtask
    if args.install:
        cmd = schtask.build_boot_command()
        ok, msg = schtask.install_task(cmd)
        print(("✔ " if ok else "✘ ") + msg)
        if not ok and sys.platform == "win32":
            print("提示：安装计划任务需要管理员权限，请以管理员身份运行。")
        return 0 if ok else 1
    if args.uninstall:
        ok, msg = schtask.uninstall_task()
        print(("✔ " if ok else "✘ ") + msg)
        return 0 if ok else 1
    info = schtask.query_task()
    if info:
        print(info)
    else:
        print("计划任务不存在（或当前平台不支持）")
    return 0


def _force_utf8_streams() -> None:
    """Windows 控制台默认 cp1252/cp936，打印中文帮助会 UnicodeEncodeError。

    打包 EXE 无法预设 PYTHONUTF8，这里对输出流强制 UTF-8（不可编码时用替换符）。
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    args = build_parser().parse_args(argv)

    if args.install or args.uninstall or args.status:
        return _task_action(args)

    cfg = load_config(args.config)
    setup_logging(logs_root(cfg), console=(not args.boot or args.dryrun))
    log = get_logger()
    log.info("%s v%s 启动（boot=%s dryrun=%s force=%s）",
             APP_NAME, __version__, args.boot, args.dryrun, args.force)

    if not args.boot:
        # 无参数 -> GUI
        from .gui import run_gui
        return run_gui(cfg)

    from . import launcher
    result = launcher.run(cfg, dryrun=args.dryrun, force=args.force)
    ok = result.all_ok
    log.info("流程结束：%s", "全部成功" if ok else "存在失败/未执行")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
