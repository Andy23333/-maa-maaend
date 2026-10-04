"""时间闸门（原项目设计红线：只在窗口内干活，平时手动开机静默退出）。"""

from __future__ import annotations

import datetime as _dt
from typing import Optional, Tuple

from .config import GateConfig


def parse_hhmm(text: str) -> Optional[_dt.time]:
    try:
        h, m = text.strip().split(":")
        return _dt.time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def gate_status(gate: GateConfig, now: Optional[_dt.datetime] = None) -> Tuple[bool, str]:
    """返回 (是否放行, 说明)。解析失败视为配置错误 -> 放行并提示（不静默拦死）。"""
    now = now or _dt.datetime.now()
    start = parse_hhmm(gate.start)
    end = parse_hhmm(gate.end)
    if not gate.enabled:
        return True, "时间闸门未启用"
    if start is None or end is None or start >= end:
        return True, f"时间闸门配置无效（{gate.start}~{gate.end}），已放行"
    if start <= now.time() <= end:
        return True, f"当前 {now:%H:%M} 在闸门窗口 {gate.start}~{gate.end} 内"
    return False, (
        f"当前 {now:%H:%M} 不在自动运行窗口 {gate.start}~{gate.end} 内，"
        "按设计红线静默退出（手动运行可加 --force 绕过）")
