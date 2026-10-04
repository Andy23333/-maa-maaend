"""程序启动与收尾：MAA / MAAEnd / 雷电模拟器（ldconsole）。"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from .config import AppEntry, EmulatorConfig
from .logutil import get_logger
from .wintools import is_windows, kill_processes, pids_by_name


def split_args(args: str) -> List[str]:
    """把配置里的参数串拆成列表（支持引号）。空串返回 []。"""
    import shlex
    args = (args or "").strip()
    if not args:
        return []
    try:
        return shlex.split(args, posix=(os.name != "nt"))
    except ValueError:
        return args.split()  # 兜底：按空白切


def validate_entry(entry: AppEntry) -> "tuple[bool, str]":
    if not entry.path.strip():
        return False, "未填写程序路径"
    p = Path(entry.path)
    if not p.exists():
        return False, f"路径不存在：{entry.path}"
    if not p.is_file():
        return False, f"路径不是文件：{entry.path}"
    return True, ""


def launch_program(entry: AppEntry, dryrun: bool) -> Optional[subprocess.Popen]:
    """启动主程序（工作目录设为主程序所在目录，很多程序依赖相对路径）。"""
    log = get_logger()
    exe = Path(entry.path)
    cmd = [str(exe)] + split_args(entry.args)
    if dryrun:
        log.info("[DRY-RUN] 跳过启动：%s", " ".join(cmd))
        return None
    try:
        # DETACHED：主程序生命周期与本工具解耦
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED|NEW_GROUP
        proc = subprocess.Popen(
            cmd, cwd=str(exe.parent), creationflags=flags if os.name == "nt" else 0,
            close_fds=True)
        log.info("已启动 %s（PID=%s）", exe.name, proc.pid)
        return proc
    except OSError as e:
        log.error("启动失败 %s：%s", exe, e)
        return None


# ---------------------------------------------------------------------------
# 雷电模拟器（明日方舟链路；对应原 launcher.ps1 的 ldconsole launch / runapp）
# ---------------------------------------------------------------------------

def ldconsole_run(emu: EmulatorConfig, args: List[str], dryrun: bool) -> bool:
    log = get_logger()
    if not emu.ldconsole_path.strip():
        log.error("启用了模拟器流程但未填写 ldconsole 路径")
        return False
    exe = Path(emu.ldconsole_path)
    if not exe.exists():
        log.error("未找到 ldconsole：%s", exe)
        return False
    cmd = [str(exe)] + args
    if dryrun:
        log.info("[DRY-RUN] 跳过执行：%s", " ".join(cmd))
        return True
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0:
            log.error("ldconsole 失败(%s)：%s", args,
                      r.stderr.decode("utf-8", "replace").strip())
            return False
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log.error("ldconsole 调用异常：%s", e)
        return False


def start_emulator_and_game(emu: EmulatorConfig, dryrun: bool) -> bool:
    """启动模拟器 -> 拉起明日方舟 -> 固定等待进游戏。"""
    log = get_logger()
    log.info("启动雷电模拟器（index=%s）…", emu.index)
    if not ldconsole_run(emu, ["launch", "--index", str(emu.index)], dryrun):
        return False
    log.info("通过包名启动明日方舟：%s", emu.package)
    if not ldconsole_run(emu, ["runapp", "--index", str(emu.index),
                               "--packagename", emu.package], dryrun):
        return False
    wait = max(0, emu.launch_wait_sec)
    if dryrun:
        log.info("[DRY-RUN] 压缩等待：原应等待 %s 秒", wait)
        wait = min(wait, 1)
    log.info("等待 %.0f 秒让游戏进入主界面 …", wait)
    time.sleep(wait)
    return True


def close_entry(entry: AppEntry, emu: EmulatorConfig, dryrun: bool) -> None:
    """收尾：关闭主程序 + 配置里登记的关联进程（原 Close-MaaEndAndGame）。"""
    log = get_logger()
    names = list(entry.kill_names or [])
    if entry.path:
        names.append(Path(entry.path).name)
    if emu.enabled and emu.ldconsole_path:
        names.append("dnplayer.exe")   # 雷电模拟器主进程
    names = [n for n in dict.fromkeys(names) if n]
    if dryrun:
        log.info("[DRY-RUN] 跳过结束进程：%s", ", ".join(names))
        return
    n = kill_processes(names)
    log.info("已结束 %s 个进程（%s）", n, ", ".join(names))


def is_process_running(entry: AppEntry) -> bool:
    if not is_windows() or not entry.path:
        return False
    return bool(pids_by_name(Path(entry.path).name))
