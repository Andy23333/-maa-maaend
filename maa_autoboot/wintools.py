"""Windows 原生能力封装（纯 ctypes，零第三方依赖）。

包含原项目用 PowerShell / pyautogui 完成的事：
提权检测、进程枚举、窗口枚举、全局快捷键发送、鼠标点击。
所有函数在非 Windows 平台安全降级（返回空 / 抛出明确异常），便于开发与 CI。
"""

from __future__ import annotations

import sys
from typing import Iterable, List, Optional, Tuple

_IS_WINDOWS = sys.platform == "win32"


class WindowsOnlyError(RuntimeError):
    """在非 Windows 环境调用 Windows 专属能力。"""


def is_windows() -> bool:
    return _IS_WINDOWS


# ---------------------------------------------------------------------------
# 提权（原项目 §8.6：MaaEnd/Endfield 带管理员清单，UIPI 隔离要求本进程也是管理员）
# ---------------------------------------------------------------------------

def is_admin() -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_elevation() -> bool:
    """弹出 UAC 重新以管理员启动自身（GUI 内使用，需要用户点确认）。"""
    if not _IS_WINDOWS:
        raise WindowsOnlyError("request_elevation 仅支持 Windows")
    import ctypes
    params = " ".join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1)  # SW_SHOWNORMAL
    return int(ret) > 32


# ---------------------------------------------------------------------------
# 进程枚举（CreateToolhelp32Snapshot，替代原 pyautogui/PowerShell Get-Process）
# ---------------------------------------------------------------------------

def list_processes() -> List[Tuple[int, str]]:
    """返回 [(pid, 小写进程名), ...]。非 Windows 返回空列表。"""
    if not _IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x2

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    result: List[Tuple[int, str]] = []
    if snap == -1:
        return result
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        result.append((int(entry.th32ProcessID), entry.szExeFile.lower()))
        ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    kernel32.CloseHandle(snap)
    return result


def pids_by_name(image_name: str) -> List[int]:
    name = image_name.lower()
    return [pid for pid, exe in list_processes() if exe == name]


# ---------------------------------------------------------------------------
# 窗口枚举（对应原 click_maa_linkstart.py 的 enum_windows_by_exe / pick_main_window）
# ---------------------------------------------------------------------------

def enum_windows_by_exe(image_name: str) -> List[Tuple[int, int, str]]:
    """返回属于指定进程名的可见顶层窗口 [(hwnd, pid, title), ...]。"""
    if not _IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes

    target_pids = set(pids_by_name(image_name))
    if not target_pids:
        return []

    user32 = ctypes.windll.user32
    results: List[Tuple[int, int, str]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) in target_pids:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            results.append((int(hwnd), int(pid.value), buf.value))
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return results


def main_window_hwnd(image_name: str) -> Optional[int]:
    """挑“主窗口”：可见、有标题、尺寸最大的那个（弹窗会让主窗口暂时缺席，
    这是原项目三阶段点击器里先关弹窗的原因）。"""
    wins = [w for w in enum_windows_by_exe(image_name) if w[2].strip()]
    if not wins:
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    best, best_area = None, -1
    for hwnd, _pid, _title in wins:
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            if area > best_area:
                best, best_area = hwnd, area
    return best


# ---------------------------------------------------------------------------
# 键鼠输入（全局快捷键 / 点击，零 pyautogui）
# ---------------------------------------------------------------------------

_VK_MAP = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}
for _ch in "abcdefghijklmnopqrstuvwxyz":
    _VK_MAP[_ch] = ord(_ch.upper())
for _i in range(0, 10):
    _VK_MAP[str(_i)] = 0x30 + _i


def send_hotkey(combo: str) -> bool:
    """发送全局快捷键（如 "ctrl+shift+alt+l"）。

    原理：MAA 通过 RegisterHotKey 注册全局热键，无论窗口是否聚焦都会收到
    WM_HOTKEY，因此这是图像识别失败后最稳的兜底（原项目 §6.3）。
    """
    if not _IS_WINDOWS:
        raise WindowsOnlyError("send_hotkey 仅支持 Windows")
    import ctypes
    keys = [k.strip().lower() for k in combo.split("+") if k.strip()]
    vks = []
    for k in keys:
        if k not in _VK_MAP:
            return False
        vks.append(_VK_MAP[k])
    keybd = ctypes.windll.user32.keybd_event
    for vk in vks:
        keybd(vk, 0, 0, 0)
    for vk in reversed(vks):
        keybd(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
    return True


def click_at(x: int, y: int) -> bool:
    """移动鼠标并左键单击（SetCursorPos + mouse_event，替代 pyautogui.click）。"""
    if not _IS_WINDOWS:
        raise WindowsOnlyError("click_at 仅支持 Windows")
    import ctypes
    user32 = ctypes.windll.user32
    if not user32.SetCursorPos(int(x), int(y)):
        return False
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True


def send_key_to_hwnd(hwnd: int, vk: int) -> bool:
    """向指定窗口 PostMessage 按键（关更新弹窗用：Enter/Space/Esc 逐个试）。"""
    if not _IS_WINDOWS:
        raise WindowsOnlyError("send_key_to_hwnd 仅支持 Windows")
    import ctypes
    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    user32 = ctypes.windll.user32
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
    return True


def close_window(hwnd: int) -> bool:
    """礼貌关闭窗口（WM_CLOSE，等价于点右上角 X）。"""
    if not _IS_WINDOWS:
        raise WindowsOnlyError("close_window 仅支持 Windows")
    import ctypes
    return bool(ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0))  # WM_CLOSE


def get_foreground_window() -> Optional[int]:
    if not _IS_WINDOWS:
        return None
    import ctypes
    return ctypes.windll.user32.GetForegroundWindow() or None


def window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """返回 (left, top, right, bottom)；DPI 感知由调用方在进程级设置。"""
    if not _IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def set_dpi_aware() -> None:
    """进程级 DPI 感知，保证截图/坐标在高分屏下不缩放错位（原项目做法）。"""
    if not _IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def kill_processes(image_names: Iterable[str]) -> int:
    """taskkill /F 结束指定进程（原 Close-MaaEndAndGame 的收尾清理）。"""
    import subprocess
    killed = 0
    for name in image_names:
        if not name:
            continue
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/IM", name], capture_output=True, timeout=30)
            if r.returncode == 0:
                killed += 1
        except (OSError, subprocess.SubprocessError):
            pass
    return killed
