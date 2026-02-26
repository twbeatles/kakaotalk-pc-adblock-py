from __future__ import annotations

import logging
import logging.handlers
import os
from typing import Optional

from .config import LOG_FILE


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("KakaoTalkLayoutAdBlocker")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    level_name = (level or "INFO").upper()
    stream_handler.setLevel(getattr(logging, level_name, logging.INFO))
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


__all__ = ["setup_logging"]
