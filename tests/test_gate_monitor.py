"""时间闸门与日志监控测试。"""

import datetime as _dt
from pathlib import Path

from maa_autoboot.config import GateConfig
from maa_autoboot.gate import gate_status
from maa_autoboot.monitor import read_new_text, wait_for_marker


def _at(h, m):
    return _dt.datetime(2026, 9, 28, h, m)


def test_gate_inside_window():
    ok, _ = gate_status(GateConfig(), now=_at(6, 0))
    assert ok is True


def test_gate_outside_window():
    ok, msg = gate_status(GateConfig(), now=_at(14, 30))
    assert ok is False
    assert "静默退出" in msg


def test_gate_disabled_always_passes():
    ok, _ = gate_status(GateConfig(enabled=False), now=_at(23, 59))
    assert ok is True


def test_gate_invalid_config_passes_with_hint():
    ok, msg = gate_status(GateConfig(start="abc", end="06:10"), now=_at(6, 0))
    assert ok is True
    assert "无效" in msg


# ---------------------------------------------------------------- monitor

def test_read_new_text_utf8(tmp_path: Path):
    p = tmp_path / "gui.log"
    p.write_text("任务已全部完成！", encoding="utf-8")
    text, off = read_new_text(p, 0)
    assert "任务已全部完成" in text
    assert off == p.stat().st_size
    # 增量读取：无新内容返回空
    text2, off2 = read_new_text(p, off)
    assert text2 == "" and off2 == off


def test_read_new_text_rotated(tmp_path: Path):
    p = tmp_path / "a.log"
    p.write_text("first", encoding="utf-8")
    _, off = read_new_text(p, 0)
    p.write_text("new", encoding="utf-8")     # 轮转后变小
    text, off2 = read_new_text(p, off)
    assert "new" in text and off2 == p.stat().st_size


def test_wait_for_marker(tmp_path: Path):
    marker_file = tmp_path / "debug" / "gui.log"
    marker_file.parent.mkdir()
    marker_file.write_text("[INFO] 开始\n", encoding="utf-8")

    def grow():
        with open(marker_file, "a", encoding="utf-8") as f:
            f.write("任务已全部完成！\n")

    import threading
    threading.Timer(0.2, grow).start()
    assert wait_for_marker([marker_file], "任务已全部完成", 5) is True


def test_wait_for_marker_timeout(tmp_path: Path):
    p = tmp_path / "x.log"
    p.write_text("nothing here", encoding="utf-8")
    assert wait_for_marker([p], "任务已全部完成", 0.5) is False
