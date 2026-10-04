"""完成监控：日志标记匹配（UTF-8！）与进程稳定性检测。

核心经验（原项目 §8.2）：
- MAA 完成标记：``gui.log`` 出现 「任务已全部完成！」
- MAAEnd 完成标记：``debug/*.log`` 出现 ``tasks-completed``
- 匹配必须用 UTF-8 解码，否则中文永远匹配不到。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from .logutil import get_logger


def find_log_files(app_dir: Path, patterns: List[str]) -> List[Path]:
    """在应用目录下按 glob 找日志（如 debug/gui.log、debug/*.log）。"""
    files: List[Path] = []
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        files.extend(p for p in app_dir.glob(pat) if p.is_file())
    return sorted(set(files))


def read_new_text(path: Path, offset: int) -> "tuple[str, int]":
    """从 offset 起增量读取，严格 UTF-8 解码，返回 (新文本, 新 offset)。

    以二进制打开 + 手动解码：即便日志被写坏也不会抛异常中断监控。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return "", offset
    if size < offset:            # 日志被轮转/重建
        offset = 0
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            raw = f.read()
    except OSError:
        return "", offset
    return raw.decode("utf-8", errors="replace"), size


def wait_for_marker(
    log_files: List[Path],
    marker: str,
    timeout_sec: float,
    should_stop: Optional[Callable[[], bool]] = None,
    poll_sec: float = 3.0,
    on_progress: Optional[Callable[[float], None]] = None,
) -> bool:
    """轮询日志增量，直到出现完成标记 / 超时 / 外部要求停止。

    返回 True=检测到完成标记。
    """
    log = get_logger()
    offsets = {p: p.stat().st_size if p.exists() else 0 for p in log_files}
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            return False
        for p in log_files:
            text, offsets[p] = read_new_text(p, offsets.get(p, 0))
            if marker and marker in text:
                log.info("在 %s 检测到完成标记 %r", p.name, marker)
                return True
        if on_progress:
            on_progress(timeout_sec - (deadline - time.monotonic()))
        time.sleep(poll_sec)
    log.warning("等待完成标记 %r 超时（%.0f 秒）", marker, timeout_sec)
    return False


def wait_process_stable(
    pid_getter: Callable[[], List[int]],
    stable_sec: float = 15.0,
    timeout_sec: float = 300.0,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Optional[int]:
    """等待进程集合“连续稳定” —— PID 集合连续 stable_sec 不变化。

    背景：自动更新会重启整个程序，PID 变化 = 更新重启中。
    返回稳定后的 PID 列表；超时/停止返回 None。
    """
    log = get_logger()
    deadline = time.monotonic() + timeout_sec
    last: Optional[frozenset] = None
    stable_since: Optional[float] = None
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            return None
        cur = frozenset(pid_getter())
        now = time.monotonic()
        if cur and cur == last:
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= stable_sec:
                return sorted(cur)
        else:
            stable_since = None
            last = cur
        time.sleep(1.0)
    log.warning("等待进程稳定超时（%.0f 秒）", timeout_sec)
    return None
