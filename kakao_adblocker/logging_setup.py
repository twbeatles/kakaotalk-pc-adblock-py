from __future__ import annotations

import logging
import logging.handlers
import os

from .config import get_runtime_paths


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


def _reset_logger_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        try:
            logger.removeHandler(handler)
        except Exception:
            pass
        _close_handler(handler)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("KakaoTalkLayoutAdBlocker")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    _reset_logger_handlers(logger)
    fmt = _build_formatter()
    log_file = get_runtime_paths(create=True).log_file

    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
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
        log_file = get_runtime_paths(create=True).log_file
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(_build_formatter())
        return True, f"logging 초기화 가능 ({log_file})"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    finally:
        if handler is not None:
            _close_handler(handler)


__all__ = ["setup_logging", "probe_logging_setup", "_build_formatter", "_resolve_level", "_reset_logger_handlers"]
