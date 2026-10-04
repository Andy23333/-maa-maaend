"""视觉能力（可选依赖）：模板匹配 + 截图留证。

设计原则（沿用原项目自愈哲学）：
- cv2 / numpy / pillow 缺失时 ``vision_available()`` 返回 False，
  上层自动降级（快捷键兜底 / 仅标题匹配），**绝不崩溃**。
- 模板图片放在 ``templates/``（EXE 旁或仓库根），由用户按 README 自行截取，
  因为按钮样式与分辨率/皮肤强相关，官方不预置。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional, Tuple

TEMPLATE_DIR_NAME = "templates"


def templates_dir() -> Path:
    from .config import app_base_dir
    return app_base_dir() / TEMPLATE_DIR_NAME


def template_path(name: str) -> Path:
    return templates_dir() / name


def vision_available() -> bool:
    """cv2 + numpy + PIL 全部可导入才算可用。"""
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def missing_vision_deps() -> str:
    missing = []
    for mod, pkg in (("cv2", "opencv-python"), ("numpy", "numpy"), ("PIL", "pillow")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    return ", ".join(missing)


def save_debug_png(out_dir: Path, prefix: str) -> Optional[Path]:
    """全屏截图留证（排查卡屏用）。失败返回 None，不影响主流程。"""
    try:
        from PIL import ImageGrab
    except ImportError:
        return None
    if sys.platform != "win32":
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"{prefix}_{stamp}.png"
    try:
        ImageGrab.grab().save(out)
        return out
    except OSError:
        return None


def grab_screen():
    """抓全屏返回 BGR ndarray；依赖缺失/非 Windows 返回 None。"""
    if not vision_available() or sys.platform != "win32":
        return None
    import cv2
    import numpy
    from PIL import ImageGrab
    img = ImageGrab.grab()
    arr = numpy.asarray(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def match_on_screen(template_png: Path, threshold: float = 0.8) -> Optional[Tuple[int, int]]:
    """在整屏中匹配模板，返回命中中心坐标 (x, y)；未命中/依赖缺失返回 None。"""
    if not template_png.exists():
        return None
    screen = grab_screen()
    if screen is None:
        return None
    import cv2
    tpl = cv2.imread(str(template_png), cv2.IMREAD_COLOR)
    if tpl is None:
        return None
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None
    h, w = tpl.shape[:2]
    return max_loc[0] + w // 2, max_loc[1] + h // 2


def match_in_window_region(
    hwnd: int, template_png: Path, threshold: float = 0.8,
) -> Optional[Tuple[int, int]]:
    """在指定窗口区域内匹配（截图整屏后裁剪窗口矩形再匹配）。"""
    from .wintools import window_rect
    rect = window_rect(hwnd)
    if rect is None:
        return None
    screen = grab_screen()
    if screen is None:
        return None
    if not template_png.exists():
        return None
    import cv2
    l, t, r, b = rect
    l, t = max(0, l), max(0, t)
    region = screen[t:b, l:r]
    if region.size == 0:
        return None
    tpl = cv2.imread(str(template_png), cv2.IMREAD_COLOR)
    if tpl is None:
        return None
    res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None
    h, w = tpl.shape[:2]
    return l + max_loc[0] + w // 2, t + max_loc[1] + h // 2


def match_multiscale(region, template_png: Path, threshold: float = 0.8):
    """多尺度匹配（MAAend 公告弹窗是 WebView2 渲染，DPI 缩放会导致尺寸差异）。"""
    import cv2
    tpl = cv2.imread(str(template_png), cv2.IMREAD_COLOR)
    if tpl is None:
        return None
    best = (None, 0.0)
    for scale in (1.0, 0.9, 1.1, 0.8, 1.25):
        resized = cv2.resize(tpl, None, fx=scale, fy=scale) if scale != 1.0 else tpl
        th, tw = resized.shape[:2]
        if th >= region.shape[0] or tw >= region.shape[1]:
            continue
        res = cv2.matchTemplate(region, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best[1]:
            best = ((max_loc[0] + tw // 2, max_loc[1] + th // 2), max_val)
    if best[1] >= threshold:
        return best[0]
    return None
