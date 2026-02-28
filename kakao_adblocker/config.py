from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

VERSION = "11.0.0"
APP_NAME = "KakaoTalk Layout AdBlocker"
APPDATA_DIRNAME = "KakaoTalkAdBlockerLayout"

_LOAD_WARNINGS: List[str] = []
_LOAD_WARNINGS_LOCK = threading.Lock()


def _push_load_warning(message: str) -> None:
    with _LOAD_WARNINGS_LOCK:
        _LOAD_WARNINGS.append(message)


def consume_load_warnings() -> List[str]:
    with _LOAD_WARNINGS_LOCK:
        out = list(_LOAD_WARNINGS)
        _LOAD_WARNINGS.clear()
        return out


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

BROKEN_BACKUP_KEEP_COUNT = 10
BROKEN_BACKUP_MAX_AGE_DAYS = 30
_BROKEN_SUFFIX_RE = re.compile(r"\.broken-(\d{8}-\d{6})$")
_MOJIBAKE_SIGNATURES = ("移댁뭅?ㅽ넚", "愿묎퀬")


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


def _backup_broken_json(path: str, label: str, reason: str) -> None:
    if not os.path.exists(path):
        return
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.broken-{timestamp}"
    try:
        shutil.copy2(path, backup_path)
        _push_load_warning(
            f"{label} 손상 감지: {reason}. 백업 생성: {backup_path}. 기본값으로 동작합니다."
        )
    except Exception as exc:
        _push_load_warning(
            f"{label} 손상 감지: {reason}. 백업 실패({exc.__class__.__name__}). 기본값으로 동작합니다."
        )
    _cleanup_broken_backups(path, label)


def _backup_timestamp(path: Path) -> datetime:
    match = _BROKEN_SUFFIX_RE.search(path.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
        except Exception:
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        return datetime.min


def _cleanup_broken_backups(path: str, label: str) -> None:
    base_path = Path(path)
    parent = base_path.parent
    pattern = f"{base_path.name}.broken-*"
    now = datetime.now()
    max_age = timedelta(days=BROKEN_BACKUP_MAX_AGE_DAYS)

    try:
        backups = list(parent.glob(pattern))
    except Exception as exc:
        _push_load_warning(f"{label} 백업 정리 실패({exc.__class__.__name__}).")
        return

    for backup in backups:
        backup_time = _backup_timestamp(backup)
        if now - backup_time <= max_age:
            continue
        try:
            backup.unlink()
        except Exception as exc:
            _push_load_warning(f"{label} 백업 정리 실패: {backup.name} ({exc.__class__.__name__})")

    keep = sorted(
        [p for p in parent.glob(pattern) if p.exists()],
        key=_backup_timestamp,
        reverse=True,
    )
    for old in keep[BROKEN_BACKUP_KEEP_COUNT:]:
        try:
            old.unlink()
        except Exception as exc:
            _push_load_warning(f"{label} 백업 정리 실패: {old.name} ({exc.__class__.__name__})")


def _is_mojibake_text(value: str) -> bool:
    if not value:
        return False
    if "\ufffd" in value:
        return True
    return any(signature in value for signature in _MOJIBAKE_SIGNATURES)


def _warn_if_rules_text_corrupted(rules: "LayoutRulesV11", source_label: str) -> None:
    corrupted = []
    if any(_is_mojibake_text(token) for token in rules.main_window_titles):
        corrupted.append("main_window_titles")
    if any(_is_mojibake_text(token) for token in rules.aggressive_ad_tokens):
        corrupted.append("aggressive_ad_tokens")
    if corrupted:
        _push_load_warning(
            f"{source_label} 문자열 무결성 경고: {', '.join(corrupted)}에 인코딩 이상 징후가 있습니다."
        )


def _load_json_object(path: str, label: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as exc:
        _backup_broken_json(path, label, f"JSON 파싱 실패({exc.__class__.__name__})")
        return None
    if not isinstance(raw, dict):
        _backup_broken_json(path, label, "최상위 타입이 object(dict)가 아님")
        return None
    return raw


@dataclass
class LayoutSettingsV11:
    enabled: bool = True
    run_on_startup: bool = False
    start_minimized: bool = True
    poll_interval_ms: int = 50
    idle_poll_interval_ms: int = 200
    pid_scan_interval_ms: int = 200
    cache_cleanup_interval_ms: int = 1000
    aggressive_mode: bool = True
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: str = SETTINGS_FILE) -> "LayoutSettingsV11":
        defaults = cls()
        raw = _load_json_object(path, "layout_settings_v11.json")
        if raw is None:
            return defaults
        return cls(
            enabled=_coerce_bool(raw.get("enabled"), defaults.enabled),
            run_on_startup=_coerce_bool(raw.get("run_on_startup"), defaults.run_on_startup),
            start_minimized=_coerce_bool(raw.get("start_minimized"), defaults.start_minimized),
            poll_interval_ms=_coerce_int(raw.get("poll_interval_ms"), defaults.poll_interval_ms, minimum=50, maximum=5000),
            idle_poll_interval_ms=_coerce_int(
                raw.get("idle_poll_interval_ms"),
                defaults.idle_poll_interval_ms,
                minimum=200,
                maximum=5000,
            ),
            pid_scan_interval_ms=_coerce_int(
                raw.get("pid_scan_interval_ms"),
                defaults.pid_scan_interval_ms,
                minimum=100,
                maximum=5000,
            ),
            cache_cleanup_interval_ms=_coerce_int(
                raw.get("cache_cleanup_interval_ms"),
                defaults.cache_cleanup_interval_ms,
                minimum=250,
                maximum=10000,
            ),
            aggressive_mode=_coerce_bool(raw.get("aggressive_mode"), defaults.aggressive_mode),
            log_level=_coerce_str(raw.get("log_level"), defaults.log_level).upper(),
        )

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
    ad_candidate_classes: List[str] = field(default_factory=lambda: ["EVA_Window_Dblclk", "EVA_Window"])
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
        raw = _load_json_object(path, "layout_rules_v11.json")
        if raw is None:
            _warn_if_rules_text_corrupted(defaults, "layout_rules_v11.json")
            return defaults
        main_window_classes = _coerce_str_list(raw.get("main_window_classes"), defaults.main_window_classes)
        raw_ad_candidate_classes = raw.get("ad_candidate_classes")
        if isinstance(raw_ad_candidate_classes, list):
            ad_candidate_classes = _coerce_str_list(raw_ad_candidate_classes, main_window_classes)
        else:
            ad_candidate_classes = list(main_window_classes)

        banner_min_height_px = _coerce_int(raw.get("banner_min_height_px"), defaults.banner_min_height_px, minimum=1)
        banner_max_height_px = _coerce_int(raw.get("banner_max_height_px"), defaults.banner_max_height_px, minimum=1)
        if banner_min_height_px > banner_max_height_px:
            banner_min_height_px, banner_max_height_px = banner_max_height_px, banner_min_height_px
            _push_load_warning(
                "layout_rules_v11.json banner 높이 범위(min/max)가 역전되어 자동 교정했습니다."
            )

        rules = cls(
            main_window_classes=main_window_classes,
            ad_candidate_classes=ad_candidate_classes,
            main_window_titles=_coerce_str_list(raw.get("main_window_titles"), defaults.main_window_titles),
            main_view_prefix=_coerce_str(raw.get("main_view_prefix"), defaults.main_view_prefix),
            lock_view_prefix=_coerce_str(raw.get("lock_view_prefix"), defaults.lock_view_prefix),
            eva_child_class=_coerce_str(raw.get("eva_child_class"), defaults.eva_child_class),
            custom_scroll_prefix=_coerce_str(raw.get("custom_scroll_prefix"), defaults.custom_scroll_prefix),
            chrome_legacy_title=_coerce_str(raw.get("chrome_legacy_title"), defaults.chrome_legacy_title),
            chrome_widget_prefixes=_coerce_str_list(raw.get("chrome_widget_prefixes"), defaults.chrome_widget_prefixes),
            aggressive_ad_tokens=_coerce_str_list(raw.get("aggressive_ad_tokens"), defaults.aggressive_ad_tokens),
            banner_min_height_px=banner_min_height_px,
            banner_max_height_px=banner_max_height_px,
            banner_min_width_ratio=_coerce_float(raw.get("banner_min_width_ratio"), defaults.banner_min_width_ratio, minimum=0.1, maximum=1.0),
            banner_bottom_margin_px=_coerce_int(raw.get("banner_bottom_margin_px"), defaults.banner_bottom_margin_px, minimum=0),
            layout_shadow_padding_px=_coerce_int(raw.get("layout_shadow_padding_px"), defaults.layout_shadow_padding_px, minimum=0),
            main_view_padding_px=_coerce_int(raw.get("main_view_padding_px"), defaults.main_view_padding_px, minimum=0),
            cache_ttl_seconds=_coerce_float(raw.get("cache_ttl_seconds"), defaults.cache_ttl_seconds, minimum=0.1),
            log_rate_limit_seconds=_coerce_float(raw.get("log_rate_limit_seconds"), defaults.log_rate_limit_seconds, minimum=0.1),
        )
        _warn_if_rules_text_corrupted(rules, "layout_rules_v11.json")
        return rules

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
    "consume_load_warnings",
]
