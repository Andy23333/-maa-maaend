# Changelog

All notable changes will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] - 2026-09-28

- 新增 `tests/mock/` Mock 轻量测试包：不装游戏/模拟器即可验证全链路（含 UTF-8 标记写入脚本与隔离任务名说明）

首个公开版本 —— 个人项目 autoboot-plan 的开源通用化重写。

### Added
- tkinter GUI：勾选自启动目标（仅 MAA / 仅 MAAEnd / 双启），路径、启动方式、
  超时、关机策略全部可视化配置
- 一键安装/卸载 Windows 计划任务（`/RL HIGHEST`，指向打包 EXE，消除原项目
  托管 pythonw 单点风险）
- DRY-RUN 演练（GUI 按钮 + CLI `--dryrun`）
- 关机策略用户可选：GUI 中「失败时 → 保持开机（推荐）/ 仍然关机」，
  覆盖运行超时与路径预检失败两类场景（落地原项目 §8 待办方案 A 并交由用户选择）
- 时间闸门（默认 05:55~06:10）可在 GUI 中调整
- 雷电模拟器（ldconsole）流程配置化
- 图像识别为可选依赖：缺失自动降级为全局快捷键触发（纯 ctypes，零依赖）
- 完整测试（23 项）与 CI（test.yml 三平台 × 三版本矩阵 + build.yml 自动打包发布）
- 提供 `MaaAutoBoot.exe`（PyInstaller onefile，约 11MB，双击即用）；
  CLI 输出强制 UTF-8，修复非中文代码页下 `--help` 打印中文崩溃的问题

### Changed
- PowerShell 编排重写为 Python 单语言实现
- 更新重启重跑次数限制为 1 次（原版存在无限重跑隐患）
