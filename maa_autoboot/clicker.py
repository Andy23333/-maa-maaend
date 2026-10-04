"""MAA「Link Start!」点击器（移植自原 click_maa_linkstart.py 的三阶段方案）。

阶段 1：等 MAA 主窗口出现，期间持续关闭已知弹窗（公告/版本信息）。
阶段 2：在主窗口内匹配 ``maa_linkstart_btn.png`` 模板并点击。
阶段 3：Link Start 后限时看护，反复截图存证；有 ``maa_ingame_popup_btn.png``
        则精准点掉卡住的游戏内覆盖层。

兜底：模板缺失 / 匹配超时，只要 MAA 进程还在就发全局快捷键
（默认 Ctrl+Shift+Alt+L，需在 MAA 中配置）。任何异常不静默崩溃。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import vision, wintools
from .config import Config
from .logutil import get_logger
from .wintools import click_at, close_window, main_window_hwnd, send_hotkey, send_key_to_hwnd

# 常见弹窗标题关键词（图像模板缺失时的标题兜底）
POPUP_TITLE_KEYWORDS = ("公告", "版本", "更新", "通知", "活动")


class LinkStartClicker:
    def __init__(self, cfg: Config, maa_exe_name: str, log_dir: Path,
                 should_stop: Optional[Callable[[], bool]] = None,
                 dryrun: bool = False):
        self.cfg = cfg
        self.exe_name = maa_exe_name
        self.log_dir = log_dir
        self.should_stop = should_stop or (lambda: False)
        self.dryrun = dryrun
        self.log = get_logger()
        self.stop_event = threading.Event()

    # -- 小工具 ------------------------------------------------------------

    def _stopped(self) -> bool:
        return self.stop_event.is_set() or self.should_stop()

    def _save_shot(self, prefix: str) -> None:
        p = vision.save_debug_png(self.log_dir, prefix)
        if p:
            self.log.info("已保存截图：%s", p.name)

    # -- 弹窗处理 -----------------------------------------------------------

    def _dismiss_known_popups(self, hwnd_map: Optional[dict] = None) -> int:
        """关 MAA 自身弹窗：标题关键词命中 -> WM_CLOSE；失败按 Alt+F4 语义兜底。"""
        closed = 0
        for hwnd, _pid, title in wintools.enum_windows_by_exe(self.exe_name):
            if not title.strip():
                continue
            if any(k in title for k in POPUP_TITLE_KEYWORDS):
                if self.dryrun:
                    self.log.info("[DRY-RUN] 跳过关闭弹窗：%s", title)
                else:
                    if not close_window(hwnd):
                        send_key_to_hwnd(hwnd, 0x1B)  # Esc
                    self.log.info("已尝试关闭弹窗：%s", title)
                closed += 1
        return closed

    # -- 三阶段 --------------------------------------------------------------

    def wait_main_window(self, timeout_sec: float = 300) -> Optional[int]:
        """阶段 1：等主窗口；期间持续关弹窗（弹窗会让主窗口 HWND 缺席）。"""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline and not self._stopped():
            hwnd = main_window_hwnd(self.exe_name)
            if hwnd:
                return hwnd
            self._dismiss_known_popups()
            time.sleep(2)
        return None

    def click_link_start(self, hwnd: int, timeout_sec: float = 180) -> bool:
        """阶段 2：窗口内匹配 Link Start! 模板并点击。"""
        tpl = vision.template_path("maa_linkstart_btn.png")
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline and not self._stopped():
            if self.dryrun:
                self.log.info("[DRY-RUN] 跳过模板匹配点击（%s）", tpl.name)
                return True
            pos = vision.match_in_window_region(hwnd, tpl)
            if pos:
                if click_at(*pos):
                    self.log.info("已点击 Link Start!（%s, %s）", *pos)
                    return True
            self._dismiss_known_popups()
            time.sleep(3)
        return False

    def watchdog_after_linkstart(self, watch_sec: float = 600) -> None:
        """阶段 3（方案 B）：看护期截图留证；有游戏内覆盖层模板则精准点掉。"""
        deadline = time.monotonic() + watch_sec
        tpl = vision.template_path("maa_ingame_popup_btn.png")
        last_shot = 0.0
        while time.monotonic() < deadline and not self._stopped():
            if self.dryrun:
                self.log.info("[DRY-RUN] 跳过看护阶段")
                return
            if tpl.exists():
                pos = vision.match_on_screen(tpl)
                if pos:
                    self.log.info("发现游戏内覆盖层，点击 (%s, %s)", *pos)
                    click_at(*pos)
            elif time.monotonic() - last_shot > 60:
                last_shot = time.monotonic()
                self._save_shot("maa_watchdog")
            time.sleep(5)

    # -- 主入口 --------------------------------------------------------------

    def run(self) -> bool:
        """执行三阶段；返回是否成功触发了 Link Start（点击或快捷键）。"""
        try:
            triggered = self._run_inner()
        except Exception as e:  # 自愈原则：绝不静默崩溃
            self.log.error("点击器异常：%s", e)
            triggered = False
        if not triggered:
            triggered = self._hotkey_fallback()
        return triggered

    def _run_inner(self) -> bool:
        if not vision.vision_available() and self.cfg.maa.start_mode == "click":
            self.log.warning("视觉依赖未安装（%s），直接使用快捷键兜底",
                             vision.missing_vision_deps())
            return False
        self.log.info("点击器启动（阶段1：等待 MAA 主窗口）")
        hwnd = self.wait_main_window()
        if not hwnd:
            self.log.warning("超时未等到 MAA 主窗口")
            return False
        self.log.info("MAA 主窗口就绪（阶段2：点击 Link Start!）")
        if not self.click_link_start(hwnd):
            self.log.warning("模板匹配点击未命中")
            return False
        self.log.info("进入看护阶段（阶段3）")
        self.watchdog_after_linkstart()
        return True

    def _hotkey_fallback(self) -> bool:
        """快捷键兜底：只要 MAA 进程在，发全局热键触发 Link Start!。"""
        if self._stopped() or self.dryrun:
            if self.dryrun and wintools.is_windows() and wintools.pids_by_name(self.exe_name):
                self.log.info("[DRY-RUN] 跳过发送快捷键 %s", self.cfg.hotkey)
            return False
        if not wintools.pids_by_name(self.exe_name):
            self.log.warning("MAA 进程不在，无法发送快捷键兜底")
            return False
        ok = send_hotkey(self.cfg.hotkey)
        self.log.info("快捷键兜底 %s：%s", self.cfg.hotkey, "已发送" if ok else "失败")
        return ok
