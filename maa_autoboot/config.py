"""配置管理：所有原本硬编码在脚本里的路径 / 参数，全部集中到这里。

配置文件位置（优先级从高到低）：
1. 环境变量 ``MAAAUTOBOOT_CONFIG`` 指定的路径
2. 便携模式：程序目录（或其父目录）下的 ``config.json`` —— 适合绿色免安装
3. 默认位置：Windows 为 ``%APPDATA%\\MaaAutoBoot\\config.json``，
   其他平台为 ``~/.config/MaaAutoBoot/config.json``（便于跨平台开发调试）
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

from . import APP_NAME

CONFIG_VERSION = 1

# MAA / MAAEnd 完成标记（来自原项目实测，UTF-8 匹配；可在 GUI 中修改）
MAA_DONE_MARKER = "任务已全部完成！"
MAAEND_DONE_MARKER = "tasks-completed"

# 全局快捷键兜底触发 MAA「Link Start!」（需在 MAA 界面设置同样的快捷键）
DEFAULT_HOTKEY = "ctrl+shift+alt+l"

MAA_START_MODES = ("click", "hotkey", "open")
MAAEND_START_MODES = ("cli", "open")


@dataclass
class GateConfig:
    """时间闸门：只在窗口内干活，平时手动开机一律静默退出（原项目设计红线）。"""

    enabled: bool = True
    start: str = "05:55"
    end: str = "06:10"


@dataclass
class AppEntry:
    """单个自动化目标（MAA 或 MAAEnd）的配置。"""

    enabled: bool = False
    path: str = ""                       # 主程序绝对路径，如 C:\\maa\\MAA.exe
    args: str = ""                       # 额外命令行参数
    start_mode: str = ""                 # 启动方式，见 MAA_START_MODES / MAAEND_START_MODES
    timeout_min: int = 90                # 完成监控超时（分钟）
    close_after: bool = True             # 跑完后关闭该程序（及关联游戏进程）
    kill_names: list[str] = field(default_factory=list)  # 收尾时额外结束的进程名

    def normalized_mode(self, default: str) -> str:
        return self.start_mode if self.start_mode in ("cli", "open", "click", "hotkey") else default


@dataclass
class EmulatorConfig:
    """明日方舟走雷电模拟器的启动参数（不使用模拟器的用户可整体关闭）。"""

    enabled: bool = False
    ldconsole_path: str = ""             # 如 D:\LDPlayer\LDPlayer9\ldconsole.exe
    index: int = 0
    package: str = "com.hypergryph.arknights"
    launch_wait_sec: int = 60            # 启动模拟器后等待游戏进入的秒数


@dataclass
class ShutdownConfig:
    """关机策略。默认“失败不关机”（原项目已知待办 方案A 的落地实现）。"""

    enabled: bool = True                 # 全部成功后自动关机
    grace_sec: int = 60                  # 关机倒计时宽限
    on_failure: str = "keep"             # keep=失败保持开机(推荐) / shutdown=失败也关机


@dataclass
class Config:
    version: int = CONFIG_VERSION
    gate: GateConfig = field(default_factory=GateConfig)
    emulator: EmulatorConfig = field(default_factory=EmulatorConfig)
    shutdown: ShutdownConfig = field(default_factory=ShutdownConfig)

    maaend: AppEntry = field(default_factory=lambda: AppEntry(
        enabled=False, path="",
        start_mode="cli", timeout_min=180, close_after=True,
        kill_names=["MaaEnd.exe", "Endfield.exe", "qmlauncher.exe"],
    ))
    maa: AppEntry = field(default_factory=lambda: AppEntry(
        enabled=False, path="",
        start_mode="hotkey", timeout_min=90, close_after=True,
        kill_names=["MAA.exe"],
    ))

    # MAAend 弹窗处理（更新完成/新动态公告），需要视觉依赖，缺失时自动降级
    dismiss_maaend_popups: bool = True
    dismiss_timeout_min: int = 25
    # MAA「Link Start!」全局快捷键（图像识别失败时的兜底）
    hotkey: str = DEFAULT_HOTKEY
    # 运行日志目录；留空 = 默认位置
    log_dir: str = ""


# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------

def app_base_dir() -> Path:
    """程序自身目录（打包成 EXE 时为 EXE 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    env = os.environ.get("MAAAUTOBOOT_CONFIG")
    if env:
        return Path(env)
    # 便携模式：EXE / 仓库根目录旁的 config.json
    portable = app_base_dir() / "config.json"
    if portable.exists():
        return portable
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME / "config.json"
    return Path.home() / ".config" / APP_NAME / "config.json"


def default_log_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME / "logs"
    return Path.home() / ".config" / APP_NAME / "logs"


def logs_root(config: Config) -> Path:
    return Path(config.log_dir) if config.log_dir else default_log_dir()


# ---------------------------------------------------------------------------
# 序列化（容忍缺字段 / 多字段，向前兼容）
# ---------------------------------------------------------------------------

def _merge_dataclass(dc: Any, data: Dict[str, Any]) -> Any:
    """把 dict 合入 dataclass 实例：仅接受已存在的字段，类型尽量容错。"""
    for f in dc.__dataclass_fields__.values():
        if f.name not in data:
            continue
        raw = data[f.name]
        cur = getattr(dc, f.name)
        if isinstance(cur, bool):
            setattr(dc, f.name, bool(raw))
        elif isinstance(cur, int) and not isinstance(cur, bool):
            try:
                setattr(dc, f.name, int(raw))
            except (TypeError, ValueError):
                pass
        elif isinstance(cur, list):
            if isinstance(raw, list):
                setattr(dc, f.name, [str(x) for x in raw])
        else:
            setattr(dc, f.name, str(raw) if raw is not None else cur)
    return dc


def config_to_dict(cfg: Config) -> Dict[str, Any]:
    return asdict(cfg)


def config_from_dict(data: Dict[str, Any]) -> Config:
    cfg = Config()
    if not isinstance(data, dict):
        return cfg
    cfg.version = int(data.get("version", CONFIG_VERSION) or CONFIG_VERSION)
    if isinstance(data.get("gate"), dict):
        _merge_dataclass(cfg.gate, data["gate"])
    if isinstance(data.get("emulator"), dict):
        _merge_dataclass(cfg.emulator, data["emulator"])
    if isinstance(data.get("shutdown"), dict):
        _merge_dataclass(cfg.shutdown, data["shutdown"])
    if isinstance(data.get("maaend"), dict):
        _merge_dataclass(cfg.maaend, data["maaend"])
    if isinstance(data.get("maa"), dict):
        _merge_dataclass(cfg.maa, data["maa"])
    cfg.dismiss_maaend_popups = bool(data.get("dismiss_maaend_popups", True))
    cfg.dismiss_timeout_min = int(data.get("dismiss_timeout_min", 25) or 25)
    cfg.hotkey = str(data.get("hotkey", DEFAULT_HOTKEY) or DEFAULT_HOTKEY)
    cfg.log_dir = str(data.get("log_dir", "") or "")
    return cfg


def load_config(path: Path | str | None = None) -> Config:
    p = Path(path) if path else default_config_path()
    if not p.exists():
        return Config()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 配置损坏时不崩溃，退回默认值（自愈原则）
        return Config()
    return config_from_dict(data if isinstance(data, dict) else {})


def save_config(cfg: Config, path: Path | str | None = None) -> Path:
    p = Path(path) if path else default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config_to_dict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
