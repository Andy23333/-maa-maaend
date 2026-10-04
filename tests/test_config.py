"""配置读写测试。"""

import json

import pytest

from maa_autoboot.config import (Config, app_base_dir,
                                 config_to_dict, default_config_path,
                                 load_config, save_config)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("MAAAUTOBOOT_CONFIG", str(tmp_path / "config.json"))
    yield


def test_defaults():
    cfg = Config()
    assert cfg.maa.enabled is False
    assert cfg.maaend.enabled is False
    assert cfg.gate.enabled and cfg.gate.start == "05:55" and cfg.gate.end == "06:10"
    assert cfg.shutdown.on_failure == "keep"          # 方案A：失败不关机
    assert cfg.maaend.start_mode == "cli"             # MAAend 默认 CLI 直跑
    assert cfg.maa.start_mode == "hotkey"             # MAA 默认快捷键触发


def test_roundtrip(tmp_path):
    cfg = Config()
    cfg.maa.enabled = True
    cfg.maa.path = r"C:\Tools\Maa\MaaAssistantArknights.exe"
    cfg.maaend.start_mode = "open"
    cfg.maaend.path = r"C:\Tools\MAAEnd\MaaEnd.exe"
    cfg.emulator.enabled = True
    cfg.hotkey = "ctrl+shift+alt+k"
    cfg.shutdown.on_failure = "shutdown"     # 用户可选：失败也关机
    p = save_config(cfg)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["maa"]["enabled"] is True
    assert data["shutdown"]["on_failure"] == "shutdown"
    cfg2 = load_config(p)
    assert cfg2.maa.path == cfg.maa.path
    assert cfg2.maaend.start_mode == "open"
    assert cfg2.hotkey == "ctrl+shift+alt+k"
    assert cfg2.emulator.enabled is True
    assert cfg2.shutdown.on_failure == "shutdown"


def test_on_failure_default_is_keep():
    """默认策略：失败保持开机（原项目方案A）。"""
    assert Config().shutdown.on_failure == "keep"


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert isinstance(cfg, Config)


def test_damaged_file_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{oops not json", encoding="utf-8")
    cfg = load_config(p)
    assert isinstance(cfg, Config)


def test_portable_config_preferred(tmp_path, monkeypatch):
    base = tmp_path / "portable"
    base.mkdir()
    monkeypatch.delenv("MAAAUTOBOOT_CONFIG", raising=False)
    (base / "config.json").write_text(
        json.dumps(config_to_dict(Config())), encoding="utf-8")
    monkeypatch.setattr("maa_autoboot.config.app_base_dir", lambda: base)
    p = default_config_path()
    assert p == base / "config.json"


def test_app_base_dir_creates_on_demand(tmp_path, monkeypatch):
    monkeypatch.setenv("MAAAUTOBOOT_HOME", str(tmp_path / "home"))
    d = app_base_dir()
    assert d.exists()
