# 🧪 Mock 轻量测试包（不跑游戏、不吃配置）

## 原理

MaaAutoBoot 对目标的「完成判定」是**日志标记 + 进程名**，不涉及游戏画面：

| 真实目标 | 工具盯什么 | Mock 怎么模拟 |
|---|---|---|
| MAAEnd | 进程 `MAAEnd.exe` 稳定 10 秒 → `<程序目录>\debug\*.log` 出现 `tasks-completed` | 改名的 `cmd.exe` 存活 15 秒后写入标记再退出 |
| MAA | `<程序目录>\debug\gui.log` 出现 `任务已全部完成！` | 改名的 `cmd.exe` 存活 10 秒后写入标记再退出 |

因此可以**完全不安装 MAA / MAAEnd / 游戏 / 模拟器**，用假进程走完
「启动 → 监控 → 完成检测 → 收尾 → 关机决策」全部真实代码路径。
1 核 1G 的 VM 都绰绰有余，**不需要嵌套虚拟化**。

⚠️ 本包只验证**工具自身逻辑**；MAA 图像识别、游戏内实际表现仍需实机验证（Mock 替代不了）。

## 使用（4 步）

0. 把 `MaaAutoBoot.exe` 复制到本文件夹 → 双击 `setup_mock.cmd`
   （生成假进程 + 便携 `config.json`，之后 GUI / 命令行 / 计划任务都自动用 Mock 配置）
1. **演练**（秒级，不真启动）：
   `MaaAutoBoot.exe --boot --force --dryrun`
2. **Mock 全链路**（约 1 分钟）：
   `MaaAutoBoot.exe --boot --force`
   ⚠️ Mock 配置默认「成功后 15 秒倒计时自动关机」——**请在 VM 里跑**；
   在宿主机上跑请先把 `config.json` 里 `shutdown.enabled` 改为 `false`。
   实时看日志：`powershell -Command "Get-Content logs\maa_autoboot.log -Wait -Tail 30"`
3. **无人值守全链路**（VM 内，管理员 PowerShell）：
   ```powershell
   $env:MAAAUTOBOOT_TASK_NAME="MaaAutoBootTest"; .\MaaAutoBoot.exe --install
   ```
   重启 VM → 登录后自动跑 Mock → VM 自动关机 = 全链路成功。
   `MAAAUTOBOOT_TASK_NAME` 保证测试任务与真实 `MaaAutoBoot` 计划任务**互不干扰**。
4. **清理**：
   ```powershell
   $env:MAAAUTOBOOT_TASK_NAME="MaaAutoBootTest"; .\MaaAutoBoot.exe --uninstall
   ```
   删除本文件夹里的 `MAA.exe` / `MAAEnd.exe` / `config.json` / `logs` / `debug` 即还原。

## 验收要点（日志里应该看到什么）

1. 演练：`[DRY-RUN]` 字样，且**没有任何进程被拉起**
2. Mock 全链路：`MAAend 已稳定（PID=…）` → MAAend 阶段成功 → `MAA 阶段开始` → 关机倒计时
3. 失败路径（可选）：把 `mock_maaend.cmd` 里的 marker 行删掉再跑 → 应判定失败、**不关机**（`on_failure=keep`）
4. 双击 `MaaAutoBoot.exe` 打开 GUI：目标路径应指向本文件夹的两个假 exe（便携配置生效的证明）

## 文件清单

| 文件 | 作用 |
|---|---|
| `setup_mock.cmd` / `setup_mock.ps1` | 一键搭建（假进程 + config.json） |
| `mock_maaend.cmd` | 假 MAAEnd：存活 → `tasks-completed` → 退出 |
| `mock_maa.cmd` | 假 MAA：存活 → `任务已全部完成！` → 退出 |
| `write_marker.ps1` | 以 **UTF-8** 写日志标记（cmd echo 会写 GBK，中文标记永远匹配不上——这是原项目踩过的坑） |
