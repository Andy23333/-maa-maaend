"""计划任务命令构造 + 编排器 DRY-RUN 测试（跨平台可跑）。"""

from pathlib import Path

from maa_autoboot import launcher, schtask
from maa_autoboot.config import Config


# ------------------------------------------------------------- schtask

def test_tr_value_quotes_program():
    cmd = schtask.TaskCommand(r"C:\Program Files\App\App.exe", "--boot")
    assert cmd.tr_value() == r'"C:\Program Files\App\App.exe" --boot'


def test_boot_command_source_mode():
    cmd = schtask.build_boot_command()
    assert "--boot" in cmd.args
    assert Path(cmd.program).exists()


def test_task_name_env_isolation(monkeypatch):
    """环境变量 MAAAUTOBOOT_TASK_NAME 可隔离测试任务（不干扰已安装任务）。"""
    monkeypatch.delenv("MAAAUTOBOOT_TASK_NAME", raising=False)
    assert schtask.task_name() == "MaaAutoBoot"
    monkeypatch.setenv("MAAAUTOBOOT_TASK_NAME", "MaaAutoBootTest")
    assert schtask.task_name() == "MaaAutoBootTest"


def test_cli_main_dryrun(capsys, tmp_path, monkeypatch):
    """CLI --boot --dryrun：默认配置未选任何目标 -> 提示并返回失败码 2。"""
    monkeypatch.setenv("MAAAUTOBOOT_CONFIG", str(tmp_path / "config.json"))
    from maa_autoboot.cli import main
    rc = main(["--boot", "--dryrun", "--force"])
    assert rc == 2
    out = capsys.readouterr().err
    assert "DRY-RUN" in out or "未启用" in out


# ------------------------------------------------------------- launcher

def test_nothing_enabled_warns():
    """一个都没勾选：正常进入流程但整体不算成功（避免“啥也没干就关机”）。"""
    r = launcher.run(Config(), dryrun=True, force=True)
    assert r.started
    assert r.maa_ok is None and r.maaend_ok is None
    assert not r.all_ok


def test_enabled_with_missing_path_reports_error():
    cfg = Config()
    cfg.maa.enabled = True
    cfg.maa.path = r"C:\definitely\not\here.exe"
    r = launcher.run(cfg, dryrun=True, force=True)
    assert r.maa_ok is False
    assert not r.all_ok
    assert any("路径" in e for e in r.errors)


def test_dryrun_full_pipeline(tmp_path):
    """双启 + 模拟器 + 关机的 DRY-RUN：不真正启动任何程序、不关机。"""
    fake_maa = tmp_path / "MaaAssistantArknights.exe"
    fake_maa.write_bytes(b"")
    fake_end = tmp_path / "MaaEnd.exe"
    fake_end.write_bytes(b"")
    fake_ld = tmp_path / "ldconsole.exe"
    fake_ld.write_bytes(b"")
    cfg = Config()
    cfg.maa.enabled, cfg.maa.path = True, str(fake_maa)
    cfg.maaend.enabled, cfg.maaend.path = True, str(fake_end)
    cfg.emulator.enabled, cfg.emulator.ldconsole_path = True, str(fake_ld)
    cfg.shutdown.enabled = True
    r = launcher.run(cfg, dryrun=True, force=True)
    assert r.started
    assert r.maa_ok is True and r.maaend_ok is True
    assert r.all_ok
    assert not r.shutdown_scheduled          # DRY-RUN 绝不关机


def test_gate_blocks_without_force(monkeypatch):
    """闸门拦截时不执行任何动作。"""
    monkeypatch.setattr("maa_autoboot.launcher.gate_status",
                        lambda g: (False, "闸门外（测试模拟）"))
    cfg = Config()
    r = launcher.run(cfg, dryrun=True, force=False)
    assert not r.started
    assert not r.all_ok


def test_failure_keep_vs_shutdown_policy(caplog, monkeypatch):
    """用户可选：失败保持开机（默认）/ 失败也关机（含预检失败场景）。"""
    import logging
    # 其余测试可能已调用 setup_logging（propagate=False），
    # 这里强制日志向 root 传播以便 caplog 捕获
    monkeypatch.setattr(logging.getLogger("maa_autoboot"), "propagate", True)
    cfg = Config()
    cfg.maa.enabled = True
    cfg.maa.path = r"C:\definitely\not\here.exe"   # 必然预检失败
    cfg.shutdown.enabled = True

    # 默认策略 keep：保持开机
    with caplog.at_level(logging.INFO, logger="maa_autoboot"):
        r1 = launcher.run(cfg, dryrun=True, force=True)
    assert not r1.all_ok
    assert any("保持开机" in rec.getMessage() for rec in caplog.records)

    # 用户选择 shutdown：失败也关机
    caplog.clear()
    cfg.shutdown.on_failure = "shutdown"
    with caplog.at_level(logging.INFO, logger="maa_autoboot"):
        r2 = launcher.run(cfg, dryrun=True, force=True)
    assert not r2.all_ok
    assert any("失败也关机" in rec.getMessage() for rec in caplog.records)
    assert not r2.shutdown_scheduled              # DRY-RUN 绝不真正关机
