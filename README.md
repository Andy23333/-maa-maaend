# MaaAutoBoot — MAA / MAAEnd 开机自动跑日常

[![Tests](https://img.shields.io/badge/tests-24%20passed-brightgreen)](.github/workflows/test.yml)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)]()
[![Python](https://img.shields.io/badge/python-3.9%2B-informational)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

> **一句话定位**：带 GUI 的 Windows 开机自启工具 —— 勾选 **MAA（明日方舟）**、**MAAEnd（终末地）** 或**两者都跑**，
> 每天 6:00 由 BIOS 自动开机后无人值守跑完日常，全部完成自动关机。平时手动开机时它**静默退出，绝不打扰**。

本项目是个人项目 [autoboot-plan]（硬编码路径的 PowerShell/Python 混合脚本）的开源通用化重写版：
所有路径可配置、双击即用的 GUI、开箱即用的计划任务安装、完整的日志与 DRY-RUN 演练支持。

---

## ✨ 功能特性

| 特性 | 说明 |
| --- | --- |
| 🖥️ **图形界面配置** | 勾选自启动目标：**仅 MAA / 仅 MAAEnd / 双启**；路径、参数、超时全部可视化配置 |
| ⏰ **时间闸门** | 只在配置的时间窗口（默认 05:55~06:10）内干活；手动开机一律静默退出（原项目设计红线） |
| 🔁 **自愈机制** | 自动更新重启进程 → 等稳定后自动重跑；弹窗 → 标题/图像识别关闭；任何异常不静默崩溃 |
| 📋 **完成判定** | 严格 UTF-8 解析 MAA `gui.log` / MAAEnd `debug/*.log` 的完成标记，不靠猜时间 |
| 🛡️ **失败不关机** | 默认失败保持开机并醒目记日志（避免失败被"关机"掩盖）；也可配置为失败仍关机 |
| 🧪 **DRY-RUN 演练** | 一键演练全流程：不启动程序、不关机，配置错误一眼可见 |
| 📦 **零依赖启动** | 核心 GUI/编排仅用 Python 标准库；图像识别为**可选**依赖，缺失自动降级（快捷键兜底） |
| 🔐 **无需常驻** | 跑完即退出，不后台驻留、不联网、不上传任何数据 |

---

## 🚀 安装

### 方式一：下载打包版（推荐普通用户）

1. 到 [Releases](../../releases) 页面下载 `MaaAutoBoot.exe`（GitHub Actions 自动构建，约 11 MB）
2. 放到一个**固定位置**（如 `D:\Tools\MaaAutoBoot\`——计划任务会指向它，之后别挪窝）
3. 双击运行 → 勾选自启动目标 → 填好路径 → 点「安装 / 更新」计划任务，完成

> 💡 首次运行如遇 SmartScreen 蓝色提示（开源程序未签名），点「更多信息 → 仍要运行」。
> 个别杀软对 PyInstaller 单文件有误报，可加白名单，或自行源码构建 / 核对 CI 产物。

### 方式二：源码运行

```bash
git clone https://github.com/<you>/maa-autoboot.git
cd maa-autoboot
python run_boot.py            # 打开 GUI（需要 Python 3.9+，tkinter 随标准安装）
```

可选视觉依赖（MAA「图像识别点击」模式需要；不装则自动降级为快捷键模式）：

```bash
pip install opencv-python numpy pillow
```

---

## 🖱️ 快速开始（3 分钟）

1. **打开 GUI** → 在「① 自启动目标」勾选：
   - ☑ **MAAEnd** —— 自动跑终末地日常（默认 `CLI 直接执行 --autostart` 模式，跑完即完）
   - ☑ **MAA** —— 自动跑明日方舟日常（默认 `全局快捷键触发` 模式，零依赖）
   - 只勾一个 = 只跑它；两个都勾 = 先 MAAEnd 后 MAA 串行执行
2. **填路径**：两个程序的 `exe` 路径（点「浏览」选择）；用模拟器跑方舟的再填 `ldconsole.exe`
3. **保存设置**（配置写入 `%APPDATA%\MaaAutoBoot\config.json`）
4. **DRY-RUN 演练**：日志区会逐步打印将要做的事，确认无误
5. **安装开机自启任务**：点「安装/更新计划任务」→ 完成。
   开机后本工具在时间闸门内自动执行，跑完按配置自动关机。

> 💡 **MAA 侧需要做一件事**：把 MAA 设置里的「Link Start!」快捷键设为
> `Ctrl+Shift+Alt+L`（与 GUI 中一致，可在本工具里改）。若想用更稳的"图像点击"模式，
> 见 [docs/DEVELOPING.md](docs/DEVELOPING.md) 的模板截图说明。

---

## 🌅 6:00 全自动无人值守（可选进阶）

要实现"人还在睡觉，电脑自己开机跑日常再关机"，需要三件套（均为 Windows/BIOS 自带功能）：

1. **BIOS RTC Alarm**：主板 BIOS 中设置每天 06:00 自动开机（各品牌叫法：RTC 自动开机 / 定时开机）
2. **Windows 自动登录**：`netplwiz` 取消"必须输入用户名和密码"，或注册表 `AutoAdminLogon`
3. **本工具的计划任务**：GUI 一键安装，登录后自动运行，静默执行

安全边界：即使 BIOS 误开机，不在时间闸门内时本工具**什么都不做**，电脑停在桌面等你。

---

## ⚙️ 工作原理

```
BIOS RTC 06:00 开机 → Windows 自动登录 → 计划任务(MaaAutoBoot, 最高权限)
    → 时间闸门检查（闸门外 → 静默退出）
    → MAAend 阶段：启动 MaaEnd.exe --autostart
        ├── 弹窗处理线程（更新弹窗关闭 / 公告"我知道了"图像识别）
        └── 监控 debug/*.log 出现 tasks-completed → 成功
    → MAA 阶段：(可选) ldconsole 启动模拟器 + 唤起游戏
        ├── 启动 MAA，触发：图像点击「Link Start!」/ 全局快捷键 / 仅启动
        └── 监控 gui.log 出现 「任务已全部完成！」→ 成功
    → 收尾：结束相关进程 → 全部成功则自动关机（失败默认保持开机）
```

自愈细节（继承自原项目实测经验）：

- **更新重启**：检测到进程 PID 变化 → 等待进程稳定 → 自动重跑一次（上限 1 次，防死循环）
- **编码坑**：所有日志读取强制 UTF-8（MAA 日志是 UTF-8，用 GBK 读中文标记永远匹配不到）
- **UIPI 隔离**：MaaEnd/Endfield 带管理员清单，因此计划任务以 `/RL HIGHEST` 运行，并向 MAA 发送输入需要同权限

---

## 📖 配置参考（config.json）

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `maa.enabled` / `maaend.enabled` | `false` | **自启动目标勾选**（GUI 核心） |
| `maa.path` / `maaend.path` | — | 程序 exe 完整路径 |
| `maa.start_mode` | `hotkey` | `click` 图像点击 / `hotkey` 快捷键 / `open` 仅启动 |
| `maaend.start_mode` | `cli` | `cli` 执行 `--autostart` / `open` 仅打开（依赖其内部定时） |
| `*.timeout_min` | 180 / 30 | 完成判定超时（分钟） |
| `*.close_after` | `true` | 完成后结束该程序 |
| `emulator.*` | 关 | 雷电模拟器 `ldconsole` 路径、实例序号、包名、启动等待 |
| `gate.*` | 05:55~06:10 | 时间闸门窗口与开关 |
| `shutdown.enabled` | `true` | 全部成功后自动关机 |
| `shutdown.on_failure` | `keep` | 失败时 `keep` 保持开机 / `shutdown` 仍然关机 |
| `hotkey` | `ctrl+shift+alt+l` | 快捷键触发模式使用的组合键 |

---

## 🧪 在已有自启脚本的电脑上隔离测试

电脑上已跑着别的自启方案（如原版 `AutoBootLauncher` 计划任务）时，按下面三层递进，全程零冲突：

1. **第一层 · 演练（零副作用）**：GUI 填好路径后点「演练一次」，或
   `MaaAutoBoot.exe --boot --dryrun --force`。不启动程序、不关机、不写计划任务，
   用来验证配置与编排逻辑。
2. **第二层 · 同机真实试跑（不装计划任务）**：GUI 里把「全部成功后自动关机」先取消勾选，
   只勾选一个目标，然后手动执行 `MaaAutoBoot.exe --boot --force`。跑完对比
   `%APPDATA%\MaaAutoBoot\logs\` 与旧脚本的 `boot_*.log` 时间戳即可评估各阶段耗时。
   ⚠️ 测试期**不要点「安装/更新」计划任务**——新旧任务同时存在会双重执行。
3. **第三层 · 双任务并存对照（可选）**：确需安装计划任务对照时，用环境变量把测试实例
   挂到独立任务名上，不动任何现有任务：
   ```bat
   set MAAAUTOBOOT_TASK_NAME=MaaAutoBootTest
   set MAAAUTOBOOT_CONFIG=%APPDATA%\MaaAutoBoot\config-test.json
   MaaAutoBoot.exe
   ```
   测完在同名环境下点「卸载」即可。旧脚本若要临时停用：`schtasks /Change /TN AutoBootLauncher /DISABLE`。

资源占用参考：本工具自身长期驻留时段几乎为 0% CPU / ~20MB 内存（纯等待与日志监控），
真正的性能开销在 MAA / MAAEnd / 模拟器本身，与旧方案一致。

### 🖥️ VMware 虚拟机测试（推荐的全链路沙盒）

1. **建 VM**：Win10/11 x64，≥2核/4GB（只测 MAAEnd+MAA）；要跑雷电模拟器则 ≥4核/8GB，
   并且 **处理器设置勾选「虚拟化 Intel VT-x/EPT」**（嵌套虚拟化，模拟器必需）。
   安装 VMware Tools，开启时间同步（避免挂起恢复后时钟漂移触发误判）。
2. **装环境**：VM 内安装 MAA / MAAEnd / 游戏客户端（或从宿主机复制现成目录），
   显示分辨率固定、缩放 100%（截图模板与实机不通用，需在 VM 内重新截取）。
3. **配置工具**：`MaaAutoBoot.exe` 拷入 VM → GUI 勾选目标、填路径 →
   先「演练一次」，再取消勾选自动关机后 `--boot --force` 真跑一轮。
4. **无人值守链路**：`netplwiz` 设自动登录（账户须为管理员）→ GUI「安装/更新」计划任务
   → **重启 VM** 验证登录后自动执行。VM 没有 BIOS RTC 唤醒，用宿主机计划任务代替：
   `vmrun -T ws start "D:\VMs\Win11.vmx"`（vmrun 位于 VMware 安装目录）。
5. **关机验证**：恢复勾选自动关机 → 任务完成后 VM 自动关机，宿主机看到 powered off 即全链路成功。
6. **打快照**：环境配好后先拍快照再开测，任何翻车一键回滚——这是 VM 测试的核心优势。

⚠️ 注意：① 嵌套虚拟化下模拟器性能比裸机低 20~40%，性能数据仅供参考，上线以实机为准；
② VM 内闸门外的静默退出是设计行为，不是故障（手动测试请用 `--force`）；③ 测自动关机要用真关机而非挂起。

### 🧪 Mock 轻量测试（不用跑游戏，1核1G VM 就够）

VM 跑不动游戏？不需要跑！完成判定靠的是**日志标记 + 进程名**，`tests/mock/`
用改名 cmd.exe 模拟 MAA / MAAEnd 的「启动→忙→完成→退出」，走完全部真实代码路径：

```bat
cd tests\mock
:: 0) 把 MaaAutoBoot.exe 复制到本目录，然后双击 setup_mock.cmd
MaaAutoBoot.exe --boot --force --dryrun   :: 1) 演练（秒级）
MaaAutoBoot.exe --boot --force            :: 2) Mock 全链路（约1分钟，成功后自动关机，请在VM里跑）
```

无人值守测试用独立任务名，不碰真实计划任务：
`$env:MAAAUTOBOOT_TASK_NAME="MaaAutoBootTest"; .\MaaAutoBoot.exe --install`
详见 `tests/mock/README.md`。

## ❓ 常见问题

<details>
<summary><b>提示"不是管理员权限" / 按键被拦截</b></summary>

MaaEnd 与终末地本体带管理员清单，Windows UIPI 会拦截低权限进程向它们发送输入。
请通过 GUI 的「安装计划任务」（以 `/RL HIGHEST` 运行）启动，而不是直接双击 EXE。
</details>

<details>
<summary><b>图像点击模式提示缺依赖</b></summary>

`pip install opencv-python numpy pillow`，或直接使用默认的快捷键模式（零依赖）。
依赖缺失时工具自动降级，不会崩溃。
</details>

<details>
<summary><b>中文完成标记永远匹配不到、只能等超时</b></summary>

说明有代码用了非 UTF-8 读日志 —— 本工具已全部强制 UTF-8。若你在改代码，请保持
`open(..., encoding="utf-8")`（教训来自原项目 §8.2）。
</details>

<details>
<summary><b>MAA 卡在游戏内弹窗（点不掉"进入游戏"覆盖层）</b></summary>

快捷键模式只能触发 Link Start，进游戏后的覆盖层需要图像识别方案：
截取弹窗按钮图片存为 `templates/maa_ingame_popup_btn.png`（见 docs/DEVELOPING.md）。
</details>

<details>
<summary><b>残留提权进程杀不掉（拒绝访问）</b></summary>

非管理员会话杀不掉提权进程。最省事的处理是直接重启；或以管理员运行本工具的收尾清理。
</details>

---

## 🧑‍💻 开发

```bash
pip install -r requirements-dev.txt
pytest                 # 21 项测试（跨平台可跑，Windows API 自动跳过）
python -m maa_autoboot --boot --dryrun --force    # 命令行演练
```

打包 EXE（本地或交给 CI）：

```bash
pyinstaller --noconfirm --onefile --windowed --name MaaAutoBoot \
    --icon assets/icon.ico entry.py
```

推送 `v*` 标签时 GitHub Actions 自动构建并发布 Release。
架构与踩坑交接文档见 **[docs/DEVELOPING.md](docs/DEVELOPING.md)**。

---

## 📄 免责声明

本工具仅负责"启动你已安装的 MAA / MAAEnd 并在完成后关机"，
不修改、不逆向、不分发上述软件本身。使用自动化工具请知悉并遵守
鹰角网络的用户协议与封号风险提示，风险自担。

## 🙏 致谢

- [MAA (MaaAssistantArknights)](https://github.com/MaaAssistantArknights/MaaAssistantArknights)
- [MAAEnd](https://github.com/——/MAAEnd)（终末地助手）
- 原项目 autoboot-plan 的全部实测数据与设计经验

## License

[MIT](LICENSE)
