"""tkinter GUI —— 用户选择自启动 MAA / MAAEnd / 都自运行，并管理所有配置。

零第三方依赖（tkinter 为 Python 标准库），Windows / Linux 均可打开。
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from . import __version__, schtask, vision, wintools
from .config import Config, save_config
from .logutil import setup_logging

_MAAMODE_TEXT = {"click": "图像识别点击（推荐，需视觉依赖）",
                 "hotkey": "全局快捷键触发（零依赖）",
                 "open": "仅启动 MAA，不主动触发"}
_MAAMODE_VAL = {v: k for k, v in _MAAMODE_TEXT.items()}
_ENDMODE_TEXT = {"cli": "CLI 直接执行 --autostart（推荐）",
                 "open": "仅打开程序（依赖 MAAend 内部定时）"}
_ENDMODE_VAL = {v: k for k, v in _ENDMODE_TEXT.items()}


class App(tk.Tk):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.title(f"MAA 自启动助手 v{__version__}")
        self.geometry("760x640")
        self.minsize(720, 600)
        self._normalize_fonts()
        self._logq: "queue.Queue[str]" = queue.Queue()
        self._build_vars()
        self._build_ui()
        self._update_mode_label()
        self._refresh_task_status()
        self.after(100, self._poll_log_queue)

    def _normalize_fonts(self) -> None:
        """跨平台选一个支持中文的界面字体（Windows: 微软雅黑；Linux: Noto/文泉驿）。"""
        try:
            import tkinter.font as tkfont
            families = set(tkfont.families(self))
            for fam in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑",
                        "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC",
                        "Sarasa Mono SC", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei"):
                if fam in families:
                    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                                 "TkHeadingFont", "TkCaptionFont"):
                        try:
                            tkfont.nametofont(name).configure(family=fam)
                        except tk.TclError:
                            pass
                    break
        except Exception:
            pass

    # ------------------------------------------------------------------ vars
    def _build_vars(self) -> None:
        c = self.cfg
        self.v_maa_enabled = tk.BooleanVar(value=c.maa.enabled)
        self.v_maaend_enabled = tk.BooleanVar(value=c.maaend.enabled)
        self.v_maa_path = tk.StringVar(value=c.maa.path)
        self.v_maaend_path = tk.StringVar(value=c.maaend.path)
        self.v_maa_args = tk.StringVar(value=c.maa.args)
        self.v_maaend_args = tk.StringVar(value=c.maaend.args)
        self.v_maa_mode = tk.StringVar(value=_MAAMODE_TEXT.get(
            c.maa.normalized_mode("hotkey"), _MAAMODE_TEXT["hotkey"]))
        self.v_maaend_mode = tk.StringVar(value=_ENDMODE_TEXT.get(
            c.maaend.normalized_mode("cli"), _ENDMODE_TEXT["cli"]))
        self.v_maa_timeout = tk.IntVar(value=c.maa.timeout_min)
        self.v_maaend_timeout = tk.IntVar(value=c.maaend.timeout_min)
        self.v_maa_close = tk.BooleanVar(value=c.maa.close_after)
        self.v_maaend_close = tk.BooleanVar(value=c.maaend.close_after)
        self.v_emu_enabled = tk.BooleanVar(value=c.emulator.enabled)
        self.v_emu_path = tk.StringVar(value=c.emulator.ldconsole_path)
        self.v_emu_index = tk.IntVar(value=c.emulator.index)
        self.v_emu_pkg = tk.StringVar(value=c.emulator.package)
        self.v_emu_wait = tk.IntVar(value=c.emulator.launch_wait_sec)
        self.v_gate_enabled = tk.BooleanVar(value=c.gate.enabled)
        self.v_gate_start = tk.StringVar(value=c.gate.start)
        self.v_gate_end = tk.StringVar(value=c.gate.end)
        self.v_shutdown = tk.BooleanVar(value=c.shutdown.enabled)
        self.v_shutdown_grace = tk.IntVar(value=c.shutdown.grace_sec)
        self.v_on_fail = tk.StringVar(value="保持开机（推荐）"
                                      if c.shutdown.on_failure == "keep" else "仍然关机")
        self.v_hotkey = tk.StringVar(value=c.hotkey)
        self.v_dismiss = tk.BooleanVar(value=c.dismiss_maaend_popups)

    # -------------------------------------------------------------------- ui
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, **pad)

        # ① 自启动目标（核心需求：MAA / MAAEnd / 都自运行）
        g1 = ttk.LabelFrame(outer, text=" ① 自启动目标（开机后自动跑哪个的日常）")
        g1.pack(fill="x", **pad)
        row = ttk.Frame(g1); row.pack(fill="x", padx=6, pady=4)
        ttk.Checkbutton(row, text="MAAEnd（明日方舟：终末地）",
                        variable=self.v_maaend_enabled,
                        command=self._update_mode_label).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(row, text="MAA（明日方舟，配合雷电模拟器）",
                        variable=self.v_maa_enabled,
                        command=self._update_mode_label).pack(side="left")
        self.l_mode = ttk.Label(g1, text="", foreground="#0a7")
        self.l_mode.pack(anchor="w", padx=6)
        self._update_mode_label()

        # ② 路径与参数
        g2 = ttk.LabelFrame(outer, text=" ② 路径与参数")
        g2.pack(fill="x", **pad)
        self._entry_row(g2, "MAAEnd 主程序", self.v_maaend_path,
                        lambda: self._browse(self.v_maaend_path))
        self._entry_row(g2, "MAA 主程序", self.v_maa_path,
                        lambda: self._browse(self.v_maa_path))
        row = ttk.Frame(g2); row.pack(fill="x", padx=6, pady=2)
        ttk.Label(row, text="MAAEnd 启动方式").grid(row=0, column=0, sticky="w")
        ttk.Combobox(row, textvariable=self.v_maaend_mode, state="readonly",
                     width=36, values=list(_ENDMODE_TEXT.values())
                     ).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row, text="超时(分)").grid(row=0, column=2, padx=(18, 2))
        ttk.Spinbox(row, from_=10, to=600, textvariable=self.v_maaend_timeout,
                    width=6).grid(row=0, column=3)
        ttk.Checkbutton(row, text="跑完关闭", variable=self.v_maaend_close
                        ).grid(row=0, column=4, padx=10)
        row2 = ttk.Frame(g2); row2.pack(fill="x", padx=6, pady=2)
        ttk.Label(row2, text="MAA 启动方式　　").grid(row=0, column=0, sticky="w")
        ttk.Combobox(row2, textvariable=self.v_maa_mode, state="readonly",
                     width=36, values=list(_MAAMODE_TEXT.values())
                     ).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row2, text="超时(分)").grid(row=0, column=2, padx=(18, 2))
        ttk.Spinbox(row2, from_=10, to=600, textvariable=self.v_maa_timeout,
                    width=6).grid(row=0, column=3)
        ttk.Checkbutton(row2, text="跑完关闭", variable=self.v_maa_close
                        ).grid(row=0, column=4, padx=10)
        row3 = ttk.Frame(g2); row3.pack(fill="x", padx=6, pady=2)
        ttk.Label(row3, text="MAA「Link Start!」快捷键").grid(row=0, column=0)
        ttk.Entry(row3, textvariable=self.v_hotkey, width=20
                  ).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Checkbutton(row3, text="自动关闭 MAAend 更新/公告弹窗（需视觉依赖，缺失自动降级）",
                        variable=self.v_dismiss).grid(row=0, column=2, padx=10)

        # ③ 模拟器（明日方舟链路）
        g3 = ttk.LabelFrame(outer, text=" ③ 雷电模拟器（MAA 用；PC 端用户可取消勾选）")
        g3.pack(fill="x", **pad)
        ttk.Checkbutton(g3, text="通过 ldconsole 启动模拟器与明日方舟",
                        variable=self.v_emu_enabled).pack(anchor="w", padx=6)
        self._entry_row(g3, "ldconsole 路径", self.v_emu_path,
                        lambda: self._browse(self.v_emu_path))
        row = ttk.Frame(g3); row.pack(fill="x", padx=6, pady=2)
        ttk.Label(row, text="模拟器索引").pack(side="left")
        ttk.Spinbox(row, from_=0, to=8, textvariable=self.v_emu_index,
                    width=4).pack(side="left", padx=4)
        ttk.Label(row, text="明日方舟包名").pack(side="left", padx=(12, 0))
        ttk.Entry(row, textvariable=self.v_emu_pkg, width=30).pack(side="left", padx=4)
        ttk.Label(row, text="启动等待(秒)").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row, from_=10, to=600, textvariable=self.v_emu_wait,
                    width=6).pack(side="left", padx=4)

        # ④ 时间闸门与关机
        g4 = ttk.LabelFrame(outer, text=" ④ 时间闸门与关机（闸门外手动开机不会触发任何动作）")
        g4.pack(fill="x", **pad)
        row = ttk.Frame(g4); row.pack(fill="x", padx=6, pady=2)
        ttk.Checkbutton(row, text="启用时间闸门", variable=self.v_gate_enabled
                        ).pack(side="left")
        ttk.Label(row, text="窗口").pack(side="left", padx=(10, 2))
        ttk.Entry(row, textvariable=self.v_gate_start, width=7).pack(side="left")
        ttk.Label(row, text="~").pack(side="left")
        ttk.Entry(row, textvariable=self.v_gate_end, width=7).pack(side="left")
        ttk.Checkbutton(row, text="全部成功后自动关机", variable=self.v_shutdown
                        ).pack(side="left", padx=(18, 0))
        ttk.Label(row, text="宽限(秒)").pack(side="left", padx=(10, 2))
        ttk.Spinbox(row, from_=10, to=600, textvariable=self.v_shutdown_grace,
                    width=6).pack(side="left")
        ttk.Label(row, text="失败时").pack(side="left", padx=(18, 2))
        ttk.Combobox(row, textvariable=self.v_on_fail, state="readonly", width=16,
                     values=["保持开机（推荐）", "仍然关机"]).pack(side="left")

        # ⑤ 计划任务
        g5 = ttk.LabelFrame(outer, text=" ⑤ 开机自启（Windows 计划任务，登录时触发 + 最高权限）")
        g5.pack(fill="x", **pad)
        row = ttk.Frame(g5); row.pack(fill="x", padx=6, pady=2)
        self.l_task = ttk.Label(row, text="计划任务状态：检测中…")
        self.l_task.pack(side="left")
        ttk.Button(row, text="安装 / 更新", command=self._install_task,
                   width=12).pack(side="left", padx=10)
        ttk.Button(row, text="卸载", command=self._uninstall_task,
                   width=8).pack(side="left")

        # ⑥ 操作区
        g6 = ttk.Frame(outer); g6.pack(fill="x", **pad)
        ttk.Button(g6, text="💾 保存设置", command=self._save).pack(side="left")
        ttk.Button(g6, text="▶ 演练一次（DRY-RUN，不启动不关机）",
                   command=self._dryrun).pack(side="left", padx=8)
        ttk.Button(g6, text="打开日志目录", command=self._open_logs).pack(side="left", padx=8)
        ttk.Button(g6, text="打开模板目录", command=self._open_templates).pack(side="left")
        if not vision.vision_available():
            ttk.Label(g6, text="（视觉依赖未安装：图像点击不可用，快捷键方式不受影响）",
                      foreground="#a60").pack(side="left", padx=10)

        # 日志输出
        self.txt = scrolledtext.ScrolledText(outer, height=10, state="disabled",
                                             font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True, **pad)

    def _entry_row(self, parent, label, var, browse_cmd) -> None:
        row = ttk.Frame(parent); row.pack(fill="x", padx=6, pady=2)
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x",
                                              expand=True, padx=6)
        ttk.Button(row, text="浏览…", command=browse_cmd, width=7).pack(side="left")

    def _browse(self, var: tk.StringVar) -> None:
        p = filedialog.askopenfilename(
            filetypes=[("可执行程序", "*.exe"), ("所有文件", "*.*")])
        if p:
            var.set(p)

    def _update_mode_label(self) -> None:
        m, e = self.v_maa_enabled.get(), self.v_maaend_enabled.get()
        if m and e:
            text = "当前模式：MAAEnd → MAA 顺次执行，全部完成后自动关机"
        elif m:
            text = "当前模式：仅自动运行 MAA（明日方舟）"
        elif e:
            text = "当前模式：仅自动运行 MAAEnd（终末地）"
        else:
            text = "⚠ 尚未选择任何自启动目标，请至少勾选一个"
        self.l_mode.config(text=text)

    # ------------------------------------------------------------ config io
    def _collect(self) -> None:
        c = self.cfg
        c.maa.enabled = self.v_maa_enabled.get()
        c.maa.path = self.v_maa_path.get().strip()
        c.maa.args = self.v_maa_args.get().strip()
        c.maa.start_mode = _MAAMODE_VAL.get(self.v_maa_mode.get(), "hotkey")
        c.maa.timeout_min = int(self.v_maa_timeout.get())
        c.maa.close_after = self.v_maa_close.get()
        c.maaend.enabled = self.v_maaend_enabled.get()
        c.maaend.path = self.v_maaend_path.get().strip()
        c.maaend.args = self.v_maaend_args.get().strip()
        c.maaend.start_mode = _ENDMODE_VAL.get(self.v_maaend_mode.get(), "cli")
        c.maaend.timeout_min = int(self.v_maaend_timeout.get())
        c.maaend.close_after = self.v_maaend_close.get()
        c.emulator.enabled = self.v_emu_enabled.get()
        c.emulator.ldconsole_path = self.v_emu_path.get().strip()
        c.emulator.index = int(self.v_emu_index.get())
        c.emulator.package = self.v_emu_pkg.get().strip()
        c.emulator.launch_wait_sec = int(self.v_emu_wait.get())
        c.gate.enabled = self.v_gate_enabled.get()
        c.gate.start = self.v_gate_start.get().strip()
        c.gate.end = self.v_gate_end.get().strip()
        c.shutdown.enabled = self.v_shutdown.get()
        c.shutdown.grace_sec = int(self.v_shutdown_grace.get())
        c.shutdown.on_failure = "keep" if "保持" in self.v_on_fail.get() else "shutdown"
        c.hotkey = self.v_hotkey.get().strip()
        c.dismiss_maaend_popups = self.v_dismiss.get()

    def _save(self) -> None:
        self._collect()
        path = save_config(self.cfg)
        messagebox.showinfo("已保存", f"配置已写入：\n{path}")

    # ------------------------------------------------------------ plan task
    def _refresh_task_status(self) -> None:
        if sys.platform != "win32":
            self.l_task.config(text="计划任务状态：仅 Windows 支持")
            return
        self.l_task.config(
            text="计划任务状态：已安装 ✔" if schtask.task_exists()
            else "计划任务状态：未安装（安装后才能开机自动运行）")

    def _install_task(self) -> None:
        self._collect()
        save_config(self.cfg)
        if sys.platform != "win32":
            messagebox.showwarning("不支持", "计划任务仅 Windows 支持")
            return
        if not wintools.is_admin():
            # 弹 UAC 用管理员身份执行 --install
            if wintools.is_windows():
                import ctypes
                prog, arg = (sys.executable, "--install") if getattr(
                    sys, "frozen", False) else (
                    sys.executable, f'"{schtask_build_ref()}" --install')
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", prog, arg, None, 1)
                if int(ret) > 32:
                    messagebox.showinfo("需要授权", "已弹出 UAC 授权窗口，请在弹窗中确认。")
                else:
                    messagebox.showwarning("未授权", "UAC 授权被取消，计划任务未安装。")
            self.after(1500, self._refresh_task_status)
            return
        ok, msg = schtask.install_task(schtask.build_boot_command())
        self._append_log(("✔ " if ok else "✘ ") + msg + "\n")
        self._refresh_task_status()

    def _uninstall_task(self) -> None:
        ok, msg = schtask.uninstall_task()
        self._append_log(("✔ " if ok else "✘ ") + msg + "\n")
        self._refresh_task_status()

    # ------------------------------------------------------------ dry run
    def _dryrun(self) -> None:
        self._collect()
        self._append_log("\n===== DRY-RUN 演练开始 =====\n")
        t = threading.Thread(target=self._dryrun_worker, daemon=True)
        t.start()

    def _dryrun_worker(self) -> None:
        from . import launcher
        from .config import logs_root
        setup_logging(logs_root(self.cfg), console=False)
        _attach_queue_handler(self._logq)
        try:
            result = launcher.run(self.cfg, dryrun=True, force=True)
            self._logq.put(f"\n===== 演练结束：{'全部成功' if result.all_ok else '见上方日志'} =====\n")
        except Exception as e:  # GUI 里也绝不崩
            self._logq.put(f"演练异常：{e}\n")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                line = self._logq.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.after(200, self._poll_log_queue)

    def _append_log(self, text: str) -> None:
        self.txt.config(state="normal")
        self.txt.insert("end", text)
        self.txt.see("end")
        self.txt.config(state="disabled")

    # ------------------------------------------------------------ open dirs
    def _open_logs(self) -> None:
        from .config import logs_root
        _open_dir(logs_root(self.cfg))

    def _open_templates(self) -> None:
        _open_dir(vision.templates_dir())


def schtask_build_ref() -> str:
    """源码模式下 --install 需要的入口脚本路径。"""
    from pathlib import Path
    return str(Path(__file__).resolve().parent.parent / "run_boot.py")


def _open_dir(path) -> None:
    from pathlib import Path
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(p)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


# --------------------------------------------------------------------------
# 日志桥接：把 logging 输出送进 GUI 文本框
# --------------------------------------------------------------------------

class QueueHandler:
    """极简 logging -> queue 桥（避免引入 logging.Handler 的 GUI 依赖问题）。"""

    def __init__(self, q: "queue.Queue[str]"):
        import logging
        self.q = q
        self._h = logging.Handler()
        self._h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                               datefmt="%H:%M:%S"))
        self._h._is_gui_queue = True  # type: ignore[attr-defined]
        self._h.emit = self._emit  # type: ignore[method-assign]
        logging.getLogger("maa_autoboot").addHandler(self._h)

    def _emit(self, record) -> None:
        try:
            self.q.put(self._h.format(record) + "\n")
        except Exception:
            pass


def _attach_queue_handler(q: "queue.Queue[str]") -> None:
    """挂载日志桥（幂等：先清掉旧桥再挂新的）。"""
    import logging
    lg = logging.getLogger("maa_autoboot")
    for h in list(lg.handlers):
        if getattr(h, "_is_gui_queue", False):
            lg.removeHandler(h)
    QueueHandler(q)


def run_gui(cfg: Optional[Config] = None) -> int:
    cfg = cfg or Config()
    setup_logging(None, console=False)  # GUI 模式日志进窗口
    app = App(cfg)
    app.mainloop()
    return 0
