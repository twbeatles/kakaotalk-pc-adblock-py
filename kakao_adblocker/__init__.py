from __future__ import annotations

from importlib import import_module
from typing import Dict, Tuple

_MODULE_EXPORTS = {
    "app": "kakao_adblocker.app",
}

_ATTR_EXPORTS: Dict[str, Tuple[str, str]] = {
    "main": ("kakao_adblocker.app", "main"),
    "VERSION": ("kakao_adblocker.config", "VERSION"),
    "APP_NAME": ("kakao_adblocker.config", "APP_NAME"),
    "APPDATA_DIRNAME": ("kakao_adblocker.config", "APPDATA_DIRNAME"),
    "APPDATA_DIR": ("kakao_adblocker.config", "APPDATA_DIR"),
    "SETTINGS_FILE": ("kakao_adblocker.config", "SETTINGS_FILE"),
    "RULES_FILE": ("kakao_adblocker.config", "RULES_FILE"),
    "LOG_FILE": ("kakao_adblocker.config", "LOG_FILE"),
    "LEGACY_FILES": ("kakao_adblocker.config", "LEGACY_FILES"),
    "LayoutSettingsV11": ("kakao_adblocker.config", "LayoutSettingsV11"),
    "LayoutRulesV11": ("kakao_adblocker.config", "LayoutRulesV11"),
    "resource_base_dir": ("kakao_adblocker.config", "resource_base_dir"),
    "get_app_data_dir": ("kakao_adblocker.config", "get_app_data_dir"),
    "ensure_runtime_files": ("kakao_adblocker.config", "ensure_runtime_files"),
    "consume_load_warnings": ("kakao_adblocker.config", "consume_load_warnings"),
    "LayoutOnlyEngine": ("kakao_adblocker.event_engine", "LayoutOnlyEngine"),
    "EngineState": ("kakao_adblocker.event_engine", "EngineState"),
    "WindowInfo": ("kakao_adblocker.event_engine", "WindowInfo"),
    "LayoutEngine": ("kakao_adblocker.layout_engine", "LayoutEngine"),
    "TrayController": ("kakao_adblocker.ui", "TrayController"),
    "ProcessInspector": ("kakao_adblocker.services", "ProcessInspector"),
    "StartupManager": ("kakao_adblocker.services", "StartupManager"),
    "ShellService": ("kakao_adblocker.services", "ShellService"),
    "ReleaseService": ("kakao_adblocker.services", "ReleaseService"),
    "Win32API": ("kakao_adblocker.win32_api", "Win32API"),
    "SW_HIDE": ("kakao_adblocker.win32_api", "SW_HIDE"),
    "SW_SHOW": ("kakao_adblocker.win32_api", "SW_SHOW"),
    "SWP_NOSIZE": ("kakao_adblocker.win32_api", "SWP_NOSIZE"),
    "SWP_NOMOVE": ("kakao_adblocker.win32_api", "SWP_NOMOVE"),
    "SWP_NOZORDER": ("kakao_adblocker.win32_api", "SWP_NOZORDER"),
    "SWP_NOACTIVATE": ("kakao_adblocker.win32_api", "SWP_NOACTIVATE"),
    "WM_CLOSE": ("kakao_adblocker.win32_api", "WM_CLOSE"),
    "setup_logging": ("kakao_adblocker.logging_setup", "setup_logging"),
}

__all__ = [
    "app",
    "main",
    "VERSION",
    "APP_NAME",
    "APPDATA_DIRNAME",
    "APPDATA_DIR",
    "SETTINGS_FILE",
    "RULES_FILE",
    "LOG_FILE",
    "LEGACY_FILES",
    "LayoutSettingsV11",
    "LayoutRulesV11",
    "LayoutOnlyEngine",
    "EngineState",
    "WindowInfo",
    "LayoutEngine",
    "TrayController",
    "ProcessInspector",
    "StartupManager",
    "ShellService",
    "ReleaseService",
    "Win32API",
    "SW_HIDE",
    "SW_SHOW",
    "SWP_NOSIZE",
    "SWP_NOMOVE",
    "SWP_NOZORDER",
    "SWP_NOACTIVATE",
    "WM_CLOSE",
    "setup_logging",
    "resource_base_dir",
    "get_app_data_dir",
    "ensure_runtime_files",
    "consume_load_warnings",
]


def __getattr__(name: str):
    module_name = _MODULE_EXPORTS.get(name)
    if module_name is not None:
        module = import_module(module_name)
        globals()[name] = module
        return module

    target = _ATTR_EXPORTS.get(name)
    if target is not None:
        source_module_name, source_attr_name = target
        source_module = import_module(source_module_name)
        value = getattr(source_module, source_attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
