"""日志工具：统一格式、文件 + 控制台双写。

踩坑提醒（来自原项目 §8.2）：MAA / MAAEnd 的日志是 UTF-8（无 BOM），
读取它们的任何代码都必须显式 ``encoding="utf-8"``，否则中文完成标记
永远匹配不到，只能靠超时兜底关机。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s [%(levelname)s] %(message)s"


def setup_logging(log_dir: Path | str | None = None, console: bool = True) -> logging.Logger:
    """初始化根记录器；重复调用安全（先清掉旧 handler）。"""
    logger = logging.getLogger("maa_autoboot")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)

    if log_dir:
        try:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                log_dir / "maa_autoboot.log", maxBytes=2 * 1024 * 1024,
                backupCount=5, encoding="utf-8")
            fh.setFormatter(logging.Formatter(_FMT))
            logger.addHandler(fh)
        except OSError:
            pass  # 写不了文件就只用控制台，绝不因此崩溃

    if console or not logger.handlers:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter(_FMT))
        logger.addHandler(sh)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("maa_autoboot")
