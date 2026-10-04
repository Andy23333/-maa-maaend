# DEVELOPING.md — 开发者交接文档

> 面向接手开发与维护的工程师。回答「架构是什么、每个文件干什么、有哪些坑、怎么打包」。
> 使用手册见根目录 [README.md](../README.md)。

## 1. 目录结构

```
maa-autoboot/
├── entry.py                 # PyInstaller 打包入口（GUI + 兼容 --boot）
├── run_boot.py              # 源码运行入口（计划任务指向它 + pythonw）
├── maa_autoboot/
│   ├── cli.py               # 命令行解析：--boot/--dryrun/--force/--install/--uninstall/--status
│   ├── config.py            # 配置 dataclass + JSON 读写 + 路径解析（便携模式优先）
│   ├── gate.py              # 时间闸门（设计红线：闸门外一律静默退出）
│   ├── schtask.py           # schtasks 封装：安装/卸载/查询开机自启计划任务
│   ├── launcher.py          # ★ 主编排：闸门→自检→MAAend→MAA→关机决策
│   ├── apps.py              # 程序/模拟器启动、参数拼装、进程收尾
│   ├── monitor.py           # 日志增量读取(UTF-8!)、完成标记匹配、进程稳定检测
│   ├── wintools.py          # 纯 ctypes：提权/枚举窗口/进程/快捷键/点击/DPI
│   ├── vision.py            # 可选视觉：cv2 模板匹配、截图留证（缺依赖自动降级）
│   ├── clicker.py           # MAA「Link Start!」三阶段点击器（模板+快捷键兜底）
│   ├── dismiss.py           # MAAend 弹窗处理线程（更新弹窗/公告按钮）
│   ├── gui.py               # ★ tkinter GUI（零第三方依赖）
│   └── logutil.py           # 日志（RotatingFileHandler，UTF-8）
├── tests/                   # pytest：config/gate/monitor/schtask/launcher 全覆盖
├── assets/icon.ico          # scripts/make_icon.py 生成
├── templates/               # 用户自截的图像模板（见 §3）
└── .github/workflows/       # test.yml（3 系统×3 版本）+ build.yml（打包发布）
```

## 2. 关键设计决策

| 决策 | 理由 |
| --- | --- |
| PowerShell 编排 → Python 重写 | 消除 PS+PY 双解释器/双编码坑；GUI、编排、点击器统一运行时；可测试 |
| 计划任务 Action 指向 EXE | 原项目指向"托管 pythonw.exe"，pip 升级清空 site-packages 即断（单点风险）；打包版无解释器依赖 |
| MAAend 默认 `--autostart` CLI 模式 | 阻塞式直跑，完成判定清晰；保留 `open` 模式兼容其内部 6:05 定时用法 |
| MAA 默认快捷键触发 | 零依赖、不受分辨率/皮肤影响；图像点击为可选增强 |
| 失败默认不关机 | 原版"失败也关机"掩盖问题（原 §8 待办方案 A）；如需旧行为改 `shutdown.on_failure` |
| 重跑上限 1 次 | 原版存在无限重跑隐患 |
| 所有非 Windows 调用可降级 | 便于跨平台开发、CI 与单元测试（winreg/ctypes.windll 全部懒加载守卫） |

## 3. 图像模板（templates/）

视觉模式按文件名取模板，**由用户按自己分辨率截取**（按钮样式与 MAA 版本/皮肤/DPI 强相关，官方不预置）：

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `maa_linkstart_btn.png` | MAA 主界面绿色「Link Start!」按钮 | 点击器阶段 2 精准点击 |
| `maa_ingame_popup_btn.png` | 游戏内覆盖层的按钮（如「进入游戏」） | 看护阶段精准点掉卡屏弹窗（原项目 §8 待办闭环） |
| `maaend_iknow_btn.png` | MAAend 公告弹窗「我知道了」按钮 | dismiss 线程多尺度匹配点击 |

GUI「打开模板目录」按钮可直达该目录。任何模板缺失 → 自动降级（标题匹配/快捷键），不崩溃。

截图方法：游戏/助手全屏置于弹窗画面 → `Win+Shift+S` 框选**只含按钮本体** → 保存为上表文件名。

## 4. 常用命令

```bash
pip install -r requirements-dev.txt
pytest                                     # 全部测试
python -m maa_autoboot                     # GUI
python -m maa_autoboot --boot --dryrun --force      # 演练
python -m maa_autoboot --boot --force               # 立即真实执行（绕过闸门）
python -m maa_autoboot --status            # 查询计划任务
python scripts/make_icon.py                # 重新生成图标
```

## 5. 打包发布

```bash
pyinstaller --noconfirm --onefile --windowed --name MaaAutoBoot \
    --icon assets/icon.ico entry.py
# 产物 dist/MaaAutoBoot.exe；计划任务 Action 自动指向它
```

发布流程：推 tag `v*` → GitHub Actions `build.yml` 在 windows-latest 构建 → 自动创建 Release 并附 EXE。

## 6. 踩坑清单（继承 + 新增）

1. **UTF-8**：MAA/MAAEnd 日志为 UTF-8 无 BOM。任何读取必须显式 `encoding="utf-8"`，
   否则中文完成标记（`任务已全部完成！`）永远匹配不到 → 只能超时关机（原 §8.2 血泪）。
2. **UIPI**：向 MaaEnd/Endfield 发送键鼠的进程必须是管理员（它们带 requireAdministrator 清单）。
   计划任务务必 `/RL HIGHEST`；非提权会话演练时只做日志演示。
3. **schtasks 引号**：`/TR` 的程序路径必须整体加引号且参数跟在外面，嵌套引号是重灾区
   （本仓库 `TaskCommand.tr_value()` 统一处理，有测试覆盖）。
4. **时间闸门必须最先检查**：任何副作用（启动/关机）之前。手动开机静默退出是核心用户体验。
5. **DRY-RUN 不许有任何真实副作用**：不启动进程、不等待窗口、不关机（测试锁定了这一点）。
6. **配置损坏不崩溃**：`load_config` 解析失败返回默认值（宁可重填也不白屏）。
7. **弹窗处理线程必须 daemon + 整轮 try/except**：线程死了 = 弹窗卡死整条流水线（自愈原则）。

## 7. 与原项目（autoboot-plan）的迁移对照

| 原 | 新 |
| --- | --- |
| `launcher.ps1` 编排 | `launcher.py` |
| `run_hidden.pyw` | `entry.py --boot`（EXE 内置） |
| `click_maa_linkstart.py` | `clicker.py`（pyautogui → 纯 ctypes） |
| `dismiss_maaend_update.py` | `dismiss.py` |
| `Test-RequiredPaths` | `apps.validate_entry` + 启动前自检 |
| 计划任务手工 `schtasks /Create` | GUI 一键安装（`schtask.py`） |
| `AUTORUN_DRYRUN=1` 环境变量 | `--dryrun` 参数 + GUI 演练按钮 |
| 硬编码 `C:\maa\maa ark` 等路径 | `config.json`（GUI 可视化编辑） |

原项目特有的 BIOS RTC + netplwiz 自动登录设置保持不变（README §进阶）。
