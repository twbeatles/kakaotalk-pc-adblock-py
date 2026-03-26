from __future__ import annotations

import os
from pathlib import Path

if "__path__" not in globals():
    __path__ = [str(Path(__file__).resolve().parent)]  # type: ignore[assignment]
if not globals().get("__package__"):
    __package__ = "kakao_adblocker.config"

from .models import LayoutRulesV11, LayoutSettingsV11
from .paths import APP_NAME, APPDATA_DIRNAME, VERSION, RuntimePaths, _build_runtime_paths, _default_appdata_dir, resource_base_dir
from .storage import (
    _atomic_write_text,
    _backup_broken_json,
    _backup_timestamp,
    _cleanup_broken_backups,
    _coerce_bool,
    _coerce_float,
    _coerce_int,
    _coerce_str,
    _coerce_str_list,
    _json_with_trailing_newline,
    _load_json_object,
    _self_heal_broken_json,
    _write_text_if_missing,
)
from .warnings import _is_mojibake_text, _push_load_warning, _warn_if_rules_text_corrupted, consume_load_warnings

_INITIAL_RUNTIME_PATHS = _build_runtime_paths(_default_appdata_dir())

# Compatibility aliases only. Internal runtime code should use get_runtime_paths().
APPDATA_DIR = _INITIAL_RUNTIME_PATHS.appdata_dir
SETTINGS_FILE = _INITIAL_RUNTIME_PATHS.settings_file
RULES_FILE = _INITIAL_RUNTIME_PATHS.rules_file
LOG_FILE = _INITIAL_RUNTIME_PATHS.log_file

LEGACY_FILES = (
    "adblock_settings.json",
    "ad_patterns.json",
    "blocked_domains.txt",
)


def _runtime_path_override(name: str, initial: str, fallback: str) -> str:
    current = str(globals().get(name, initial))
    return current if current != initial else fallback


def get_runtime_paths(create: bool = False) -> RuntimePaths:
    appdata_dir = _runtime_path_override("APPDATA_DIR", _INITIAL_RUNTIME_PATHS.appdata_dir, _default_appdata_dir())
    default_paths = _build_runtime_paths(appdata_dir)
    paths = RuntimePaths(
        appdata_dir=appdata_dir,
        settings_file=_runtime_path_override("SETTINGS_FILE", _INITIAL_RUNTIME_PATHS.settings_file, default_paths.settings_file),
        rules_file=_runtime_path_override("RULES_FILE", _INITIAL_RUNTIME_PATHS.rules_file, default_paths.rules_file),
        log_file=_runtime_path_override("LOG_FILE", _INITIAL_RUNTIME_PATHS.log_file, default_paths.log_file),
    )
    if create:
        Path(paths.appdata_dir).mkdir(parents=True, exist_ok=True)
    return paths


def resolve_app_data_dir(create: bool = False) -> str:
    return get_runtime_paths(create=create).appdata_dir


def get_app_data_dir() -> str:
    return resolve_app_data_dir(create=True)


def _ensure_from_template(dst: str, default_text: str) -> None:
    if os.path.exists(dst):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    src = os.path.join(resource_base_dir(), os.path.basename(dst))
    try:
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = default_text
    except Exception:
        content = default_text
    _write_text_if_missing(dst, _json_with_trailing_newline(content))


def ensure_runtime_files() -> None:
    paths = get_runtime_paths(create=True)
    _ensure_from_template(paths.settings_file, LayoutSettingsV11.default_json())
    _ensure_from_template(paths.rules_file, LayoutRulesV11.default_json())
    if not os.path.exists(paths.log_file):
        _write_text_if_missing(paths.log_file, "")


__all__ = [
    "VERSION",
    "APP_NAME",
    "APPDATA_DIRNAME",
    "APPDATA_DIR",
    "SETTINGS_FILE",
    "RULES_FILE",
    "LOG_FILE",
    "LEGACY_FILES",
    "RuntimePaths",
    "LayoutSettingsV11",
    "LayoutRulesV11",
    "resource_base_dir",
    "resolve_app_data_dir",
    "get_app_data_dir",
    "get_runtime_paths",
    "ensure_runtime_files",
    "consume_load_warnings",
]
