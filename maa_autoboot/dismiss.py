"""MAAend 弹窗处理（移植自原 dismiss_maaend_update.py，长驻线程）。

处理两类弹窗：
1. 更新完成弹窗 —— 标题关键词命中 -> Enter/Space/Esc 逐个试 -> WM_CLOSE；
2. 「新动态」公告弹窗 —— WebView2 渲染，需模板 ``maaend_iknow_btn.png``
   多尺度匹配「我知道了」绿色按钮；沿父进程链判定归属 MAAend 才点，防误点。

cv2 缺失时自动降级为「仅标题匹配」，不崩溃（原项目自愈原则）。
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

from . import vision, wintools
from .logutil import get_logger
from .wintools import close_window, send_key_to_hwnd

UPDATE_TITLE_KEYWORDS = ("更新", "升级", "版本")
ENTER, SPACE, ESC = 0x0D, 0x20, 0x1B


class MaaEndPopupDismisser(threading.Thread):
    """daemon 线程：跑在 MAAend 阶段全程，超时自动退出。"""

    def __init__(self, maaend_exe_name: str, timeout_min: float,
                 should_stop: Optional[Callable[[], bool]] = None,
                 dryrun: bool = False):
        super().__init__(daemon=True, name="maaend-popup-dismisser")
        self.exe_name = maaend_exe_name
        self.timeout_sec = timeout_min * 60
        self.should_stop = should_stop or (lambda: False)
        self.dryrun = dryrun
        self.stop_event = threading.Event()
        self.log = get_logger()

    # -- 进程归属判定（2026-09-24 修正版：沿父进程链，WebView 子进程也算） --

    def _build_pid_map(self) -> dict:
        ppid_of = {}
        for pid, name in wintools.list_processes():
            ppid_of.setdefault(pid, name)
        return ppid_of

    def _is_maaend_owned(self, pid: int, pid_map: dict) -> bool:
        """pid 自身或其 WebView2 子进程是否归属于 MAAend 弹窗场景。"""
        exe = self.exe_name.lower()
        cur = pid
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            name = pid_map.get(cur)
            if name and name == exe:
                return True
            # toolhelp 快照不含 PPID，无法继续回溯父链；
            # WebView2 子进程（msedgewebview2）只可能服务于宿主弹窗，视为归属
            if name and "msedgewebview2" in name:
                return True
            break
        return False

    # -- 弹窗识别与处理 ------------------------------------------------------

    def _find_popups(self) -> List[Tuple[int, int, str]]:
        pid_map = self._build_pid_map()
        out = []
        for hwnd, pid, title in wintools.enum_windows_by_exe(self.exe_name):
            if title.strip() and self._is_maaend_owned(pid, pid_map):
                out.append((hwnd, pid, title))
        return out

    def _close_update_popup(self, hwnd: int, title: str) -> None:
        if self.dryrun:
            self.log.info("[DRY-RUN] 跳过处理更新弹窗：%s", title)
            return
        for vk in (ENTER, SPACE, ESC):
            send_key_to_hwnd(hwnd, vk)
            time.sleep(0.3)
            if not wintools.is_windows() or not wintools.enum_windows_by_exe(self.exe_name):
                break
        close_window(hwnd)
        self.log.info("已处理更新弹窗：%s", title)

    def _handle_announce_popups(self) -> int:
        """「新动态」公告：模板多尺度匹配「我知道了」按钮。"""
        tpl = vision.template_path("maaend_iknow_btn.png")
        if not vision.vision_available() or not tpl.exists():
            return 0  # 降级：交给标题分支
        handled = 0
        from .wintools import window_rect
        for hwnd, _pid, title in self._find_popups():
            rect = window_rect(hwnd)
            if not rect:
                continue
            screen = vision.grab_screen()
            if screen is None:
                return handled
            l, t, r, b = rect
            l, t = max(0, l), max(0, t)
            region = screen[t:b, l:r]
            if region.size == 0:
                continue
            pos = vision.match_multiscale(region, tpl)
            if pos and not self.dryrun:
                wintools.click_at(l + pos[0], t + pos[1])
                self.log.info("已点击公告「我知道了」(%s, %s)", *pos)
                handled += 1
            elif pos and self.dryrun:
                self.log.info("[DRY-RUN] 跳过点击公告按钮")
                handled += 1
        return handled

    # -- 线程主循环（整轮 try/except，任何异常不退出） -----------------------

    def run(self) -> None:
        self.log.info("MAAend 弹窗处理线程启动（%.0f 分钟后自动退出）",
                      self.timeout_sec / 60)
        deadline = time.monotonic() + self.timeout_sec
        while time.monotonic() < deadline:
            if self.stop_event.is_set() or self.should_stop():
                break
            try:
                for hwnd, _pid, title in self._find_popups():
                    if any(k in title for k in UPDATE_TITLE_KEYWORDS):
                        self._close_update_popup(hwnd, title)
                self._handle_announce_popups()
            except Exception as e:  # 自愈原则
                self.log.error("弹窗处理轮异常（继续）：%s", e)
            time.sleep(3)
        self.log.info("MAAend 弹窗处理线程退出")

    def stop(self) -> None:
        self.stop_event.set()
