from __future__ import annotations

import logging
import logging.handlers
import os

from .config import LOG_FILE


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _resolve_level(level: str) -> int:
    level_name = (level or "INFO").upper()
    return int(getattr(logging, level_name, logging.INFO))


def _close_handler(handler: logging.Handler) -> None:
    try:
        handler.close()
    except Exception:
        pass


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("KakaoTalkLayoutAdBlocker")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = _build_formatter()

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
    stream_handler.setLevel(_resolve_level(level))
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


def probe_logging_setup() -> tuple[bool, str]:
    handler: logging.Handler | None = None
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(_build_formatter())
        return True, f"logging 초기화 가능 ({LOG_FILE})"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    finally:
        if handler is not None:
            _close_handler(handler)


__all__ = ["setup_logging", "probe_logging_setup", "_build_formatter", "_resolve_level"]
