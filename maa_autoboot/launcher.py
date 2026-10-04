"""主编排器：移植自原 launcher.ps1 的主流程（Python 重写版）。

主流程：时间闸门 -> 提权/路径自检 -> MAAend 阶段 -> MAA 阶段 -> 关机决策。

与原版的差异（均为文档 §8 待办中列出的改进）：
- 失败默认**不关机**并醒目记日志（原版“失败也关机”会掩盖问题；
  如需旧行为，在 GUI 中把“失败时”设为“仍然关机”）。
- 更新重启重跑次数限制为 1 次，避免无限循环。
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import apps, wintools
from .clicker import LinkStartClicker
from .config import AppEntry, Config
from .dismiss import MaaEndPopupDismisser
from .gate import gate_status
from .logutil import get_logger
from .monitor import find_log_files, wait_for_marker, wait_process_stable
from .vision import save_debug_png

MAX_RERUN = 1  # 更新重启后的最大重跑次数


@dataclass
class RunResult:
    started: bool = False                 # 是否真正进入执行（闸门拦截=False）
    maaend_ok: Optional[bool] = None      # None=未启用
    maa_ok: Optional[bool] = None
    shutdown_scheduled: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        checks = [v for v in (self.maaend_ok, self.maa_ok) if v is not None]
        return bool(checks) and all(checks)


def _should_stop_factory(should_stop: Optional[Callable[[], bool]]) -> Callable[[], bool]:
    return should_stop or (lambda: False)


def _app_dir(entry: AppEntry) -> Path:
    return Path(entry.path).parent


def _maa_log_paths(cfg: Config) -> List[Path]:
    return find_log_files(_app_dir(cfg.maa), ["debug/gui.log", "debug\\gui.log"])


def _maaend_log_paths(cfg: Config) -> List[Path]:
    return find_log_files(_app_dir(cfg.maaend), ["debug/*.log", "debug\\*.log"])


# ---------------------------------------------------------------------------
# MAAEnd 阶段（原 Invoke-MaaEndAutoRerun / Watch-MaaEndRun）
# ---------------------------------------------------------------------------

def _run_maaend_phase(cfg: Config, dryrun: bool, should_stop: Callable[[], bool]) -> bool:
    log = get_logger()
    entry = cfg.maaend
    exe = Path(entry.path)
    log.info("========== MAAend 阶段开始（%s）=========", exe)

    # 启动参数：CLI 模式补 --autostart（让 MAAend 立即执行日常实例）
    args = entry.args
    if entry.normalized_mode("cli") == "cli" and "--autostart" not in args:
        args = (args + " --autostart").strip()
    run_entry = AppEntry(**{**entry.__dict__, "args": args})

    apps.launch_program(run_entry, dryrun)

    # DRY-RUN：到此为止，不监控真实进程
    if dryrun:
        log.info("[DRY-RUN] MAAend 已“启动”，跳过进程监控与完成检测")
        return True

    # 弹窗处理线程（长驻）
    dismisser: Optional[MaaEndPopupDismisser] = None
    if cfg.dismiss_maaend_popups and not dryrun:
        dismisser = MaaEndPopupDismisser(
            exe.name, cfg.dismiss_timeout_min, should_stop)
        dismisser.start()

    try:
        exe_name = exe.name
        reruns = 0
        while True:
            pids = wait_process_stable(
                lambda: wintools.pids_by_name(exe_name), stable_sec=10,
                timeout_sec=600, should_stop=should_stop)
            if not pids:
                log.error("MAAend 进程未稳定（可能启动失败）")
                return False
            log.info("MAAend 已稳定（PID=%s）", pids)

            ok = wait_for_marker(
                _maaend_log_paths(cfg), "tasks-completed",
                timeout_sec=entry.timeout_min * 60, should_stop=should_stop)
            if ok:
                return True

            # 未完成：可能是更新重启打断了运行（PID 变化）
            cur = wintools.pids_by_name(exe_name)
            if reruns < MAX_RERUN and cur and set(cur) != set(pids):
                reruns += 1
                log.warning("检测到 MAAend 更新重启，重跑日常（第 %s 次，--autostart）", reruns)
                if not dryrun:
                    apps.launch_program(
                        AppEntry(**{**entry.__dict__, "args": "--autostart"}), dryrun)
                continue
            log.error("MAAend 完成标记超时且未见更新重启，判定失败")
            return False
    finally:
        if dismisser:
            dismisser.stop()
        if entry.close_after and not dryrun:
            apps.close_entry(entry, cfg.emulator, dryrun)


# ---------------------------------------------------------------------------
# MAA 阶段（原 click_maa_linkstart + Watch-MaaRun）
# ---------------------------------------------------------------------------

def _trigger_maa(cfg: Config, dryrun: bool, should_stop: Callable[[], bool],
                 rerun: bool) -> bool:
    """触发 MAA 开始跑日常。click=图像点击器；hotkey=窗口出现后发全局热键。"""
    log = get_logger()
    exe_name = Path(cfg.maa.path).name
    mode = cfg.maa.normalized_mode("hotkey")

    if dryrun:
        log.info("[DRY-RUN] 跳过 MAA 触发（模式=%s）", mode)
        return True

    if mode == "click":
        clicker = LinkStartClicker(cfg, exe_name, _logs_dir(cfg),
                                   should_stop, dryrun)
        return clicker.run()
    if mode == "hotkey":
        hwnd = _wait_maa_window(exe_name, should_stop)
        if not hwnd:
            log.error("未等到 MAA 主窗口，无法发送快捷键")
            return False
        if dryrun:
            log.info("[DRY-RUN] 跳过发送快捷键 %s", cfg.hotkey)
            return True
        ok = wintools.send_hotkey(cfg.hotkey)
        log.info("已发送快捷键 %s（%s）", cfg.hotkey, "成功" if ok else "失败")
        return ok
    log.info("MAA 启动方式=open：不主动触发，交由 MAA 自身设置/人工处理")
    return True


def _wait_maa_window(exe_name: str, should_stop: Callable[[], bool],
                     timeout_sec: float = 300) -> Optional[int]:
    from .wintools import main_window_hwnd
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline and not should_stop():
        hwnd = main_window_hwnd(exe_name)
        if hwnd:
            return hwnd
        time.sleep(2)
    return None


def _logs_dir(cfg: Config) -> Path:
    from .config import logs_root
    return logs_root(cfg)


def _run_maa_phase(cfg: Config, dryrun: bool, should_stop: Callable[[], bool]) -> bool:
    log = get_logger()
    entry = cfg.maa
    exe = Path(entry.path)
    log.info("========== MAA 阶段开始（%s）=========", exe)

    if cfg.emulator.enabled:
        if not apps.start_emulator_and_game(cfg.emulator, dryrun):
            log.error("模拟器/游戏启动失败")
            return False

    apps.launch_program(entry, dryrun)
    if not _trigger_maa(cfg, dryrun, should_stop, rerun=False):
        log.error("MAA 未能开始执行（点击/快捷键均失败）")
        return False

    # DRY-RUN：到此为止，不监控真实进程
    if dryrun:
        log.info("[DRY-RUN] MAA 已“启动”，跳过完成监控")
        return True

    exe_name = exe.name
    reruns = 0
    while True:
        ok = wait_for_marker(
            _maa_log_paths(cfg), "任务已全部完成！",
            timeout_sec=entry.timeout_min * 60, should_stop=should_stop)
        if ok:
            return True
        # 更新重启检测：PID 集合相对稳定基线发生变化则重触发
        cur = set(wintools.pids_by_name(exe_name))
        if reruns < MAX_RERUN and cur:
            reruns += 1
            log.warning("检测到 MAA 可能更新重启，重新触发（第 %s 次）", reruns)
            apps.launch_program(entry, dryrun)
            if not _trigger_maa(cfg, dryrun, should_stop, rerun=True):
                return False
            continue
        # 超时：截图留证（方案 B）
        shot = None if dryrun else save_debug_png(_logs_dir(cfg), "maa_stuck_timeout")
        if shot:
            log.info("超时截图已保存：%s", shot)
        log.error("MAA 完成标记超时，判定失败")
        return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(cfg: Config, dryrun: bool = False, force: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
        skip_gate: bool = False) -> RunResult:
    log = get_logger()
    should_stop = _should_stop_factory(should_stop)
    result = RunResult()

    # 1. 时间闸门（必须放在任何副作用之前 —— 原项目设计红线）
    if not skip_gate and not force:
        allowed, why = gate_status(cfg.gate)
        log.info(why)
        if not allowed:
            return result
    result.started = True
    if dryrun:
        log.info("DRY-RUN 演练模式：不启动程序、不写计划任务、不实际关机")

    # 2. 提权自检（UIPI 隔离：MAAend/Endfield 带管理员清单）
    if wintools.is_windows() and not wintools.is_admin() and not dryrun:
        log.warning("当前不是管理员权限：向 MAAend/Endfield 发送输入可能被 UIPI 拦截。"
                    "建议通过计划任务（/RL HIGHEST）启动本工具")

    # 3. 路径自检（原 Test-RequiredPaths：路径失效一眼可见）
    for name, entry, key in (("MAAend", cfg.maaend, "maaend_ok"),
                             ("MAA", cfg.maa, "maa_ok")):
        if not entry.enabled:
            continue
        ok, why = apps.validate_entry(entry)
        if not ok:
            setattr(result, key, False)   # 启用但路径无效 -> 明确记为失败
            result.errors.append(f"{name}: {why}")
            log.error("[ERROR] %s 路径校验失败：%s", name, why)

    preflight_failed = bool(result.errors)
    if preflight_failed:
        # 预检失败默认保持开机（便于白天排查）；但用户明确选择
        # “失败也关机”时必须遵从其选择
        if not (cfg.shutdown.enabled and cfg.shutdown.on_failure == "shutdown"):
            log.warning("预检失败，按默认策略保持开机"
                        "（如需失败也关机，请在 GUI 将“失败时”改为“仍然关机”）")
            return result
        log.warning("预检失败，按用户设置“失败也关机”处理")

    # 4. 依次执行（原项目架构决策：先终末地后明日方舟，顺次串行）
    if not preflight_failed:
        if cfg.maaend.enabled:
            result.maaend_ok = _run_maaend_phase(cfg, dryrun, should_stop)
            log.info("MAAend 阶段结果：%s", "成功" if result.maaend_ok else "失败")
        if cfg.maa.enabled:
            result.maa_ok = _run_maa_phase(cfg, dryrun, should_stop)
            log.info("MAA 阶段结果：%s", "成功" if result.maa_ok else "失败")

    # 5. 关机决策
    success = result.all_ok
    if not cfg.maa.enabled and not cfg.maaend.enabled:
        log.warning("未启用任何自启动目标（请在 GUI 中勾选 MAA / MAAEnd）")
        return result

    should_shutdown = cfg.shutdown.enabled and (success or cfg.shutdown.on_failure == "shutdown")
    if should_shutdown:
        if not success:
            log.warning("按配置“失败也关机”执行（如不希望，请在 GUI 改为失败保持开机）")
        grace = max(10, cfg.shutdown.grace_sec)
        if dryrun:
            log.info("[DRY-RUN] 跳过关机（原将执行 shutdown /s /t %s）", grace)
        elif sys.platform == "win32":
            try:
                subprocess.run(["shutdown", "/s", "/t", str(grace)],
                               check=True, capture_output=True, timeout=30)
                log.info("已安排 %s 秒后关机", grace)
                result.shutdown_scheduled = True
            except (OSError, subprocess.SubprocessError) as e:
                log.error("关机命令失败：%s", e)
                result.errors.append(f"关机失败: {e}")
        else:
            log.warning("非 Windows 环境跳过关机")
    else:
        if not success:
            log.warning("存在失败任务，按默认策略保持开机，请人工检查日志")
        else:
            log.info("自动关机未启用，保持开机")
    return result
