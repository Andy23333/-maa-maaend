"""Windows 计划任务管理（schtasks 封装）。

与原项目的差异：
- 原项目 Action 指向“托管 pythonw.exe”，版本升级会清空 site-packages，
  是已知单点风险（§8 待办 3）。
- 本实现：打包成 EXE 时 Action 直接指向 EXE（无解释器依赖）；
  源码运行时指向仓库根的 run_boot.py + pythonw。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import APP_NAME

# 任务名隔离：设置环境变量 MAAAUTOBOOT_TASK_NAME（如 MaaAutoBootTest）
# 可在不影响已有 MaaAutoBoot / AutoBootLauncher 任务的情况下独立测试。


def task_name() -> str:
    """计划任务名（默认 MaaAutoBoot，可用环境变量 MAAAUTOBOOT_TASK_NAME 覆盖）。"""
    return os.environ.get("MAAAUTOBOOT_TASK_NAME") or APP_NAME


@dataclass
class TaskCommand:
    program: str   # 可执行文件
    args: str      # 参数串（可为空）

    def tr_value(self) -> str:
        """/TR 参数值：schtasks 对引号敏感，程序路径必须整体加引号。"""
        return f'"{self.program}" {self.args}'.strip()


def build_boot_command() -> TaskCommand:
    """构造“开机后静默执行”的命令行（指向自身，带 --boot 标志）。"""
    if getattr(sys, "frozen", False):
        return TaskCommand(program=sys.executable, args="--boot")
    # 源码运行：优先 pythonw（无控制台窗口）
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    if not pyw.exists():
        pyw = exe
    run_boot = Path(__file__).resolve().parent.parent / "run_boot.py"
    return TaskCommand(program=str(pyw), args=f'"{run_boot}" --boot')


def _run_schtasks(args: list[str], timeout: int = 60) -> "subprocess.CompletedProcess[bytes]":
    return subprocess.run(["schtasks", *args], capture_output=True, timeout=timeout)


def task_exists(name: str = "") -> bool:
    name = name or task_name()
    if not sys.platform == "win32":
        return False
    try:
        return _run_schtasks(["/Query", "/TN", name]).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def query_task(name: str = "") -> Optional[str]:
    """返回任务状态摘要（Next Run Time 等），便于 GUI 显示。"""
    name = name or task_name()
    if sys.platform != "win32":
        return None
    try:
        r = _run_schtasks(["/Query", "/TN", name, "/V", "/FO", "LIST"])
        if r.returncode != 0:
            return None
        return r.stdout.decode("gbk", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None


def install_task(cmd: TaskCommand, name: str = "") -> tuple[bool, str]:
    """创建/覆盖 ONLOGON + 最高权限 计划任务（需管理员权限）。"""
    name = name or task_name()
    if sys.platform != "win32":
        return False, "仅 Windows 支持计划任务"
    try:
        r = _run_schtasks(
            ["/Create", "/TN", name, "/TR", cmd.tr_value(),
             "/SC", "ONLOGON", "/RL", "HIGHEST", "/F"])
        out = r.stdout.decode("gbk", errors="replace").strip()
        if r.returncode == 0:
            return True, out or "计划任务创建成功"
        # 已存在时 /F 应覆盖；到这来一般是权限不足
        return False, out + r.stderr.decode("gbk", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def uninstall_task(name: str = "") -> tuple[bool, str]:
    name = name or task_name()
    if sys.platform != "win32":
        return False, "仅 Windows 支持计划任务"
    try:
        r = _run_schtasks(["/Delete", "/TN", name, "/F"])
        text = r.stdout.decode("gbk", errors="replace").strip()
        if r.returncode == 0:
            return True, text or "计划任务已删除"
        return False, text + r.stderr.decode("gbk", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
