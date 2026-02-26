from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List

VERSION = "11.0.0"
APP_NAME = "KakaoTalk Layout AdBlocker"
APPDATA_DIRNAME = "KakaoTalkAdBlockerLayout"


def resource_base_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(getattr(sys, "_MEIPASS"))
    return str(Path(__file__).resolve().parents[1])


def get_app_data_dir() -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    path = Path(appdata) / APPDATA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


APPDATA_DIR = get_app_data_dir()
SETTINGS_FILE = os.path.join(APPDATA_DIR, "layout_settings_v11.json")
RULES_FILE = os.path.join(APPDATA_DIR, "layout_rules_v11.json")
LOG_FILE = os.path.join(APPDATA_DIR, "layout_adblock.log")

LEGACY_FILES = (
    "adblock_settings.json",
    "ad_patterns.json",
    "blocked_domains.txt",
)


def _coerce_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        out = default
    else:
        out = value
    if minimum is not None:
        out = max(out, minimum)
    if maximum is not None:
        out = min(out, maximum)
    return out


def _coerce_float(value: Any, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        out = float(default)
    else:
        out = float(value)
    if minimum is not None:
        out = max(out, minimum)
    if maximum is not None:
        out = min(out, maximum)
    return out


def _coerce_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _coerce_str_list(value: Any, default: List[str]) -> List[str]:
    if not isinstance(value, list):
        return list(default)
    out = [x for x in value if isinstance(x, str) and x.strip()]
    return out if out else list(default)


@dataclass
class LayoutSettingsV11:
    enabled: bool = True
    run_on_startup: bool = False
    start_minimized: bool = True
    poll_interval_ms: int = 100
    aggressive_mode: bool = True
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: str = SETTINGS_FILE) -> "LayoutSettingsV11":
        defaults = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                return defaults
            return cls(
                enabled=_coerce_bool(raw.get("enabled"), defaults.enabled),
                run_on_startup=_coerce_bool(raw.get("run_on_startup"), defaults.run_on_startup),
                start_minimized=_coerce_bool(raw.get("start_minimized"), defaults.start_minimized),
                poll_interval_ms=_coerce_int(raw.get("poll_interval_ms"), defaults.poll_interval_ms, minimum=50, maximum=5000),
                aggressive_mode=_coerce_bool(raw.get("aggressive_mode"), defaults.aggressive_mode),
                log_level=_coerce_str(raw.get("log_level"), defaults.log_level).upper(),
            )
        except Exception:
            return defaults

    def save(self, path: str = SETTINGS_FILE) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def default_json(cls) -> str:
        return json.dumps(asdict(cls()), indent=2, ensure_ascii=False)


@dataclass
class LayoutRulesV11:
    main_window_classes: List[str] = field(default_factory=lambda: ["EVA_Window_Dblclk", "EVA_Window"])
    main_window_titles: List[str] = field(default_factory=lambda: ["카카오톡", "KakaoTalk"])
    main_view_prefix: str = "OnlineMainView"
    lock_view_prefix: str = "LockModeView"
    eva_child_class: str = "EVA_ChildWindow"
    custom_scroll_prefix: str = "_EVA_"
    chrome_legacy_title: str = "Chrome Legacy Window"
    chrome_widget_prefixes: List[str] = field(default_factory=lambda: ["Chrome_WidgetWin_"])
    aggressive_ad_tokens: List[str] = field(default_factory=lambda: ["Ad", "AdFit", "Advertisement", "광고"])
    banner_min_height_px: int = 40
    banner_max_height_px: int = 260
    banner_min_width_ratio: float = 0.75
    banner_bottom_margin_px: int = 40
    layout_shadow_padding_px: int = 2
    main_view_padding_px: int = 31
    cache_ttl_seconds: float = 8.0
    log_rate_limit_seconds: float = 8.0

    @property
    def aggressive_ad_tokens_lc(self) -> List[str]:
        return [t.lower() for t in self.aggressive_ad_tokens]

    @classmethod
    def load(cls, path: str = RULES_FILE) -> "LayoutRulesV11":
        defaults = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                return defaults
            return cls(
                main_window_classes=_coerce_str_list(raw.get("main_window_classes"), defaults.main_window_classes),
                main_window_titles=_coerce_str_list(raw.get("main_window_titles"), defaults.main_window_titles),
                main_view_prefix=_coerce_str(raw.get("main_view_prefix"), defaults.main_view_prefix),
                lock_view_prefix=_coerce_str(raw.get("lock_view_prefix"), defaults.lock_view_prefix),
                eva_child_class=_coerce_str(raw.get("eva_child_class"), defaults.eva_child_class),
                custom_scroll_prefix=_coerce_str(raw.get("custom_scroll_prefix"), defaults.custom_scroll_prefix),
                chrome_legacy_title=_coerce_str(raw.get("chrome_legacy_title"), defaults.chrome_legacy_title),
                chrome_widget_prefixes=_coerce_str_list(raw.get("chrome_widget_prefixes"), defaults.chrome_widget_prefixes),
                aggressive_ad_tokens=_coerce_str_list(raw.get("aggressive_ad_tokens"), defaults.aggressive_ad_tokens),
                banner_min_height_px=_coerce_int(raw.get("banner_min_height_px"), defaults.banner_min_height_px, minimum=1),
                banner_max_height_px=_coerce_int(raw.get("banner_max_height_px"), defaults.banner_max_height_px, minimum=1),
                banner_min_width_ratio=_coerce_float(raw.get("banner_min_width_ratio"), defaults.banner_min_width_ratio, minimum=0.1, maximum=1.0),
                banner_bottom_margin_px=_coerce_int(raw.get("banner_bottom_margin_px"), defaults.banner_bottom_margin_px, minimum=0),
                layout_shadow_padding_px=_coerce_int(raw.get("layout_shadow_padding_px"), defaults.layout_shadow_padding_px, minimum=0),
                main_view_padding_px=_coerce_int(raw.get("main_view_padding_px"), defaults.main_view_padding_px, minimum=0),
                cache_ttl_seconds=_coerce_float(raw.get("cache_ttl_seconds"), defaults.cache_ttl_seconds, minimum=0.1),
                log_rate_limit_seconds=_coerce_float(raw.get("log_rate_limit_seconds"), defaults.log_rate_limit_seconds, minimum=0.1),
            )
        except Exception:
            return defaults

    def save(self, path: str = RULES_FILE) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def default_json(cls) -> str:
        return json.dumps(asdict(cls()), indent=2, ensure_ascii=False)


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
    with open(dst, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_runtime_files() -> None:
    os.makedirs(APPDATA_DIR, exist_ok=True)
    _ensure_from_template(SETTINGS_FILE, LayoutSettingsV11.default_json())
    _ensure_from_template(RULES_FILE, LayoutRulesV11.default_json())
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "a", encoding="utf-8"):
            pass


__all__ = [
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
    "resource_base_dir",
    "get_app_data_dir",
    "ensure_runtime_files",
]
