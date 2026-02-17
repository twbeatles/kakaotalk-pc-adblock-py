# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v10.0 (Event-Driven Architecture)
==========================================================
- v10.0 Changes:
    - SetWinEventHook for event-driven window detection (CPU 0% idle)
    - Hybrid polling fallback for robustness
    - Pattern-based ad detection from external config
    - Thread-safe event queue system
    - Message pump for Win32 events
"""

import os
import sys
import shutil
import codecs
import ctypes
import ctypes.wintypes
import json
import threading
import time
import heapq
import random
import logging
import logging.handlers
import queue
import platform
import subprocess
import winreg
from datetime import datetime
from typing import Optional, List, Dict, Set, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
from collections import deque

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ═══════════════════════════════════════════════════════════════════════════════
# Third-party libraries
# ═══════════════════════════════════════════════════════════════════════════════
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    pystray = None
    TRAY_AVAILABLE = False

try:
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except ImportError:
    Desktop = None
    PYWINAUTO_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & Configuration
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "10.0.0"
APP_NAME = "KakaoTalk AdBlocker Pro"
APPDATA_DIRNAME = "KakaoTalkAdBlockerPro"

# Package layout: <repo>/kakao_adblocker/legacy.py
# Keep resource compatibility with previous single-file layout (<repo>/).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resource_base_dir() -> str:
    """Directory that contains bundled resources (PyInstaller) or source files (dev)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(getattr(sys, "_MEIPASS"))
    return BASE_DIR

def get_app_data_dir() -> str:
    """
    Persistent per-user data directory.
    Default: %APPDATA%\\KakaoTalkAdBlockerPro
    Fallback: ~\\AppData\\Roaming\\KakaoTalkAdBlockerPro (or home dir if unknown)
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        home = os.path.expanduser("~")
        # Best-effort Windows-style fallback; on non-Windows this is still safe.
        appdata = os.path.join(home, "AppData", "Roaming")
    path = os.path.join(appdata, APPDATA_DIRNAME)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        # Last resort: keep the app functional even if directory creation fails.
        path = BASE_DIR
    return path

APPDATA_DIR = get_app_data_dir()
SETTINGS_FILE = os.path.join(APPDATA_DIR, "adblock_settings.json")
DOMAINS_FILE = os.path.join(APPDATA_DIR, "blocked_domains.txt")
PATTERNS_FILE = os.path.join(APPDATA_DIR, "ad_patterns.json")
LOG_FILE = os.path.join(APPDATA_DIR, "adblock.log")

def migrate_legacy_user_files() -> None:
    """One-time migration from portable folder to AppData (if AppData file is missing)."""
    if APPDATA_DIR == BASE_DIR:
        return
    for name in ("adblock_settings.json", "blocked_domains.txt", "ad_patterns.json"):
        src = os.path.join(BASE_DIR, name)
        dst = os.path.join(APPDATA_DIR, name)
        try:
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
        except Exception:
            pass

def ensure_user_file(path: str, *, copy_from_resource: bool = True, default_text: Optional[str] = None) -> None:
    """
    Ensure a user-editable file exists under AppData.
    If missing: copy from resource dir (same filename) else create using default_text.
    """
    try:
        if os.path.exists(path):
            return
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        if copy_from_resource:
            candidate = os.path.join(resource_base_dir(), os.path.basename(path))
            if os.path.exists(candidate):
                shutil.copy2(candidate, path)
                return
        if default_text is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(default_text)
    except Exception:
        pass


def _make_backup(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = f"{path}.{ts}.bak"
    try:
        shutil.copy2(path, dst)
        return dst
    except Exception:
        return None


def _merge_with_schema(data: Any, schema: Any) -> Tuple[Any, bool]:
    """
    Merge user config with default schema.
    - Keep known keys
    - Fill missing keys from schema
    - Replace type-mismatched values with schema defaults
    Returns (merged, changed).
    """
    if isinstance(schema, dict):
        changed = False
        data_dict = data if isinstance(data, dict) else {}
        if not isinstance(data, dict):
            changed = True
        out: Dict[str, Any] = {}
        for key, default_value in schema.items():
            merged_value, local_changed = _merge_with_schema(data_dict.get(key), default_value)
            out[key] = merged_value
            changed = changed or local_changed or (key not in data_dict)
        return out, changed

    if isinstance(schema, list):
        if not isinstance(data, list):
            return list(schema), True
        return data, False

    if schema is None:
        return data, False

    if isinstance(schema, bool):
        if isinstance(data, bool):
            return data, False
        return schema, True

    if isinstance(schema, int):
        if isinstance(data, int) and not isinstance(data, bool):
            return data, False
        return schema, True

    if isinstance(schema, float):
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            return float(data), False
        return schema, True

    if isinstance(schema, str):
        if isinstance(data, str):
            return data, False
        return schema, True

    return data, False

THEMES = {
    "light": {
        "primary": "#FEE500", "primary_dark": "#FDD835", "bg": "#FFFFFF",
        "text": "#191919", "sub_text": "#757575", "success": "#2E7D32",
        "warning": "#FF6F00", "error": "#D32F2F", "surface": "#F8F9FA", "border": "#E9ECEF",
        "on_primary": "#3A1D1D", "on_primary_sub": "#665500"
    },
    "dark": {
        "primary": "#FEE500", "primary_dark": "#E5CF00", "bg": "#111216",
        "text": "#F2F2F2", "sub_text": "#B0B0B0", "success": "#7ED77F",
        "warning": "#FFB74D", "error": "#EF6F6C", "surface": "#191B20", "border": "#2A2D35",
        "on_primary": "#3A1D1D", "on_primary_sub": "#665500"
    }
}

COLORS = THEMES["light"].copy()

def apply_theme(theme: str, logger: Optional[logging.Logger] = None) -> str:
    theme_key = (theme or "light").lower()
    if theme_key not in THEMES:
        if logger:
            logger.warning(f"Unknown theme '{theme_key}', falling back to light")
        theme_key = "light"
    COLORS.clear()
    COLORS.update(THEMES[theme_key])
    return theme_key

FONTS = {"header": ("맑은 고딕", 14, "bold"), "title": ("맑은 고딕", 11, "bold"),
         "section": ("맑은 고딕", 10, "bold"), "body": ("맑은 고딕", 10), "log": ("Consolas", 9)}

DEFAULT_AD_DOMAINS = [
    "display.ad.daum.net", "analytics.ad.daum.net", "ad.daum.net",
    "alea.adam.ad.daum.net", "adam.ad.daum.net", "wat.ad.daum.net",
    "biz.ad.daum.net", "cs.ad.daum.net", "ad.mad.daum.net",
    "ams.ad.daum.net", "amsv2.daum.net", "ad.smart.kakao.com", "ad.kakao.com",
    "display.ad.kakao.com", "business.kakao.com", "ad.kakaocdn.net", "ad.kakaocdn.com",
    "track.tiara.kakao.com", "stat.tiara.kakao.com", "kakaoad.criteo.com"
] + [f"adimg{i}.kakaocdn.net" for i in range(1, 11)]


# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Constants for Event Hooks
# ═══════════════════════════════════════════════════════════════════════════════
# Event types
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
EVENT_OBJECT_REORDER = 0x8004
EVENT_OBJECT_FOCUS = 0x8005
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
EVENT_OBJECT_NAMECHANGE = 0x800C
EVENT_SYSTEM_FOREGROUND = 0x0003

# Hook flags
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

# Window operations
SW_HIDE = 0
SW_SHOW = 5
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# Message types
WM_QUIT = 0x0012

# WinEvent object IDs
OBJID_WINDOW = 0x00000000


# ═══════════════════════════════════════════════════════════════════════════════
# Logging System
# ═══════════════════════════════════════════════════════════════════════════════
class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        try:
            # If queue is full, remove oldest and add new
            if self.log_queue.full():
                try:
                    self.log_queue.get_nowait()
                except queue.Empty:
                    pass
            self.log_queue.put_nowait(self.format(record))
        except Exception:
            pass  # Fail silently if logging fails

def setup_logging() -> tuple:
    log_queue = queue.Queue(maxsize=200)
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()
    
    fmt = logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)s | %(message)s', datefmt='%H:%M:%S')
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        # Use RotatingFileHandler to prevent unbounded log growth (max 5MB, keep 3 backups)
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    
    qh = QueueHandler(log_queue)
    qh.setLevel(logging.INFO)
    qh.setFormatter(fmt)
    logger.addHandler(qh)
    return logger, log_queue


# ═══════════════════════════════════════════════════════════════════════════════
# Pattern Matching System
# ═══════════════════════════════════════════════════════════════════════════════
class PatternType(Enum):
    TEXT_STARTSWITH = "text_startswith"
    TEXT_CONTAINS = "text_contains"
    TEXT_EQUALS = "text_equals"
    TEXT_REGEX = "text_regex"
    CLASS_EQUALS = "class_equals"
    CLASS_STARTSWITH = "class_startswith"

@dataclass
class AdPattern:
    pattern_type: PatternType
    value: str
    description: str = ""
    compiled_regex: Optional[re.Pattern] = field(default=None, repr=False)
    
    def __post_init__(self):
        if self.pattern_type == PatternType.TEXT_REGEX:
            try:
                self.compiled_regex = re.compile(self.value, re.IGNORECASE)
            except re.error:
                self.compiled_regex = None


@dataclass(frozen=True)
class RuntimeConfig:
    main_window_classes: Tuple[str, ...]
    main_window_titles: Tuple[str, ...]
    event_hook_enabled: bool
    fallback_polling: bool
    scan_interval_active: float
    scan_interval_idle: float
    resize_threshold: int
    min_view_height: int
    event_dedupe_seconds: float
    layout_enabled: bool
    layout_min_height: int
    layout_max_height: int
    layout_min_width_ratio: float
    layout_bottom_margin: int
    layout_class_allowlist: Tuple[str, ...]
    layout_class_blocklist: Tuple[str, ...]
    layout_engine_enabled: bool
    layout_engine_threshold: int
    layout_engine_min_h: int
    layout_engine_max_h: int
    layout_engine_min_width_ratio: float
    layout_engine_bottom_margin: int
    layout_engine_excluded_classes: Tuple[str, ...]
    layout_engine_score_weights: Dict[str, int]
    log_hidden_ads: bool
    log_resizes: bool
    uia_enabled: bool
    uia_scan_interval: float
    uia_max_depth: int
    pid_check_active_seconds: float
    pid_check_idle_seconds: float
    event_coalesce_seconds: float


class PatternConfig:
    DEFAULT_CONFIG = {
        "window_classes": {"main_window": ["EVA_Window"]},
        "title_filters": {"main_window_titles": ["카카오톡", "KakaoTalk"]},
        "ad_patterns": {"hide": [
            {"type": "text_startswith", "value": "BannerAdView"},
            {"type": "text_startswith", "value": "AdView"},
            {"type": "text_startswith", "value": "LockScreenAdView"}
        ]},
        "resize_patterns": {"targets": [{"type": "text_startswith", "value": "OnlineMainView"}]},
        "layout_heuristics": {
            "enabled": True,
            "min_height_px": 80,
            "max_height_px": 170,
            "min_width_ratio": 0.85,
            "bottom_margin_px": 10,
            "class_allowlist": [],
            "class_blocklist": []
        },
        "layout_engine": {
            "enabled": True,
            "banner_score_threshold": 6,
            "candidate_min_height_px": 50,
            "candidate_max_height_px": 250,
            "candidate_min_width_ratio": 0.8,
            "candidate_bottom_margin_px": 25,
            "diagnostic_sample": 5,
            "excluded_classes": [
                "_EVA_CustomScrollCtrl",
                "Edit",
                "Intermediate D3D Window",
                "Chrome_RenderWidgetHostHWND"
            ],
            "score_weights": {
                "is_chrome_widget": 3,
                "title_contains_ad_token": 4,
                "height_in_band": 2,
                "overlap_ratio_high": 2,
                "bottom_aligned_strong": 2,
                "is_content_view": -5,
                "is_eva_child": 1
            }
        },
        "timing": {"scan_interval_active_ms": 500, "scan_interval_idle_ms": 2000,
                   "resize_threshold_px": 5, "min_view_height_px": 100,
                   "event_dedupe_ms": 500},
        "event_hook": {"enabled": True, "fallback_polling": True},
        "logging": {"log_hidden_ads": False, "log_resizes": False},
        "uia": {"enabled": True, "scan_interval_ms": 3000, "max_depth": 8},
        "performance": {
            "pid_check_active_ms": 5000,
            "pid_check_idle_ms": 20000,
            "event_coalesce_ms": 120
        },
    }
    
    def __init__(self, config_path: str, logger: logging.Logger):
        self.config_path = config_path
        self.logger = logger
        self.config = self._load_config()
        self.hide_patterns = self._parse_patterns(self.config.get("ad_patterns", {}).get("hide", []))
        self.resize_patterns = self._parse_patterns(self.config.get("resize_patterns", {}).get("targets", []))
        self.runtime = self._build_runtime()

    def _load_config(self) -> Dict:
        loaded: Dict[str, Any] = {}
        changed = False
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                    loaded, changed = _merge_with_schema(raw, self.DEFAULT_CONFIG)
                    self.logger.info(f"Loaded patterns from {self.config_path}")
                    if changed:
                        _make_backup(self.config_path)
                        with open(self.config_path, "w", encoding="utf-8") as wf:
                            json.dump(loaded, wf, indent=2, ensure_ascii=False)
                        self.logger.info("Pattern config migrated to latest schema")
                    return loaded
        except Exception as e:
            self.logger.error(f"Config load error: {e}")
        self.logger.warning("Using default patterns")
        return json.loads(json.dumps(self.DEFAULT_CONFIG))

    def _parse_patterns(self, pattern_list: List[Dict]) -> List[AdPattern]:
        patterns = []
        for p in pattern_list:
            try:
                value = p.get("value", "").strip() if p.get("value") else ""
                if not value:
                    self.logger.warning(f"Skipping pattern with empty value: {p}")
                    continue
                ptype = PatternType(p.get("type", "text_startswith"))
                patterns.append(AdPattern(ptype, value, p.get("description", "")))
            except ValueError:
                self.logger.warning(f"Unknown pattern type '{p.get('type')}', skipping")
        return patterns

    def _build_runtime(self) -> RuntimeConfig:
        timing = self.config.get("timing", {})
        layout_heur = self.config.get("layout_heuristics", {})
        layout_engine = self.config.get("layout_engine", {})
        logging_cfg = self.config.get("logging", {})
        perf_cfg = self.config.get("performance", {})
        event_hook = self.config.get("event_hook", {})
        uia_cfg = self.config.get("uia", {})

        weights = layout_engine.get("score_weights", {})
        if not isinstance(weights, dict):
            weights = {}
        safe_weights = {str(k): int(v) for k, v in weights.items()}

        return RuntimeConfig(
            main_window_classes=tuple(self.config.get("window_classes", {}).get("main_window", ["EVA_Window"])),
            main_window_titles=tuple(self.config.get("title_filters", {}).get("main_window_titles", ["카카오톡", "KakaoTalk"])),
            event_hook_enabled=bool(event_hook.get("enabled", True)),
            fallback_polling=bool(event_hook.get("fallback_polling", True)),
            scan_interval_active=float(timing.get("scan_interval_active_ms", 1500)) / 1000.0,
            scan_interval_idle=float(timing.get("scan_interval_idle_ms", 3000)) / 1000.0,
            resize_threshold=int(timing.get("resize_threshold_px", 5)),
            min_view_height=int(timing.get("min_view_height_px", 100)),
            event_dedupe_seconds=float(timing.get("event_dedupe_ms", 500)) / 1000.0,
            layout_enabled=bool(layout_heur.get("enabled", True)),
            layout_min_height=int(layout_heur.get("min_height_px", 80)),
            layout_max_height=int(layout_heur.get("max_height_px", 170)),
            layout_min_width_ratio=float(layout_heur.get("min_width_ratio", 0.85)),
            layout_bottom_margin=int(layout_heur.get("bottom_margin_px", 10)),
            layout_class_allowlist=tuple(layout_heur.get("class_allowlist", [])),
            layout_class_blocklist=tuple(layout_heur.get("class_blocklist", [])),
            layout_engine_enabled=bool(layout_engine.get("enabled", True)),
            layout_engine_threshold=int(layout_engine.get("banner_score_threshold", 6)),
            layout_engine_min_h=int(layout_engine.get("candidate_min_height_px", 50)),
            layout_engine_max_h=int(layout_engine.get("candidate_max_height_px", 250)),
            layout_engine_min_width_ratio=float(layout_engine.get("candidate_min_width_ratio", 0.8)),
            layout_engine_bottom_margin=int(layout_engine.get("candidate_bottom_margin_px", 25)),
            layout_engine_excluded_classes=tuple(layout_engine.get("excluded_classes", [])),
            layout_engine_score_weights=safe_weights,
            log_hidden_ads=bool(logging_cfg.get("log_hidden_ads", False)),
            log_resizes=bool(logging_cfg.get("log_resizes", False)),
            uia_enabled=bool(uia_cfg.get("enabled", True)),
            uia_scan_interval=float(uia_cfg.get("scan_interval_ms", 3000)) / 1000.0,
            uia_max_depth=int(uia_cfg.get("max_depth", 8)),
            pid_check_active_seconds=float(perf_cfg.get("pid_check_active_ms", 5000)) / 1000.0,
            pid_check_idle_seconds=float(perf_cfg.get("pid_check_idle_ms", 20000)) / 1000.0,
            event_coalesce_seconds=float(perf_cfg.get("event_coalesce_ms", 120)) / 1000.0,
        )

    @property
    def main_window_classes(self) -> List[str]:
        return list(self.runtime.main_window_classes)
    
    @property
    def main_window_titles(self) -> List[str]:
        return list(self.runtime.main_window_titles)
    
    @property
    def event_hook_enabled(self) -> bool:
        return self.runtime.event_hook_enabled
    
    @property
    def fallback_polling(self) -> bool:
        return self.runtime.fallback_polling
    
    @property
    def scan_interval_active(self) -> float:
        return self.runtime.scan_interval_active
    
    @property
    def scan_interval_idle(self) -> float:
        return self.runtime.scan_interval_idle
    
    @property
    def resize_threshold(self) -> int:
        return self.runtime.resize_threshold
    
    @property
    def min_view_height(self) -> int:
        return self.runtime.min_view_height

    @property
    def event_dedupe_seconds(self) -> float:
        return self.runtime.event_dedupe_seconds

    @property
    def layout_enabled(self) -> bool:
        return self.runtime.layout_enabled

    @property
    def layout_min_height(self) -> int:
        return self.runtime.layout_min_height

    @property
    def layout_max_height(self) -> int:
        return self.runtime.layout_max_height

    @property
    def layout_min_width_ratio(self) -> float:
        return self.runtime.layout_min_width_ratio

    @property
    def layout_bottom_margin(self) -> int:
        return self.runtime.layout_bottom_margin

    @property
    def layout_class_allowlist(self) -> List[str]:
        return list(self.runtime.layout_class_allowlist)

    @property
    def layout_class_blocklist(self) -> List[str]:
        return list(self.runtime.layout_class_blocklist)

    @property
    def layout_engine_enabled(self) -> bool:
        return self.runtime.layout_engine_enabled

    @property
    def layout_engine_threshold(self) -> int:
        return self.runtime.layout_engine_threshold

    @property
    def layout_engine_min_h(self) -> int:
        return self.runtime.layout_engine_min_h

    @property
    def layout_engine_max_h(self) -> int:
        return self.runtime.layout_engine_max_h

    @property
    def layout_engine_min_width_ratio(self) -> float:
        return self.runtime.layout_engine_min_width_ratio

    @property
    def layout_engine_bottom_margin(self) -> int:
        return self.runtime.layout_engine_bottom_margin

    @property
    def layout_engine_excluded_classes(self) -> List[str]:
        return list(self.runtime.layout_engine_excluded_classes)

    @property
    def layout_engine_score_weights(self) -> Dict[str, int]:
        return dict(self.runtime.layout_engine_score_weights)
    
    @property
    def log_hidden_ads(self) -> bool:
        return self.runtime.log_hidden_ads

    @property
    def log_resizes(self) -> bool:
        return self.runtime.log_resizes

    @property
    def uia_enabled(self) -> bool:
        return self.runtime.uia_enabled

    @property
    def uia_scan_interval(self) -> float:
        return self.runtime.uia_scan_interval

    @property
    def uia_max_depth(self) -> int:
        return self.runtime.uia_max_depth

    @property
    def pid_check_active_seconds(self) -> float:
        return self.runtime.pid_check_active_seconds

    @property
    def pid_check_idle_seconds(self) -> float:
        return self.runtime.pid_check_idle_seconds

    @property
    def event_coalesce_seconds(self) -> float:
        return self.runtime.event_coalesce_seconds


@dataclass(frozen=True)
class CompiledPatternSet:
    text_startswith: Tuple[str, ...]
    text_contains: Tuple[str, ...]
    text_equals: Set[str]
    text_regex: Tuple[re.Pattern, ...]
    class_equals: Set[str]
    class_startswith: Tuple[str, ...]

class PatternMatcher:
    def __init__(self, config: PatternConfig):
        self.config = config
        self._hide_compiled = self._compile_patterns(config.hide_patterns)
        self._resize_compiled = self._compile_patterns(config.resize_patterns)
    
    def is_ad_window(self, window_text: str, window_class: str) -> bool:
        return self._matches_compiled(window_text or "", window_class or "", self._hide_compiled)
    
    def is_resize_target(self, window_text: str, window_class: str) -> bool:
        return self._matches_compiled(window_text or "", window_class or "", self._resize_compiled)
    
    def is_main_window(self, window_class: str, window_title: str) -> bool:
        """Check if this is a main KakaoTalk window with title (for resize targets)."""
        cls_ok = (window_class in self.config.main_window_classes) or window_class.startswith("EVA_Window")
        return cls_ok and any(t in (window_title or "") for t in self.config.main_window_titles)
    
    def is_kakao_window(self, window_class: str) -> bool:
        """Check if this is any KakaoTalk window (including ad popups without title)."""
        return (window_class in self.config.main_window_classes) or window_class.startswith("EVA_Window")

    @staticmethod
    def _compile_patterns(patterns: List[AdPattern]) -> CompiledPatternSet:
        text_startswith: List[str] = []
        text_contains: List[str] = []
        text_regex: List[re.Pattern] = []
        class_startswith: List[str] = []
        text_equals: Set[str] = set()
        class_equals: Set[str] = set()
        for p in patterns:
            if p.pattern_type == PatternType.TEXT_STARTSWITH:
                text_startswith.append(p.value)
            elif p.pattern_type == PatternType.TEXT_CONTAINS:
                text_contains.append(p.value)
            elif p.pattern_type == PatternType.TEXT_EQUALS:
                text_equals.add(p.value)
            elif p.pattern_type == PatternType.TEXT_REGEX and p.compiled_regex:
                text_regex.append(p.compiled_regex)
            elif p.pattern_type == PatternType.CLASS_EQUALS:
                class_equals.add(p.value)
            elif p.pattern_type == PatternType.CLASS_STARTSWITH:
                class_startswith.append(p.value)
        return CompiledPatternSet(
            text_startswith=tuple(text_startswith),
            text_contains=tuple(text_contains),
            text_equals=text_equals,
            text_regex=tuple(text_regex),
            class_equals=class_equals,
            class_startswith=tuple(class_startswith),
        )

    @staticmethod
    def _matches_compiled(text: str, cls: str, compiled: CompiledPatternSet) -> bool:
        if text in compiled.text_equals:
            return True
        if cls in compiled.class_equals:
            return True
        for v in compiled.text_startswith:
            if text.startswith(v):
                return True
        for v in compiled.class_startswith:
            if cls.startswith(v):
                return True
        for v in compiled.text_contains:
            if v in text:
                return True
        for rgx in compiled.text_regex:
            if rgx.search(text):
                return True
        return False
    
    def _matches_any(self, text: str, cls: str, patterns: List[AdPattern]) -> bool:
        for p in patterns:
            if self._matches_pattern(text, cls, p):
                return True
        return False
    
    def _matches_pattern(self, text: str, cls: str, pattern: AdPattern) -> bool:
        match pattern.pattern_type:
            case PatternType.TEXT_STARTSWITH:
                return text.startswith(pattern.value)
            case PatternType.TEXT_CONTAINS:
                return pattern.value in text
            case PatternType.TEXT_EQUALS:
                return text == pattern.value
            case PatternType.TEXT_REGEX:
                return bool(pattern.compiled_regex.search(text)) if pattern.compiled_regex else False
            case PatternType.CLASS_EQUALS:
                return cls == pattern.value
            case PatternType.CLASS_STARTSWITH:
                return cls.startswith(pattern.value)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Wrapper
# ═══════════════════════════════════════════════════════════════════════════════
class User32:
    lib = ctypes.windll.user32 if platform.system() == "Windows" else None
    _cache_ttl = 0.1
    _cache: Dict[Tuple[str, int], Tuple[float, Any]] = {}
    _cache_lock = threading.Lock()

    @classmethod
    def _get_cached(cls, key: str, hwnd: int, loader: Callable[[], Any]) -> Any:
        now = time.time()
        cache_key = (key, int(hwnd))
        with cls._cache_lock:
            found = cls._cache.get(cache_key)
            if found and (now - found[0]) <= cls._cache_ttl:
                return found[1]
        value = loader()
        with cls._cache_lock:
            cls._cache[cache_key] = (now, value)
            # Compact opportunistically.
            if len(cls._cache) > 4096:
                cutoff = now - (cls._cache_ttl * 3)
                cls._cache = {k: v for k, v in cls._cache.items() if v[0] >= cutoff}
        return value

    @classmethod
    def clear_cache(cls) -> None:
        with cls._cache_lock:
            cls._cache.clear()

    @staticmethod
    def get_pid(hwnd: int) -> int:
        if not User32.lib:
            return 0
        def _load() -> int:
            pid = ctypes.c_ulong()
            User32.lib.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return int(pid.value)
        return int(User32._get_cached("pid", hwnd, _load))

    @staticmethod
    def get_class(hwnd: int) -> str:
        if not User32.lib:
            return ""
        def _load() -> str:
            buf = ctypes.create_unicode_buffer(256)
            User32.lib.GetClassNameW(hwnd, buf, 256)
            return buf.value
        return str(User32._get_cached("class", hwnd, _load))

    @staticmethod
    def get_text(hwnd: int) -> str:
        if not User32.lib:
            return ""
        def _load() -> str:
            try:
                length = int(User32.lib.GetWindowTextLengthW(hwnd))
            except Exception:
                length = 0
            if length <= 0:
                buf = ctypes.create_unicode_buffer(512)
                try:
                    User32.lib.GetWindowTextW(hwnd, buf, 512)
                except Exception:
                    return ""
                return buf.value
            buf = ctypes.create_unicode_buffer(length + 1)
            try:
                User32.lib.GetWindowTextW(hwnd, buf, length + 1)
            except Exception:
                return ""
            return buf.value
        return str(User32._get_cached("text", hwnd, _load))

    @staticmethod
    def is_visible(hwnd: int) -> bool:
        if not User32.lib:
            return False
        return bool(User32._get_cached("visible", hwnd, lambda: bool(User32.lib.IsWindowVisible(hwnd))))

    @staticmethod
    def is_window(hwnd: int) -> bool:
        return bool(User32.lib.IsWindow(hwnd)) if User32.lib else False

    @staticmethod
    def get_parent(hwnd: int) -> int:
        if not User32.lib:
            return 0
        return int(User32._get_cached("parent", hwnd, lambda: int(User32.lib.GetParent(hwnd))))

    @staticmethod
    def show_window(hwnd: int, cmd: int) -> bool:
        return bool(User32.lib.ShowWindow(hwnd, cmd)) if User32.lib else False

    @staticmethod
    def set_window_pos(hwnd: int, x: int, y: int, w: int, h: int, flags: int) -> bool:
        return bool(User32.lib.SetWindowPos(hwnd, 0, x, y, w, h, flags)) if User32.lib else False

    @staticmethod
    def get_client_rect(hwnd: int) -> Optional[ctypes.wintypes.RECT]:
        if not User32.lib:
            return None
        rect = ctypes.wintypes.RECT()
        return rect if User32.lib.GetClientRect(hwnd, ctypes.byref(rect)) else None

    @staticmethod
    def get_window_rect(hwnd: int) -> Optional[ctypes.wintypes.RECT]:
        if not User32.lib:
            return None

        def _load() -> Optional[Tuple[int, int, int, int]]:
            rect = ctypes.wintypes.RECT()
            if not User32.lib.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

        rt = User32._get_cached("rect", hwnd, _load)
        if not rt:
            return None
        rect = ctypes.wintypes.RECT()
        rect.left, rect.top, rect.right, rect.bottom = rt
        return rect

    @staticmethod
    def screen_to_client(hwnd: int, x: int, y: int) -> tuple:
        if not User32.lib:
            return (0, 0)
        pt = ctypes.wintypes.POINT(x, y)
        User32.lib.ScreenToClient(hwnd, ctypes.byref(pt))
        return (pt.x, pt.y)


# ═══════════════════════════════════════════════════════════════════════════════
# pywinauto UIA Fallback Scanner
# ═══════════════════════════════════════════════════════════════════════════════
class UIAAdBlocker:
    def __init__(self, logger: logging.Logger, matcher: PatternMatcher, config: PatternConfig):
        self.logger = logger.getChild("UIA")
        self.matcher = matcher
        self.config = config
        self._desktop = None
        self._last_error = 0.0
        self._error_backoff = 5.0

    def _get_desktop(self):
        if not self._desktop:
            self._desktop = Desktop(backend="uia")
        return self._desktop

    def _iter_elements(self, window):
        max_depth = max(self.config.uia_max_depth, 1)
        try:
            return [window.element_info] + window.element_info.descendants(depth=max_depth)
        except TypeError:
            return [window.element_info] + window.element_info.descendants()
        except Exception:
            return [window.element_info]

    def _resolve_handle(self, element) -> int:
        current = element
        for _ in range(6):
            hwnd = getattr(current, "handle", 0) or 0
            if hwnd and User32.is_window(hwnd):
                return hwnd
            current = getattr(current, "parent", None)
            if not current:
                break
        return 0

    def _get_root_handle(self, hwnd: int) -> int:
        current = hwnd
        for _ in range(16):
            parent = User32.get_parent(current)
            if not parent or not User32.is_window(parent):
                return current
            current = parent
        return current

    def _should_skip(self, hwnd: int) -> bool:
        if not hwnd or not User32.is_window(hwnd):
            return True
        cls = User32.get_class(hwnd)
        if self.matcher.is_kakao_window(cls) and User32.get_parent(hwnd) == 0:
            return True
        return False

    def scan(self, kakao_pid: Optional[int]) -> tuple[int, Set[int]]:
        if not PYWINAUTO_AVAILABLE:
            return 0, set()
        if not kakao_pid:
            return 0, set()

        now = time.time()
        if now - self._last_error < self._error_backoff:
            return 0, set()

        try:
            desktop = self._get_desktop()
            windows = desktop.windows()
        except Exception as e:
            self._last_error = time.time()
            self.logger.debug(f"UIA desktop error: {e}")
            return 0, set()

        hidden = 0
        roots: Set[int] = set()
        for win in windows:
            try:
                if win.element_info.process_id != kakao_pid:
                    continue
            except Exception:
                continue

            for el in self._iter_elements(win):
                try:
                    text = (getattr(el, "name", "") or "").strip()
                    cls = getattr(el, "class_name", "") or ""
                    if not text and not cls:
                        continue
                    if not self.matcher.is_ad_window(text, cls):
                        continue

                    target = self._resolve_handle(el)
                    if not target or self._should_skip(target):
                        continue

                    if User32.show_window(target, SW_HIDE):
                        hidden += 1
                        root = self._get_root_handle(target)
                        if root:
                            roots.add(root)
                except Exception:
                    continue

        return hidden, roots


# ═══════════════════════════════════════════════════════════════════════════════
# Event-Driven Ad Blocker Engine (NEW in v10.0)
# ═══════════════════════════════════════════════════════════════════════════════
# Define WINEVENTPROC callback type
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,  # return type
    ctypes.wintypes.HANDLE,   # hWinEventHook
    ctypes.wintypes.DWORD,    # event
    ctypes.wintypes.HWND,     # hwnd
    ctypes.wintypes.LONG,     # idObject
    ctypes.wintypes.LONG,     # idChild
    ctypes.wintypes.DWORD,    # dwEventThread
    ctypes.wintypes.DWORD     # dwmsEventTime
)

# Define WNDENUMPROC callback type for EnumChildWindows
WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,     # return type
    ctypes.wintypes.HWND,     # hwnd
    ctypes.wintypes.LPARAM    # lParam
)

class WindowEvent:
    """Represents a window event to be processed."""
    def __init__(self, hwnd: int, event_type: int, timestamp: float = None):
        self.hwnd = hwnd
        self.event_type = event_type
        self.timestamp = timestamp or time.time()

@dataclass
class WindowInfo:
    hwnd: int
    cls: str
    text: str
    rect: Optional[ctypes.wintypes.RECT]
    visible: bool


# ═══════════════════════════════════════════════════════════════════════════════
# Window Graph + Layout Engine (v10.x redesign)
# ═══════════════════════════════════════════════════════════════════════════════
def _rect_to_tuple(rect: Any) -> Optional[Tuple[int, int, int, int]]:
    if rect is None:
        return None
    if isinstance(rect, tuple) and len(rect) == 4:
        return tuple(int(x) for x in rect)  # type: ignore[return-value]
    try:
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception:
        return None


def _tuple_to_rect(rt: Optional[Tuple[int, int, int, int]]) -> Optional[ctypes.wintypes.RECT]:
    if not rt:
        return None
    try:
        rect = ctypes.wintypes.RECT()
        rect.left = int(rt[0])
        rect.top = int(rt[1])
        rect.right = int(rt[2])
        rect.bottom = int(rt[3])
        return rect
    except Exception:
        return None

def _rect_w(rt: Tuple[int, int, int, int]) -> int:
    return max(0, int(rt[2]) - int(rt[0]))

def _rect_h(rt: Tuple[int, int, int, int]) -> int:
    return max(0, int(rt[3]) - int(rt[1]))

def _rect_intersect_w(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> int:
    left = max(a[0], b[0])
    right = min(a[2], b[2])
    return max(0, right - left)


@dataclass
class WindowNode:
    hwnd: int
    pid: int
    cls: str
    title: str
    rect: Optional[Tuple[int, int, int, int]]
    visible: bool
    parent_hwnd: int
    children: Set[int] = field(default_factory=set)
    last_seen_ts: float = 0.0


class WindowGraph:
    def __init__(self, logger: logging.Logger):
        self.logger = logger.getChild("WindowGraph")
        self.nodes: Dict[int, WindowNode] = {}

    def update(self, hwnd: int, parent_hwnd: int = 0) -> Optional[WindowNode]:
        if not hwnd or not User32.is_window(hwnd):
            return None
        try:
            pid = User32.get_pid(hwnd)
            cls = User32.get_class(hwnd)
            title = User32.get_text(hwnd)
            rect = _rect_to_tuple(User32.get_window_rect(hwnd))
            visible = User32.is_visible(hwnd)
            now = time.time()
        except Exception:
            return None

        node = self.nodes.get(hwnd)
        if not node:
            node = WindowNode(
                hwnd=hwnd, pid=pid, cls=cls, title=title, rect=rect,
                visible=visible, parent_hwnd=parent_hwnd, last_seen_ts=now
            )
            self.nodes[hwnd] = node
        else:
            node.pid = pid
            node.cls = cls
            node.title = title
            node.rect = rect
            node.visible = visible
            node.parent_hwnd = parent_hwnd
            node.last_seen_ts = now
        return node

    def snapshot_root(self, root_hwnd: int, max_depth: int = 8) -> Dict[int, WindowNode]:
        """
        Build a bounded subtree snapshot rooted at root_hwnd and store it in nodes cache.
        Returns a dict of hwnd->WindowNode for this snapshot.
        """
        out: Dict[int, WindowNode] = {}
        if not root_hwnd or not User32.is_window(root_hwnd):
            return out

        max_depth = max(int(max_depth), 1)
        bfs_queue: deque[Tuple[int, int]] = deque([(root_hwnd, 0)])
        visited: Set[int] = set()

        root = self.update(root_hwnd, 0)
        if not root:
            return out
        root.children.clear()
        out[root_hwnd] = root

        while bfs_queue:
            parent, depth = bfs_queue.popleft()
            if parent in visited:
                continue
            visited.add(parent)
            if depth >= max_depth:
                continue

            children_hwnds: List[int] = []

            def cb(ch, _):
                try:
                    if ch and User32.is_window(ch):
                        children_hwnds.append(int(ch))
                except Exception:
                    pass
                return True

            try:
                self._enum_child_windows(parent, cb)
            except Exception:
                continue

            pnode = out.get(parent) or self.update(parent, User32.get_parent(parent) or 0)
            if not pnode:
                continue
            pnode.children.clear()

            for ch in children_hwnds:
                cnode = self.update(ch, parent)
                if not cnode:
                    continue
                out[ch] = cnode
                pnode.children.add(ch)
                bfs_queue.append((ch, depth + 1))

        return out

    def _enum_child_windows(self, parent_hwnd: int, py_callback) -> None:
        # Wrap python callback with WNDENUMPROC (must keep reference alive during call)
        cb = WNDENUMPROC(py_callback)
        ctypes.windll.user32.EnumChildWindows(parent_hwnd, cb, 0)

    def to_jsonable(self, snapshot: Dict[int, WindowNode], root_hwnd: int) -> Dict[str, Any]:
        nodes_out = []
        for hwnd, n in snapshot.items():
            rect = n.rect
            nodes_out.append({
                "hwnd": int(hwnd),
                "pid": int(n.pid),
                "cls": n.cls,
                "title": n.title,
                "rect": list(rect) if rect else None,
                "visible": bool(n.visible),
                "parent_hwnd": int(n.parent_hwnd or 0),
                "children": [int(c) for c in sorted(n.children)],
            })
        return {"root_hwnd": int(root_hwnd), "nodes": nodes_out}


class LayoutEngine:
    AD_TOKENS = ("adfit", "advertisement", "adbanner")

    def __init__(self, logger: logging.Logger, matcher: PatternMatcher, config: PatternConfig):
        self.logger = logger.getChild("LayoutEngine")
        self.matcher = matcher
        self.config = config
        self._last_obs_log: Dict[int, float] = {}

    @staticmethod
    def score_candidate(
        cls: str,
        title: str,
        rect: Tuple[int, int, int, int],
        root_rect: Tuple[int, int, int, int],
        *,
        is_content_view: bool,
        bottom_margin_px: int,
        weights: Dict[str, int],
    ) -> int:
        w = _rect_w(rect)
        h = _rect_h(rect)
        root_w = _rect_w(root_rect) or 1

        overlap = _rect_intersect_w(rect, root_rect)
        overlap_ratio = overlap / float(root_w)

        cls_l = (cls or "").lower()
        title_l = (title or "").lower()

        def wt(k: str, default: int) -> int:
            try:
                return int(weights.get(k, default))
            except Exception:
                return default

        score = 0
        is_chrome_widget = cls.startswith("Chrome_WidgetWin") or cls.startswith("Chrome_")
        if is_chrome_widget:
            score += wt("is_chrome_widget", 3)

        if any(tok in title_l for tok in LayoutEngine.AD_TOKENS):
            score += wt("title_contains_ad_token", 4)

        if 80 <= h <= 170:
            score += wt("height_in_band", 2)

        if overlap_ratio >= 0.9:
            score += wt("overlap_ratio_high", 2)

        if abs(rect[3] - root_rect[3]) <= max(min(int(bottom_margin_px), 10), 1):
            score += wt("bottom_aligned_strong", 2)

        if cls.startswith("EVA_ChildWindow"):
            score += wt("is_eva_child", 1)

        if is_content_view:
            score += wt("is_content_view", -5)

        return int(score)

    def detect_banners(
        self,
        snapshot: Dict[int, WindowNode],
        root_hwnd: int,
    ) -> Tuple[List[Tuple[int, str, int]], List[Tuple[int, str, int]]]:
        """
        Returns (to_hide, observed) lists of (hwnd, label, score).
        """
        root = snapshot.get(root_hwnd)
        if not root or not root.rect:
            return [], []
        root_rect = root.rect
        root_w = _rect_w(root_rect)
        if root_w <= 0:
            return [], []

        min_h = max(self.config.layout_engine_min_h, 1)
        max_h = max(self.config.layout_engine_max_h, min_h)
        min_w_ratio = max(min(self.config.layout_engine_min_width_ratio, 1.0), 0.1)
        bottom_margin = max(self.config.layout_engine_bottom_margin, 0)
        threshold = int(self.config.layout_engine_threshold)
        weights = self.config.layout_engine_score_weights or PatternConfig.DEFAULT_CONFIG["layout_engine"]["score_weights"]

        to_hide: List[Tuple[int, str, int]] = []
        observed: List[Tuple[int, str, int]] = []

        for hwnd, n in snapshot.items():
            if hwnd == root_hwnd:
                continue
            if not n.rect:
                continue
            w = _rect_w(n.rect)
            h = _rect_h(n.rect)
            if w <= 0 or h <= 0:
                continue
            if h < min_h or h > max_h:
                continue
            if w < root_w * min_w_ratio:
                continue
            if abs(n.rect[3] - root_rect[3]) > bottom_margin:
                continue

            is_content = self.matcher.is_resize_target(n.title, n.cls)
            score = self.score_candidate(
                n.cls, n.title, n.rect, root_rect,
                is_content_view=is_content,
                bottom_margin_px=bottom_margin,
                weights=weights,
            )
            label = n.title or f"[{n.cls}]"
            if score >= threshold:
                to_hide.append((hwnd, label, score))
            elif score >= (threshold - 2):
                observed.append((hwnd, label, score))

        # Rate-limited observation logging (helps tuning without spamming).
        now = time.time()
        last = self._last_obs_log.get(root_hwnd, 0.0)
        if observed and now - last >= 10.0:
            self._last_obs_log[root_hwnd] = now
            try:
                sample = observed[:5]
                for h, label, score in sample:
                    self.logger.debug(f"Observed banner candidate: score={score} hwnd={h} label={label[:60]}")
            except Exception:
                pass

        return to_hide, observed


class ResizeScheduler:
    """Single-worker delayed scheduler for resize retries."""

    def __init__(self, callback: Callable[[int], None], logger: logging.Logger):
        self._callback = callback
        self._logger = logger
        self._cv = threading.Condition()
        self._heap: List[Tuple[float, int, int, Tuple[float, ...], int]] = []
        self._pending: Set[int] = set()
        self._seq = 0
        self._active = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._cv:
            if self._active:
                return
            self._active = True
            self._thread = threading.Thread(target=self._run, daemon=True, name="ResizeScheduler")
            self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._active = False
            self._heap.clear()
            self._pending.clear()
            self._cv.notify_all()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
        self._thread = None

    def schedule(self, hwnd: int, delays: Tuple[float, ...] = (0.4, 0.8, 1.2, 1.8)) -> None:
        if not hwnd:
            return
        with self._cv:
            if not self._active:
                return
            if hwnd in self._pending:
                return
            self._pending.add(hwnd)
            self._seq += 1
            first = max(float(delays[0]), 0.05) if delays else 0.4
            heapq.heappush(self._heap, (time.time() + first, self._seq, hwnd, tuple(delays), 1))
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                while self._active and not self._heap:
                    self._cv.wait(timeout=0.5)
                if not self._active:
                    return

                run_at, _seq, hwnd, delays, stage = self._heap[0]
                now = time.time()
                wait_sec = run_at - now
                if wait_sec > 0:
                    self._cv.wait(timeout=min(wait_sec, 0.5))
                    continue
                heapq.heappop(self._heap)

            try:
                self._callback(hwnd)
            except Exception as e:
                self._logger.debug(f"ResizeScheduler callback error: {e}")

            with self._cv:
                if not self._active:
                    return
                if stage < len(delays):
                    self._seq += 1
                    gap = max(float(delays[stage]), 0.05)
                    heapq.heappush(self._heap, (time.time() + gap, self._seq, hwnd, delays, stage + 1))
                    self._cv.notify()
                else:
                    self._pending.discard(hwnd)


class EventDrivenAdBlocker:
    """
    Event-driven ad blocker using SetWinEventHook.
    
    This approach uses Windows accessibility hooks to receive notifications
    when windows are created, shown, or receive focus - eliminating the need
    for constant polling and reducing CPU usage to near-zero when idle.
    """
    
    def __init__(self, logger: logging.Logger, pattern_config: PatternConfig):
        self.logger = logger.getChild("EventEngine")
        self.config = pattern_config
        self.matcher = PatternMatcher(pattern_config)
        self.user32 = ctypes.windll.user32 if platform.system() == "Windows" else None

        # Redesign components (graph + score-based banner detection)
        self._graph = WindowGraph(self.logger)
        self._layout_engine = LayoutEngine(self.logger, self.matcher, self.config)
        
        # State management
        self.active = False
        self.kakao_pid: Optional[int] = None
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self._hidden_hwnds: Set[int] = set()
        self._processed_events: Dict[int, float] = {}
        self._resize_scheduler = ResizeScheduler(self._do_resize_children, self.logger.getChild("ResizeScheduler"))
        self._uia = UIAAdBlocker(self.logger, self.matcher, self.config) if PYWINAUTO_AVAILABLE else None
        self._last_uia_scan: float = 0.0
        
        # Event queue for async processing (coalesced by hwnd)
        self._event_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._queued_events: Dict[int, int] = {}
        self._queue_lock = threading.Lock()
        
        # Hook handles
        self._hooks: List[int] = []
        self._hook_callback = None  # Keep reference to prevent GC
        
        # Threads
        self._event_thread: Optional[threading.Thread] = None
        self._message_thread: Optional[threading.Thread] = None
        self._fallback_thread: Optional[threading.Thread] = None
        self._message_thread_id: Optional[int] = None  # For PostThreadMessage
        
        # PID update cooldown
        self._last_pid_check: float = 0.0
        self._pid_hint: bool = False
        self._previous_kakao_pid: Optional[int] = None  # For detecting PID changes
        
        # Statistics
        self._stats = {
            "events_received": 0,
            "events_coalesced": 0,
            "events_dropped": 0,
            "ads_hidden": 0,
            "resizes": 0,
            "errors": 0,
        }
        self._last_hook_error_log: float = 0.0

        # Root rescan throttling for noisy events (location/name/reorder).
        self._root_scan_last: Dict[int, float] = {}
        self._root_scan_throttle_sec: float = 0.2
    
    def start(self):
        """Start the event-driven ad blocker."""
        if not self.user32:
            return

        with self._lifecycle_lock:
            if self.active:
                return

            if not self.config.event_hook_enabled and not self.config.fallback_polling:
                self.logger.warning("Event hook and fallback polling are disabled; ad blocker not started")
                return

            self.active = True
            self._resize_scheduler.start()

            if self.config.uia_enabled:
                if self._uia:
                    self.logger.info("🧩 UIA fallback enabled (pywinauto)")
                else:
                    self.logger.info("UIA fallback disabled (pywinauto not installed)")

            # Pre-create hook callback to prevent GC race condition
            self._hook_callback = WINEVENTPROC(self._win_event_callback)

            # Start event processing thread + message pump only when hooks are enabled
            if self.config.event_hook_enabled:
                self._event_thread = threading.Thread(target=self._process_events, daemon=True, name="EventProcessor")
                self._event_thread.start()

                self._message_thread = threading.Thread(target=self._message_pump, daemon=True, name="MessagePump")
                self._message_thread.start()
            else:
                self.logger.info("Event hook disabled via config; running polling only")

            # Start fallback polling (optional safety net)
            if self.config.fallback_polling:
                self._fallback_thread = threading.Thread(target=self._fallback_loop, daemon=True, name="FallbackPoller")
                self._fallback_thread.start()
                self.logger.info(
                    f"🔄 Polling started (active {self.config.scan_interval_active:.2f}s / idle {self.config.scan_interval_idle:.2f}s)"
                )

            self.logger.info("🚀 Event-driven ad blocker started")
    
    def stop(self):
        """Stop the event-driven ad blocker."""
        with self._lifecycle_lock:
            if not self.active:
                return
            self.active = False
            self._unhook_all()

            # Send WM_QUIT to message pump thread to unblock GetMessageW
            if self._message_thread_id:
                try:
                    self.user32.PostThreadMessageW(self._message_thread_id, WM_QUIT, 0, 0)
                except Exception:
                    pass

            # Drain queued events to avoid processing stale handles on restart
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except queue.Empty:
                    break
            with self._queue_lock:
                self._queued_events.clear()

            for thread_ref in ("_event_thread", "_message_thread", "_fallback_thread"):
                thread = getattr(self, thread_ref)
                if thread and thread.is_alive():
                    thread.join(timeout=1.5)
                setattr(self, thread_ref, None)

            self._message_thread_id = None
            self._hook_callback = None
            self._resize_scheduler.stop()

            self.logger.info(f"🛑 Event-driven ad blocker stopped. Stats: {self._stats}")
    
    def _message_pump(self):
        """
        Win32 message pump required for SetWinEventHook.
        Hooks are installed here to ensure they run on the correct thread.
        """
        try:
            # Store thread ID for PostThreadMessage
            import ctypes.wintypes
            self._message_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            
            # Install hooks for window events
            events_to_hook = [
                (EVENT_OBJECT_CREATE, EVENT_OBJECT_CREATE),  # Window created
                (EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW),      # Window shown
                (EVENT_OBJECT_REORDER, EVENT_OBJECT_REORDER),  # Child order changed
                (EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_LOCATIONCHANGE),  # Moved/resized
                (EVENT_OBJECT_NAMECHANGE, EVENT_OBJECT_NAMECHANGE),  # Name/text changed
            ]
            
            for event_min, event_max in events_to_hook:
                hook = self.user32.SetWinEventHook(
                    event_min, event_max,
                    None,  # hmodWinEventProc (NULL for out-of-context)
                    self._hook_callback,
                    0,     # idProcess (0 = all processes)
                    0,     # idThread (0 = all threads)
                    WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
                )
                if hook:
                    self._hooks.append(hook)
                    self.logger.debug(f"Installed hook for event {hex(event_min)}")
                else:
                    self.logger.warning(f"Failed to install hook for event {hex(event_min)}")
            
            self.logger.info(f"Installed {len(self._hooks)} event hooks")
            
            # Message pump loop
            msg = ctypes.wintypes.MSG()
            while self.active:
                result = self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:  # WM_QUIT
                    break
                if result == -1:  # Error
                    break
                self.user32.TranslateMessage(ctypes.byref(msg))
                self.user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            self.logger.error(f"Message pump error: {e}")
        finally:
            self._unhook_all()
    
    def _win_event_callback(self, hWinEventHook, event, hwnd, idObject, idChild, 
                            dwEventThread, dwmsEventTime):
        """
        Callback for window events. Called by Windows when registered events occur.
        Must be fast - heavy processing is done in a separate thread.
        """
        try:
            # Skip if window is not valid
            if not hwnd or not User32.is_window(hwnd):
                return

            # Only care about actual window objects
            if idObject != OBJID_WINDOW or idChild != 0:
                return
            
            # Quick PID check if we have KakaoTalk PID
            if self.kakao_pid:
                if User32.get_pid(hwnd) != self.kakao_pid:
                    return
            else:
                self._pid_hint = True
                # Try to find KakaoTalk PID with cooldown to prevent performance issues.
                current_time = time.time()
                interval = self._next_pid_check_interval()
                if current_time - self._last_pid_check >= interval:
                    self._last_pid_check = current_time
                    self._update_kakao_pid()
                if self.kakao_pid and User32.get_pid(hwnd) != self.kakao_pid:
                    return
            
            self._queue_window_event(int(hwnd), int(event))
                
        except Exception as e:
            self._stats["errors"] += 1
            now = time.time()
            if now - self._last_hook_error_log >= 10.0:
                self._last_hook_error_log = now
                try:
                    self.logger.debug(f"WinEvent callback error: {e}")
                except Exception:
                    pass
    
    def _process_events(self):
        """Process window events from the queue."""
        while self.active:
            try:
                hwnd = self._event_queue.get(timeout=0.5)
                with self._queue_lock:
                    event_type = self._queued_events.pop(int(hwnd), None)
                if event_type is None:
                    continue
                self._handle_window_event(WindowEvent(int(hwnd), int(event_type)))
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.debug(f"Event processing error: {e}")
                self._stats["errors"] += 1

    def _queue_window_event(self, hwnd: int, event_type: int) -> None:
        if not hwnd:
            return
        coalesce_sec = max(self.config.event_coalesce_seconds, 0.0)
        now = time.time()
        with self._queue_lock:
            if hwnd in self._queued_events:
                self._queued_events[hwnd] = event_type
                self._stats["events_coalesced"] += 1
                return

            # Coalesce with recently processed handles too, to reduce callback storms.
            if coalesce_sec > 0:
                last_seen = self._processed_events.get(hwnd)
                if last_seen and (now - last_seen) < coalesce_sec:
                    self._stats["events_coalesced"] += 1
                    return

            if self._event_queue.full():
                self._stats["events_dropped"] += 1
                return

            self._queued_events[hwnd] = event_type
            self._event_queue.put_nowait(hwnd)
            self._stats["events_received"] += 1

    def _next_pid_check_interval(self) -> float:
        if self.kakao_pid:
            return max(self.config.pid_check_active_seconds, 0.5)
        return max(self.config.pid_check_idle_seconds, 1.0)

    def _adaptive_root_throttle(self) -> float:
        base = self._root_scan_throttle_sec
        try:
            qsize = self._event_queue.qsize()
        except Exception:
            qsize = 0
        # Stretch throttle when queue is congested.
        if qsize <= 50:
            return base
        factor = min(float(qsize) / 400.0, 3.0)
        return min(base * (1.0 + factor), 1.0)
    
    def _handle_window_event(self, event: WindowEvent):
        """Handle a single window event."""
        hwnd = event.hwnd

        if not User32.is_window(hwnd):
            with self._lock:
                self._processed_events.pop(hwnd, None)
                self._hidden_hwnds.discard(hwnd)
            return
        
        # Skip already processed in this cycle
        now = time.time()
        dedupe_seconds = max(self.config.event_dedupe_seconds, 0.0)
        with self._lock:
            last_seen = self._processed_events.get(hwnd)
            if dedupe_seconds > 0 and last_seen and (now - last_seen) < dedupe_seconds:
                return
            self._processed_events[hwnd] = now

            # Clean old processed events periodically
            if len(self._processed_events) > 2000:
                if dedupe_seconds <= 0:
                    self._processed_events.clear()
                else:
                    cutoff = now - (dedupe_seconds * 4)
                    self._processed_events = {h: t for h, t in self._processed_events.items() if t >= cutoff}
        
        # Get window info
        cls = User32.get_class(hwnd)
        text = User32.get_text(hwnd)
        is_kakao_pid = bool(self.kakao_pid and User32.get_pid(hwnd) == self.kakao_pid)
        is_noisy_layout_event = event.event_type in (EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_NAMECHANGE, EVENT_OBJECT_REORDER)

        parent = hwnd
        for _ in range(6):
            parent = User32.get_parent(parent)
            if not parent or not User32.is_window(parent):
                break
            parent_cls = User32.get_class(parent)
            if self.matcher.is_kakao_window(parent_cls):
                if is_noisy_layout_event:
                    now = time.time()
                    last = self._root_scan_last.get(parent, 0.0)
                    if now - last < self._adaptive_root_throttle():
                        return
                    self._root_scan_last[parent] = now
                self._process_main_window(parent)
                return
        
        # Check if this is a main window with title (for resize)
        if self.matcher.is_main_window(cls, text):
            if is_noisy_layout_event:
                now = time.time()
                last = self._root_scan_last.get(hwnd, 0.0)
                if now - last < self._adaptive_root_throttle():
                    return
                self._root_scan_last[hwnd] = now
            self._process_main_window(hwnd)
        # Check if this is any KakaoTalk window (including ad popups)
        elif self.matcher.is_kakao_window(cls):
            if is_noisy_layout_event:
                now = time.time()
                last = self._root_scan_last.get(hwnd, 0.0)
                if now - last < self._adaptive_root_throttle():
                    return
                self._root_scan_last[hwnd] = now
            self._process_main_window(hwnd)
        # Check if this is an ad window directly
        elif self.matcher.is_ad_window(text, cls):
            self._hide_ad(hwnd, text, reason="pattern")
        # Fallback: KakaoTalk PID matched but class not recognized
        elif is_kakao_pid:
            root_hwnd = self._get_root_window(hwnd)
            if root_hwnd:
                self._process_main_window(root_hwnd)

    @staticmethod
    def _get_root_window(hwnd: int) -> int:
        current = hwnd
        for _ in range(16):
            parent = User32.get_parent(current)
            if not parent or not User32.is_window(parent):
                return current
            current = parent
        return current

    @staticmethod
    def _class_matches_patterns(cls: str, patterns: List[str]) -> bool:
        for pattern in patterns:
            if not pattern:
                continue
            if pattern.endswith("*"):
                if cls.startswith(pattern[:-1]):
                    return True
            elif cls == pattern:
                return True
        return False

    def _collect_children(self, parent_hwnd: int) -> List[WindowInfo]:
        children: List[WindowInfo] = []

        def child_callback(hwnd, _):
            try:
                children.append(WindowInfo(
                    hwnd=hwnd,
                    cls=User32.get_class(hwnd),
                    text=User32.get_text(hwnd),
                    rect=User32.get_window_rect(hwnd),
                    visible=User32.is_visible(hwnd)
                ))
            except Exception:
                pass
            return True

        callback_func = WNDENUMPROC(child_callback)
        self.user32.EnumChildWindows(parent_hwnd, callback_func, 0)
        return children

    def _select_list_pane_rect(self, children: List[WindowInfo]) -> Optional[ctypes.wintypes.RECT]:
        pane_rect = None
        pane_height = 0
        for child in children:
            if not child.rect:
                continue
            if self.matcher.is_resize_target(child.text, child.cls):
                height = child.rect.bottom - child.rect.top
                if height <= 0:
                    continue
                if pane_rect is None or height > pane_height or (height == pane_height and child.rect.left < pane_rect.left):
                    pane_rect = child.rect
                    pane_height = height
        return pane_rect

    def _is_layout_ad(self, child: WindowInfo, parent_rect: Optional[ctypes.wintypes.RECT],
                      pane_rect: Optional[ctypes.wintypes.RECT]) -> bool:
        if not self.config.layout_enabled:
            return False
        # Some KakaoTalk ad containers can report invisible while still reserving layout space.
        if not child.rect:
            return False

        width = child.rect.right - child.rect.left
        height = child.rect.bottom - child.rect.top
        if width <= 0 or height <= 0:
            return False
        if height < self.config.layout_min_height or height > self.config.layout_max_height:
            return False

        allowlist = self.config.layout_class_allowlist
        if allowlist and not self._class_matches_patterns(child.cls, allowlist):
            return False
        blocklist = self.config.layout_class_blocklist
        if blocklist and self._class_matches_patterns(child.cls, blocklist):
            return False

        ref_rect = pane_rect or parent_rect
        if not ref_rect:
            return False
        ref_width = ref_rect.right - ref_rect.left
        if ref_width <= 0:
            return False

        min_width_ratio = self.config.layout_min_width_ratio
        if width < ref_width * min_width_ratio:
            return False
        inter_left = max(child.rect.left, ref_rect.left)
        inter_right = min(child.rect.right, ref_rect.right)
        inter_width = inter_right - inter_left
        if inter_width < ref_width * min_width_ratio:
            return False

        bottom_margin = self.config.layout_bottom_margin
        if abs(child.rect.bottom - ref_rect.bottom) > bottom_margin:
            return False

        return True
    
    def _process_main_window(self, parent_hwnd: int):
        """Process child windows of a KakaoTalk main window."""
        ads_found = False

        if not User32.is_window(parent_hwnd):
            return

        # Safety: never touch windows outside the KakaoTalk PID once known.
        if self.kakao_pid:
            try:
                if User32.get_pid(parent_hwnd) != self.kakao_pid:
                    return
            except Exception:
                return

        # Build a bounded subtree snapshot (graph-based) so we can detect deeply nested ad containers.
        snapshot = self._graph.snapshot_root(parent_hwnd, max_depth=8)
        parent_node = snapshot.get(parent_hwnd)
        parent_rect_win = User32.get_window_rect(parent_hwnd)
        parent_rect = parent_node.rect if parent_node and parent_node.rect else _rect_to_tuple(parent_rect_win)

        # Build direct-child info from the snapshot to avoid extra Win32 enumeration.
        children: List[WindowInfo] = []
        for hwnd, node in snapshot.items():
            if hwnd == parent_hwnd or node.parent_hwnd != parent_hwnd:
                continue
            children.append(
                WindowInfo(
                    hwnd=hwnd,
                    cls=node.cls or "",
                    text=node.title or "",
                    rect=_tuple_to_rect(node.rect),
                    visible=node.visible,
                )
            )
        pane_rect = self._select_list_pane_rect(children)

        # Rate-limited layout diagnostics (helps when banner is visible but not detected).
        now = time.time()
        if not hasattr(self, "_last_layout_diag"):
            self._last_layout_diag = {}
        last_diag = self._last_layout_diag.get(parent_hwnd, 0.0)

        # 1) High-confidence hide patterns across the entire subtree.
        for hwnd, n in snapshot.items():
            if hwnd == parent_hwnd:
                continue
            if self.matcher.is_ad_window(n.title or "", n.cls or ""):
                label = n.title or f"[{n.cls}]"
                if self._hide_ad(hwnd, label, reason="pattern"):
                    ads_found = True

        # 2) Score-based banner detection (geometry + signals).
        if self.config.layout_engine_enabled:
            to_hide, _observed = self._layout_engine.detect_banners(snapshot, parent_hwnd)
            for hwnd, label, score in to_hide:
                if self._hide_ad(hwnd, f"{label} (score={score})", reason="layout_engine"):
                    ads_found = True
        else:
            # Fallback: old heuristic-based detection using direct children only.
            for child in children:
                if self._is_layout_ad(child, parent_rect_win, pane_rect):
                    height = child.rect.bottom - child.rect.top if child.rect else 0
                    label = child.text or f"[Layout {height}px {child.cls}]"
                    if self._hide_ad(child.hwnd, label, reason="layout"):
                        ads_found = True

        if not ads_found and now - last_diag >= 10.0:
            self._last_layout_diag[parent_hwnd] = now
            try:
                ref_rect = pane_rect or parent_rect_win
                if ref_rect:
                    ref_w = ref_rect.right - ref_rect.left
                    ref_b = ref_rect.bottom
                    candidates = []
                    for c in children:
                        if not c.rect:
                            continue
                        w = c.rect.right - c.rect.left
                        h = c.rect.bottom - c.rect.top
                        if h <= 0 or w <= 0:
                            continue
                        if 40 <= h <= 300 and ref_w > 0 and w >= ref_w * 0.7 and abs(c.rect.bottom - ref_b) <= 40:
                            candidates.append((h, w, c))
                    candidates.sort(key=lambda x: (x[0] * x[1]), reverse=True)
                    for h, w, c in candidates[:5]:
                        self.logger.debug(
                            f"Layout diag cand: cls={c.cls} vis={c.visible} h={h} w={w} text={c.text[:40]!r}"
                        )
            except Exception:
                pass
        
        # Schedule delayed resize if ads were hidden
        if ads_found:
            self._schedule_resize(parent_hwnd)
    
    def _schedule_resize(self, parent_hwnd: int):
        """Schedule a delayed resize after ads are hidden."""
        if not self.active:
            return
        self._resize_scheduler.schedule(parent_hwnd, delays=(0.4, 0.8, 1.2, 1.8))
    
    def _do_resize_children(self, parent_hwnd: int):
        """Perform resize on all resize targets in a window."""
        snapshot = self._graph.snapshot_root(parent_hwnd, max_depth=8)
        resize_targets: List[int] = []
        for hwnd, n in snapshot.items():
            if hwnd == parent_hwnd:
                continue
            try:
                if self.matcher.is_resize_target(n.title or "", n.cls or ""):
                    resize_targets.append(hwnd)
            except Exception:
                continue

        if resize_targets:
            self._resize_views_batch(resize_targets, parent_hwnd)
            return

        # Fallback: pick the largest plausible EVA_* child view if patterns broke.
        excluded = set(self.config.layout_engine_excluded_classes or [])
        excluded.update({
            "Chrome_WidgetWin_0",
            "Chrome_WidgetWin_1",
        })
        best_hwnd = 0
        best_area = 0
        for hwnd, n in snapshot.items():
            if hwnd == parent_hwnd:
                continue
            if not n.rect:
                continue
            if n.cls in excluded:
                continue
            if not (n.cls.startswith("EVA_") or n.cls.startswith("EVA")):
                continue
            w = _rect_w(n.rect)
            h = _rect_h(n.rect)
            if h < max(int(self.config.min_view_height), 80) or w < 200:
                continue
            area = w * h
            if area > best_area:
                best_area = area
                best_hwnd = hwnd

        if best_hwnd:
            self.logger.debug(f"Resize fallback target selected: hwnd={best_hwnd} area={best_area}")
            self._resize_views_batch([best_hwnd], parent_hwnd)

    def _resize_views_batch(self, target_hwnds: List[int], parent_hwnd: int):
        """Resize multiple target views using DeferWindowPos when possible."""
        if not target_hwnds:
            return

        # Deduplicate while preserving order.
        seen: Set[int] = set()
        ordered = []
        for h in target_hwnds:
            if h and h not in seen:
                seen.add(h)
                ordered.append(h)

        if len(ordered) == 1:
            self._resize_view(ordered[0], parent_hwnd)
            return

        parent_rect = User32.get_client_rect(parent_hwnd)
        if not parent_rect:
            return
        parent_height = parent_rect.bottom - parent_rect.top
        if parent_height <= 0:
            return

        ops: List[Tuple[int, int, int, int]] = []  # (hwnd, cur_w, cur_h, target_h)
        for hwnd in ordered:
            try:
                child_rect = User32.get_window_rect(hwnd)
                if not child_rect:
                    continue
                _, client_y = User32.screen_to_client(parent_hwnd, child_rect.left, child_rect.top)
                target_h = parent_height - client_y
                if target_h < self.config.min_view_height:
                    continue
                cur_h = child_rect.bottom - child_rect.top
                cur_w = child_rect.right - child_rect.left
                if cur_w <= 0 or cur_h <= 0:
                    continue
                if abs(target_h - cur_h) <= self.config.resize_threshold:
                    continue
                ops.append((hwnd, cur_w, cur_h, int(target_h)))
            except Exception:
                continue

        if not ops:
            return
        if len(ops) == 1:
            self._resize_view(ops[0][0], parent_hwnd)
            return

        try:
            u32 = ctypes.windll.user32
            u32.BeginDeferWindowPos.restype = ctypes.c_void_p
            u32.DeferWindowPos.restype = ctypes.c_void_p
            u32.EndDeferWindowPos.restype = ctypes.wintypes.BOOL

            flags = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
            hdwp = u32.BeginDeferWindowPos(len(ops))
            if not hdwp:
                for hwnd, _w, _ch, _th in ops:
                    self._resize_view(hwnd, parent_hwnd)
                return

            for hwnd, cur_w, _cur_h, target_h in ops:
                hdwp = u32.DeferWindowPos(hdwp, hwnd, 0, 0, 0, cur_w, target_h, flags)
                if not hdwp:
                    break

            ok = bool(u32.EndDeferWindowPos(hdwp)) if hdwp else False
            if ok:
                self._stats["resizes"] += len(ops)
                if self.config.log_resizes:
                    self.logger.info(f"📐 Batch resized {len(ops)} view(s)")
                else:
                    self.logger.debug(f"Batch resized {len(ops)} view(s)")
            else:
                for hwnd, _w, _ch, _th in ops:
                    self._resize_view(hwnd, parent_hwnd)
        except Exception:
            for hwnd, _w, _ch, _th in ops:
                self._resize_view(hwnd, parent_hwnd)
    
    def _hide_ad(self, hwnd: int, text: str, reason: str = "") -> bool:
        """Hide an ad window by hiding or moving it off-screen. Returns True if ad was hidden."""
        with self._lock:
            if not User32.is_window(hwnd):
                self._hidden_hwnds.discard(hwnd)
                self._processed_events.pop(hwnd, None)
                return False
            if hwnd in self._hidden_hwnds:
                if User32.is_visible(hwnd):
                    self._hidden_hwnds.discard(hwnd)
                else:
                    return False

            hidden = False
            # Even if IsWindowVisible is false, try hiding/moving to avoid "visible but not reported" cases.
            try:
                User32.show_window(hwnd, SW_HIDE)
            except Exception:
                pass

            if not User32.is_visible(hwnd):
                hidden = True
            else:
                rect = User32.get_window_rect(hwnd)
                if rect:
                    flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOSIZE
                    if self.user32.SetWindowPos(hwnd, 0, -9999, -9999, 0, 0, flags):
                        hidden = True

            if hidden:
                self._hidden_hwnds.add(hwnd)
                self._stats["ads_hidden"] += 1
                if self.config.log_hidden_ads:
                    suffix = f" ({reason})" if reason else ""
                    self.logger.info(f"🚫 Hidden ad{suffix}: {text[:40]}")
                return True
        return False
    
    def _resize_view(self, hwnd: int, parent_hwnd: int):
        """Resize main view to fill space."""
        try:
            parent_rect = User32.get_client_rect(parent_hwnd)
            if not parent_rect:
                self.logger.debug(f"Resize failed: No parent rect for {parent_hwnd}")
                return
            parent_height = parent_rect.bottom - parent_rect.top
            parent_width = parent_rect.right - parent_rect.left
            
            child_rect = User32.get_window_rect(hwnd)
            if not child_rect:
                self.logger.debug(f"Resize failed: No child rect for {hwnd}")
                return
            
            _, client_y = User32.screen_to_client(parent_hwnd, child_rect.left, child_rect.top)
            target_height = parent_height - client_y
            
            if target_height < self.config.min_view_height:
                self.logger.debug(f"Resize skipped: target_height {target_height} < min {self.config.min_view_height}")
                return
            
            current_height = child_rect.bottom - child_rect.top
            current_width = child_rect.right - child_rect.left
            
            height_diff = abs(target_height - current_height)
            if height_diff > self.config.resize_threshold:
                flags = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
                if User32.set_window_pos(hwnd, 0, 0, current_width, target_height, flags):
                    self._stats["resizes"] += 1
                    if self.config.log_resizes:
                        self.logger.info(f"📐 Resized view: {current_height} -> {target_height} (diff: {height_diff})")
                    else:
                        self.logger.debug(f"Resized view: {current_height} -> {target_height} (diff: {height_diff})")
                else:
                    self.logger.warning(f"SetWindowPos failed for hwnd {hwnd}")
            else:
                self.logger.debug(f"Resize not needed: diff {height_diff} <= threshold {self.config.resize_threshold}")
        except Exception as e:
            self.logger.debug(f"Resize error: {e}")
    
    def _fallback_loop(self):
        """Polling loop using configured intervals."""
        scan_count = 0
        while self.active:
            try:
                now = time.time()
                interval_pid = self._next_pid_check_interval()
                if (now - self._last_pid_check >= interval_pid) or self._pid_hint:
                    self._last_pid_check = now
                    self._pid_hint = False
                    self._update_kakao_pid()
                if self.kakao_pid:
                    self._aggressive_scan()
                    self._maybe_uia_scan()
                    scan_count += 1
                    # Log every 25 scans to keep logs readable
                    if scan_count % 25 == 0:
                        self.logger.debug(f"Aggressive scan #{scan_count} completed, hidden: {self._stats['ads_hidden']}")
                interval = self.config.scan_interval_active if self.kakao_pid else self.config.scan_interval_idle
                time.sleep(max(interval, 0.05))
            except Exception as e:
                self.logger.debug(f"Fallback scan error: {e}")
                time.sleep(1)

    def _maybe_uia_scan(self):
        if not self._uia or not self.config.uia_enabled or not self.kakao_pid:
            return
        now = time.time()
        interval = max(self.config.uia_scan_interval, 0.2)
        # Add low jitter so repeated instances don't synchronize UIA scans.
        interval *= (1.0 + random.uniform(-0.08, 0.08))
        if now - self._last_uia_scan < interval:
            return
        self._last_uia_scan = now
        hidden, roots = self._uia.scan(self.kakao_pid)
        if hidden:
            for root in roots:
                self._schedule_resize(root)
            if self.config.log_hidden_ads:
                self.logger.info(f"🚫 UIA hidden {hidden} element(s)")
            else:
                self.logger.debug(f"UIA hidden {hidden} element(s)")
    
    def _aggressive_scan(self):
        """Aggressively scan and hide ads (no caching - always hide)."""
        def enum_callback(hwnd, _):
            try:
                pid = User32.get_pid(hwnd)
                if self.kakao_pid and pid != self.kakao_pid:
                    return True
                
                cls = User32.get_class(hwnd)
                
                # Process all KakaoTalk windows
                if self.matcher.is_kakao_window(cls) or (self.kakao_pid and pid == self.kakao_pid):
                    self._process_window_aggressive(hwnd)
            except Exception:
                pass
            return True
        
        callback_func = WNDENUMPROC(enum_callback)
        self.user32.EnumWindows(callback_func, 0)
    
    def _process_window_aggressive(self, parent_hwnd: int):
        """Process child windows aggressively - always try to hide ads."""
        self._process_main_window(parent_hwnd)
    
    def _hide_ad_force(self, hwnd: int):
        """Force hide ad window (bypass cached state)."""
        label = User32.get_text(hwnd) or f"[{User32.get_class(hwnd)}]"
        with self._lock:
            self._hidden_hwnds.discard(hwnd)
        return self._hide_ad(hwnd, label, reason="force")
    
    def _scan_all_windows(self):
        """Scan all windows (manual refresh)."""
        main_windows: Set[int] = set()

        def enum_callback(hwnd, _):
            try:
                pid = User32.get_pid(hwnd)
                cls = User32.get_class(hwnd)
                title = User32.get_text(hwnd)
                
                # Process all KakaoTalk windows (including ad popups without title)
                if self.kakao_pid and pid == self.kakao_pid:
                    main_windows.add(hwnd)
                    self._process_main_window(hwnd)
                elif self.kakao_pid and self.matcher.is_ad_window(title, cls):
                    label = title or f"[{cls}]"
                    self._hide_ad(hwnd, label, reason="manual")
            except Exception:
                pass
            return True
        
        callback_func = WNDENUMPROC(enum_callback)
        self.user32.EnumWindows(callback_func, 0)

        for hwnd in list(main_windows):
            if User32.is_window(hwnd):
                self._do_resize_children(hwnd)
    
    def _update_kakao_pid(self):
        """Update KakaoTalk process ID and reset state on change."""
        self._last_pid_check = time.time()
        new_pid = None
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name', 'pid']):
                    if 'kakaotalk.exe' in (p.info['name'] or '').lower():
                        new_pid = p.info['pid']
                        break
            except Exception:
                pass

        if new_pid is None:
            try:
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq kakaotalk.exe', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, creationflags=0x08000000, timeout=5
                )
                line = result.stdout.strip()
                if line and 'kakaotalk.exe' in line.lower():
                    parts = line.split(',')
                    if len(parts) >= 2:
                        new_pid = int(parts[1].replace('"', ''))
            except Exception:
                pass

        # Title-based fallback: some builds may change main window class names.
        if new_pid is None and self.user32:
            try:
                pid_holder = {"pid": None}

                def enum_by_title(hwnd, _):
                    try:
                        title = User32.get_text(hwnd)
                        if title and ("카카오톡" in title or "KakaoTalk" in title):
                            pid = User32.get_pid(hwnd)
                            if pid:
                                pid_holder["pid"] = pid
                                return False
                    except Exception:
                        pass
                    return True

                callback_func = WNDENUMPROC(enum_by_title)
                self.user32.EnumWindows(callback_func, 0)
                new_pid = pid_holder["pid"]
            except Exception:
                pass

        if new_pid is None and self.user32:
            try:
                pid_holder = {"pid": None}
                def enum_callback(hwnd, _):
                    try:
                        cls = User32.get_class(hwnd)
                        if self.matcher.is_kakao_window(cls):
                            pid = User32.get_pid(hwnd)
                            if pid:
                                pid_holder["pid"] = pid
                                return False
                    except Exception:
                        pass
                    return True
                callback_func = WNDENUMPROC(enum_callback)
                self.user32.EnumWindows(callback_func, 0)
                new_pid = pid_holder["pid"]
            except Exception:
                pass

        if new_pid != self.kakao_pid:
            old_pid = self.kakao_pid
            self.kakao_pid = new_pid
            User32.clear_cache()
            if old_pid is not None:
                self._previous_kakao_pid = old_pid
                self._on_kakao_pid_changed()
    
    def _on_kakao_pid_changed(self):
        """Reset internal state when KakaoTalk restarts (PID changes)."""
        with self._lock:
            self._hidden_hwnds.clear()
            self._processed_events.clear()
        with self._queue_lock:
            self._queued_events.clear()
        if self._previous_kakao_pid is not None:
            self.logger.info(f"🔄 KakaoTalk PID changed ({self._previous_kakao_pid} -> {self.kakao_pid}) - internal state reset")
        else:
            self.logger.info("🔄 KakaoTalk PID changed - internal state reset")
    
    def _unhook_all(self):
        """Remove all installed hooks."""
        for hook in self._hooks:
            try:
                self.user32.UnhookWinEvent(hook)
            except Exception:
                pass
        self._hooks.clear()
    
    @property
    def stats(self) -> Dict:
        return self._stats.copy()
    
    def force_scan(self):
        """Force immediate scan of all windows (for manual refresh)."""
        with self._lock:
            self._hidden_hwnds.clear()
            self._processed_events.clear()
        with self._queue_lock:
            self._queued_events.clear()
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except queue.Empty:
                break
        self._update_kakao_pid()
        if self.kakao_pid:
            self._scan_all_windows()
            self._last_uia_scan = 0.0
            self._maybe_uia_scan()
            self.logger.info("🔄 Force scan completed")
        else:
            self.logger.warning("KakaoTalk not running")

    def dump_window_tree(self, out_dir: Optional[str] = None) -> Optional[str]:
        """Dump KakaoTalk top-level roots and bounded subtrees to a JSON file for diagnostics."""
        if not self.user32:
            return None
        self._update_kakao_pid()
        if not self.kakao_pid:
            return None

        roots: List[int] = []

        def enum_cb(hwnd, _):
            try:
                if User32.get_pid(hwnd) != self.kakao_pid:
                    return True
                cls = User32.get_class(hwnd)
                title = User32.get_text(hwnd)
                if self.matcher.is_kakao_window(cls) or ("카카오톡" in (title or "") or "KakaoTalk" in (title or "")):
                    roots.append(int(hwnd))
            except Exception:
                pass
            return True

        try:
            self.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        except Exception:
            return None

        roots = list(dict.fromkeys(roots))  # stable unique
        if not roots:
            return None

        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kakao_pid": int(self.kakao_pid or 0),
            "roots": [],
        }
        for r in roots:
            try:
                snap = self._graph.snapshot_root(r, max_depth=10)
                payload["roots"].append(self._graph.to_jsonable(snap, r))
            except Exception:
                continue

        try:
            out_dir = out_dir or APPDATA_DIR
            os.makedirs(out_dir, exist_ok=True)
            name = f"window_dump_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Window tree dump saved: {path}")
            return path
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# Settings & System Managers (Same as v9.0)
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class AppSettings:
    auto_start: bool = False
    minimize_to_tray: bool = True
    hide_layout: bool = True
    block_adfit: bool = True
    adfit_update_interval_sec: int = 10
    realtime_protection: bool = True
    theme: str = "light"
    ui_batch_log_interval_ms: int = 100
    ui_status_interval_ms: int = 2000
    
    @classmethod
    def load(cls):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                    merged, changed = _merge_with_schema(raw, cls().__dict__)
                    if changed:
                        _make_backup(SETTINGS_FILE)
                        with open(SETTINGS_FILE, "w", encoding="utf-8") as wf:
                            json.dump(merged, wf, indent=2, ensure_ascii=False)
                    return cls(**{k: v for k, v in merged.items() if k in cls.__dataclass_fields__})
        except Exception:
            pass
        return cls()
    
    def save(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

class AdFitBlocker:
    KEY = r"SOFTWARE\Kakao\AdFit"

    def __init__(self, logger, update_interval_sec: int = 10):
        self.logger = logger.getChild("AdFitBlocker")
        self.update_interval_sec = max(int(update_interval_sec or 10), 1)
        self.active = False
        self._thread: Optional[threading.Thread] = None
        self._original_values: Dict[str, Optional[str]] = {}
        self._last_log: Dict[str, float] = {}
        self._log_backoff_sec = 10.0

    def _log_debug_rl(self, key: str, msg: str):
        now = time.time()
        last = self._last_log.get(key, 0.0)
        if now - last < self._log_backoff_sec:
            return
        self._last_log[key] = now
        try:
            self.logger.debug(msg)
        except Exception:
            pass

    def _key_exists(self) -> bool:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY, 0, winreg.KEY_READ)
            winreg.CloseKey(k)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def _snapshot_originals(self):
        self._original_values.clear()
        if not self._key_exists():
            self._log_debug_rl("missing_key", f"Registry key not found: HKCU\\{self.KEY}")
            return
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY, 0, winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS)
        except Exception as e:
            self._log_debug_rl("snapshot_open", f"AdFit snapshot open error: {e}")
            return

        idx = 0
        while True:
            try:
                name = winreg.EnumKey(key, idx)
                idx += 1
                try:
                    sk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{self.KEY}\\{name}", 0, winreg.KEY_READ)
                    try:
                        cur, _typ = winreg.QueryValueEx(sk, "LUD")
                        self._original_values[name] = str(cur) if cur is not None else None
                    except FileNotFoundError:
                        self._original_values[name] = None
                    except Exception:
                        self._original_values[name] = None
                    finally:
                        winreg.CloseKey(sk)
                except Exception:
                    continue
            except OSError:
                break
            except Exception:
                break

        try:
            winreg.CloseKey(key)
        except Exception:
            pass

    def _restore_originals(self):
        if not self._original_values:
            return
        for name, orig in list(self._original_values.items()):
            try:
                sk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{self.KEY}\\{name}", 0, winreg.KEY_SET_VALUE)
                try:
                    if orig is None:
                        try:
                            winreg.DeleteValue(sk, "LUD")
                        except FileNotFoundError:
                            pass
                    else:
                        winreg.SetValueEx(sk, "LUD", 0, winreg.REG_SZ, str(orig))
                finally:
                    winreg.CloseKey(sk)
            except Exception:
                continue

    def start(self):
        if self.active:
            return
        if self._thread and self._thread.is_alive():
            return
        self._snapshot_originals()
        self.active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.active = False
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None
        try:
            self._restore_originals()
        except Exception as e:
            self._log_debug_rl("restore", f"AdFit restore error: {e}")

    def _loop(self):
        while self.active:
            self._update()
            time.sleep(float(self.update_interval_sec))

    def _update(self):
        if not self._key_exists():
            self._log_debug_rl("missing_key", f"Registry key not found: HKCU\\{self.KEY}")
            return
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY, 0, winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS)
            idx, cur = 0, str(int(time.time()))
            while True:
                try:
                    name = winreg.EnumKey(key, idx)
                    try:
                        sk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{self.KEY}\\{name}", 0, winreg.KEY_WRITE)
                        winreg.SetValueEx(sk, "LUD", 0, winreg.REG_SZ, cur)
                        winreg.CloseKey(sk)
                    except Exception as e:
                        self._log_debug_rl("update_subkey", f"AdFit update subkey error: {e}")
                    idx += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception as e:
            self._log_debug_rl("update", f"AdFit update error: {e}")

class SystemManager:
    _proc_cache: Dict[str, Tuple[float, bool]] = {}
    _proc_cache_ttl = 1.5

    @staticmethod
    def is_admin(): 
        try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False
    @staticmethod
    def run_as_admin():
        # For frozen EXE, do not pass argv[0] again as the first argument.
        argv = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        params = " ".join(f'"{a}"' for a in argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        sys.exit(0)
    @staticmethod
    def flush_dns():
        try: subprocess.run("ipconfig /flushdns", capture_output=True, creationflags=0x08000000, timeout=10); return True
        except: return False
    @staticmethod
    def is_process_running(name):
        key = (name or "").lower()
        now = time.time()
        cached = SystemManager._proc_cache.get(key)
        if cached and (now - cached[0]) <= SystemManager._proc_cache_ttl:
            return cached[1]

        result = False
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name']):
                    if key in (p.info['name'] or '').lower():
                        result = True
                        break
            except: pass
        if not result:
            try:
                res = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}.exe', '/NH'], capture_output=True, text=True, creationflags=0x08000000, timeout=5)
                result = key in res.stdout.lower()
            except:
                result = False
        SystemManager._proc_cache[key] = (now, result)
        return result
    @staticmethod
    def restart_process(name):
        exe_path = None
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name', 'exe']):
                    if name.lower() in (p.info['name'] or '').lower(): exe_path = p.info['exe']; break
            except: pass
        subprocess.run(['taskkill', '/f', '/im', name], capture_output=True, creationflags=0x08000000)
        time.sleep(1.5)
        if exe_path and os.path.exists(exe_path): os.startfile(exe_path); return True
        paths = [os.path.join(os.environ.get(k, ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe') for k in ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA']]
        for p in paths:
            if os.path.exists(p): os.startfile(p); return True
        return False

class HostsManager:
    DEFAULT_PATH = r"C:\Windows\System32\drivers\etc\hosts"
    START, END = "# [KakaoTalk AdBlock Start]", "# [KakaoTalk AdBlock End]"

    def __init__(self, logger, hosts_path: Optional[str] = None):
        self.logger = logger.getChild("HostsManager")
        self.hosts_path = hosts_path or self.DEFAULT_PATH
        self.backup_dir = os.path.join(APPDATA_DIR, "backups", "hosts")

    def _read_hosts(self) -> tuple[str, str, str, bool]:
        with open(self.hosts_path, "rb") as f:
            data = f.read()

        newline = "\r\n" if b"\r\n" in data else "\n"
        has_bom = data.startswith(codecs.BOM_UTF8)

        if has_bom:
            text = data.decode("utf-8-sig", errors="replace")
            encoding = "utf-8-sig"
        else:
            try:
                text = data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                text = data.decode("mbcs", errors="replace")
                encoding = "mbcs"

        return text, newline, encoding, has_bom

    def _write_hosts(self, text: str, newline: str, encoding: str, has_bom: bool) -> bool:
        out = newline.join(text.splitlines())
        if not out.endswith(newline):
            out += newline

        enc = "utf-8-sig" if has_bom else encoding
        payload = out.encode(enc, errors="replace")

        tmp = f"{self.hosts_path}.kakao_adblock.tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(payload)
            os.replace(tmp, self.hosts_path)
            return True
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _strip_block(self, content: str) -> tuple[str, bool]:
        lines = content.splitlines()
        out = []
        skipping = False
        removed = False
        for line in lines:
            if self.START in line:
                skipping = True
                removed = True
                continue
            if skipping:
                if self.END in line:
                    skipping = False
                continue
            out.append(line)
        return "\n".join(out), removed

    @staticmethod
    def _normalize_domains(domains: List[str], logger: Optional[logging.Logger] = None) -> List[str]:
        seen: Set[str] = set()
        out: List[str] = []
        for raw in domains or []:
            d = (raw or "").strip().lower()
            if not d:
                continue
            if any(ch.isspace() for ch in d) or "/" in d or "\\" in d:
                if logger:
                    logger.debug(f"Skipping invalid domain (contains space/slash): {raw!r}")
                continue
            if not re.fullmatch(r"[a-z0-9.-]+", d):
                if logger:
                    logger.debug(f"Skipping invalid domain (bad chars): {raw!r}")
                continue
            if d in seen:
                continue
            seen.add(d)
            out.append(d)
        return out

    def backup_hosts(self) -> Optional[str]:
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            dst = os.path.join(self.backup_dir, f"hosts.{ts}.bak")
            shutil.copy2(self.hosts_path, dst)
            return dst
        except Exception as e:
            self.logger.debug(f"Hosts backup failed: {e}")
            return None

    def block(self, domains: List[str]) -> bool:
        domains = self._normalize_domains(domains, self.logger)
        try:
            content, newline, encoding, has_bom = self._read_hosts()
        except Exception as e:
            self.logger.error(f"Failed to read hosts file: {e}")
            return False

        stripped, _removed = self._strip_block(content)
        stripped = stripped.rstrip("\r\n")

        block_lines = [
            self.START,
            f"# Updated: {datetime.now()}",
            *[f"0.0.0.0 {d}" for d in domains],
            self.END,
        ]

        new_text = stripped
        if new_text:
            new_text += "\n\n"
        new_text += "\n".join(block_lines) + "\n"

        backup_path = self.backup_hosts()

        try:
            if self._write_hosts(new_text, newline, encoding, has_bom):
                if backup_path:
                    self.logger.info(f"Blocked {len(domains)} domains (hosts backup: {backup_path})")
                else:
                    self.logger.info(f"Blocked {len(domains)} domains")
                return True
            self.logger.error("Failed to write hosts file (unknown error)")
            return False
        except PermissionError:
            self.logger.error("Permission denied writing to hosts file - run as administrator")
            return False
        except Exception as e:
            self.logger.error(f"Failed to write hosts file: {e}")
            return False

    def unblock(self) -> bool:
        try:
            content, newline, encoding, has_bom = self._read_hosts()
        except Exception as e:
            self.logger.error(f"Failed to read hosts file: {e}")
            return False

        stripped, removed = self._strip_block(content)
        if not removed:
            self.logger.info("Hosts block not found (nothing to restore)")
            return True

        stripped = stripped.rstrip("\r\n") + "\n"
        backup_path = self.backup_hosts()

        try:
            ok = self._write_hosts(stripped, newline, encoding, has_bom)
            if ok:
                if backup_path:
                    self.logger.info(f"Hosts restored (backup: {backup_path})")
                else:
                    self.logger.info("Hosts restored")
                return True
            self.logger.error("Failed to restore hosts (unknown error)")
            return False
        except PermissionError:
            self.logger.error("Permission denied writing to hosts file - run as administrator")
            return False
        except Exception as e:
            self.logger.error(f"Failed to restore hosts: {e}")
            return False

    def get_status(self, domains: List[str]) -> float:
        domains = self._normalize_domains(domains, None)
        if not domains:
            return 0.0
        try:
            content, _nl, _enc, _bom = self._read_hosts()
            in_block = False
            seen: Set[str] = set()
            for line in content.splitlines():
                if self.START in line:
                    in_block = True
                    continue
                if self.END in line:
                    break
                if not in_block:
                    continue
                m = re.match(r"^\\s*(?:0\\.0\\.0\\.0|127\\.0\\.0\\.1)\\s+([^\\s#]+)", line)
                if m:
                    seen.add(m.group(1).strip().lower())
            matched = sum(1 for d in domains if d in seen)
            return matched / len(domains)
        except Exception:
            return 0.0

class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerPro"
    @staticmethod
    def is_enabled():
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(k, StartupManager.NAME); winreg.CloseKey(k); return True
        except: return False
    @staticmethod
    def set_enabled(enable):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                exe = sys.executable
                path = f'"{exe}" "{os.path.abspath(sys.argv[0])}" --minimized' if exe.endswith('python.exe') else f'"{exe}" --minimized'
                winreg.SetValueEx(k, StartupManager.NAME, 0, winreg.REG_SZ, path)
            else:
                try: winreg.DeleteValue(k, StartupManager.NAME)
                except: pass
            winreg.CloseKey(k); return True
        except: return False

class TrayManager:
    def __init__(self, app): self.app = app; self.icon = None; self.running = False
    def setup(self):
        if not TRAY_AVAILABLE: return
        self.icon = pystray.Icon("KakaoTalkAdBlocker", self._create_icon(), APP_NAME, pystray.Menu(
            pystray.MenuItem("열기", lambda: self.app.root.after(0, self.app.show_window)),
            pystray.MenuItem("종료", lambda: self.app.root.after(0, self.app.quit_app))))
    def _create_icon(self):
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0)); draw = ImageDraw.Draw(img)
        draw.polygon([(32, 4), (60, 14), (60, 32), (32, 60), (4, 32), (4, 14)], fill=(254, 229, 0, 255), outline=(200, 180, 0, 255))
        draw.line([(18, 32), (26, 42), (46, 20)], fill=(25, 25, 25, 255), width=5); return img
    def start(self):
        if not self.running and TRAY_AVAILABLE and self.icon: 
            self.running = True
            threading.Thread(target=self.icon.run, daemon=True).start()
    def stop(self):
        if self.running and self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.running = False


# ═══════════════════════════════════════════════════════════════════════════════
# UI Components
# ═══════════════════════════════════════════════════════════════════════════════
class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=120, height=40,
                 bg_color=None, fg_color=None, hover_color=None):
        bg_color = bg_color or COLORS["primary"]
        fg_color = fg_color or COLORS["text"]
        hover_color = hover_color or COLORS["primary_dark"]
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0)
        self.command, self.bg_color, self.hover_color, self.fg_color = command, bg_color, hover_color, fg_color
        self.enabled = True
        self._normal_bg = bg_color
        self._normal_hover = hover_color
        self._normal_fg = fg_color
        self.rect = self._create_rounded_rect(2, 2, width - 2, height - 2, 8, fill=bg_color, outline="")
        self.label = self.create_text(width / 2, height / 2, text=text, fill=fg_color, font=("맑은 고딕", 10, "bold"))
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if self.enabled:
            self.bg_color = self._normal_bg
            self.hover_color = self._normal_hover
            self.fg_color = self._normal_fg
            self.itemconfig(self.rect, fill=self.bg_color)
            self.itemconfig(self.label, fill=self.fg_color)
            self.config(cursor="")
        else:
            self.itemconfig(self.rect, fill=COLORS.get("border", "#DDDDDD"))
            self.itemconfig(self.label, fill=COLORS.get("sub_text", "#777777"))
            self.config(cursor="arrow")

    def _on_enter(self, _e=None):
        if not self.enabled:
            return
        self.itemconfig(self.rect, fill=self.hover_color)
        self.config(cursor="hand2")

    def _on_leave(self, _e=None):
        if not self.enabled:
            return
        self.itemconfig(self.rect, fill=self.bg_color)
        self.config(cursor="")

    def _on_press(self, _e=None):
        if not self.enabled:
            return
        self.move(self.label, 1, 1)

    def _on_release(self, _e=None):
        if not self.enabled:
            return
        self.move(self.label, -1, -1)
        if self.command:
            self.command()
    def _create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1+r,y1,x1+r,y1,x2-r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y1+r,x2,y2-r,x2,y2-r,x2,y2,x2-r,y2,x2-r,y2,x1+r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y2-r,x1,y1+r,x1,y1+r,x1,y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def update_colors(self, bg_color=None, fg_color=None, hover_color=None, canvas_bg=None):
        if bg_color:
            self.bg_color = bg_color
            self.itemconfig(self.rect, fill=bg_color)
            self._normal_bg = bg_color
        if fg_color:
            self.fg_color = fg_color
            self.itemconfig(self.label, fill=fg_color)
            self._normal_fg = fg_color
        if hover_color:
            self.hover_color = hover_color
            self._normal_hover = hover_color
        if canvas_bg:
            self.configure(bg=canvas_bg)

        if not self.enabled:
            # Re-apply disabled palette after theme updates.
            self.set_enabled(False)

class StatusCard(tk.Frame):
    def __init__(self, parent, title, value, icon="ℹ️", color=None):
        if color is None:
            color = COLORS["success"]
        super().__init__(parent, bg=COLORS["surface"], padx=15, pady=15)
        self.config(highlightbackground=COLORS["border"], highlightthickness=1)
        self.title_lbl = tk.Label(self, text=title, bg=COLORS["surface"], fg=COLORS["sub_text"], font=("맑은 고딕", 9))
        self.title_lbl.pack(anchor="w")
        self.value_lbl = tk.Label(self, text=f"{icon} {value}", bg=COLORS["surface"], fg=color, font=("맑은 고딕", 11, "bold"))
        self.value_lbl.pack(anchor="w", pady=(5, 0))
    def update_status(self, text, color=None):
        self.value_lbl.config(text=text)
        if color: self.value_lbl.config(fg=color)

    def update_theme(self):
        self.config(bg=COLORS["surface"], highlightbackground=COLORS["border"])
        self.title_lbl.config(bg=COLORS["surface"], fg=COLORS["sub_text"])
        self.value_lbl.config(bg=COLORS["surface"])


# ═══════════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk, minimized=False):
        self.root = root
        self._setup_hidpi()
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        self.settings.theme = apply_theme(self.settings.theme, self.logger)
        self.pattern_config = PatternConfig(PATTERNS_FILE, self.logger)
        
        # Use event-driven engine
        self.ad_blocker = EventDrivenAdBlocker(self.logger, self.pattern_config)
        self.adfit_blocker = AdFitBlocker(self.logger, update_interval_sec=self.settings.adfit_update_interval_sec)
        self.hosts_mgr = HostsManager(self.logger)
        self.tray = TrayManager(self)
        
        # Running flag for graceful thread shutdown
        self._running = True
        self._log_buffer: deque[str] = deque(maxlen=500)
        self._log_buffer_lock = threading.Lock()
        self._last_status_snapshot: Optional[Tuple[bool, bool, int, int, str]] = None
        
        self._setup_ui()
        self._apply_theme(self.settings.theme)
        self._update_realtime_state()
        self._update_admin_ui()
        self.tray.setup(); self.tray.start()
        
        if self.settings.realtime_protection:
            if self.settings.hide_layout:
                self.ad_blocker.start()
            if self.settings.block_adfit:
                self.adfit_blocker.start()
        
        self._start_monitor()
        self._start_log_consumer()
        self.logger.info(f"🚀 KakaoTalk AdBlocker Pro v{VERSION} started (Event-Driven)")
    
    def _setup_hidpi(self):
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except: pass
    
    def _setup_ui(self):
        self.root.title(APP_NAME)
        self.root.geometry("520x720")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Header
        self.header = tk.Frame(self.root, bg=COLORS["primary"], height=80)
        self.header.pack(fill="x"); self.header.pack_propagate(False)
        self.icon_frame = tk.Frame(self.header, bg=COLORS["primary"])
        self.icon_frame.pack(side="left", padx=20)
        self.icon_label = tk.Label(self.icon_frame, text="🛡️", bg=COLORS["primary"], font=("Segoe UI Emoji", 24))
        self.icon_label.pack()
        
        self.title_f = tk.Frame(self.header, bg=COLORS["primary"])
        self.title_f.pack(side="left", fill="y", pady=18)
        self.title_label = tk.Label(self.title_f, text=APP_NAME, bg=COLORS["primary"], fg=COLORS["on_primary"], font=FONTS["header"])
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(self.title_f, text=f"v{VERSION} | Event-Driven Engine ⚡", bg=COLORS["primary"], fg=COLORS["on_primary_sub"], font=("맑은 고딕", 9))
        self.subtitle_label.pack(anchor="w")

        # Scrollable content area (prevents UI clipping on high-DPI / small screens)
        self.body = tk.Frame(self.root, bg=COLORS["bg"])
        self.body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.body, bg=COLORS["bg"], highlightthickness=0, bd=0)
        self.v_scroll = tk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.v_scroll.pack(side="right", fill="y")

        self.content = tk.Frame(self.canvas, bg=COLORS["bg"], padx=22, pady=18)
        self._content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Dashboard
        self.section_status = tk.Label(self.content, text="상태", bg=COLORS["bg"], fg=COLORS["text"], font=FONTS["section"])
        self.section_status.pack(anchor="w", pady=(0, 6))
        self.dash = tk.Frame(self.content, bg=COLORS["bg"])
        self.dash.pack(fill="x", pady=(0, 14))
        self.card_engine = StatusCard(self.dash, "차단 엔진", "⚡ 이벤트 모드", color=COLORS["success"])
        self.card_engine.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.card_proc = StatusCard(self.dash, "카카오톡", "💤 감지 안됨", color=COLORS["sub_text"])
        self.card_proc.pack(side="left", fill="x", expand=True)
        
        # Stats card
        self.stats_f = tk.Frame(self.content, bg=COLORS["bg"])
        self.stats_f.pack(fill="x", pady=(0, 16))
        self.card_stats = StatusCard(self.stats_f, "통계", "🚫 0개 광고 차단", color=COLORS["success"])
        self.card_stats.pack(fill="x")
        
        # Optimize button
        self.btn_row = tk.Frame(self.content, bg=COLORS["bg"])
        self.section_actions = tk.Label(self.content, text="빠른 작업", bg=COLORS["bg"], fg=COLORS["text"], font=FONTS["section"])
        self.section_actions.pack(anchor="w", pady=(0, 6))
        self.btn_row.pack(fill="x", pady=4)
        self.btn_opt = ModernButton(self.btn_row, "✨ 스마트 최적화", self._optimize, width=228, height=48)
        self.btn_opt.pack(side="left")
        self.btn_refresh = ModernButton(self.btn_row, "🔄 빠른 새로고침", self._refresh_scan, width=228, height=48, bg_color=COLORS["surface"])
        self.btn_refresh.pack(side="right")
        self.desc_label = tk.Label(
            self.content,
            text="스마트 최적화: DNS 초기화 + 카카오톡 재시작 | 새로고침: 재시작 없이 즉시 적용 | Hosts 복구: 차단 해제 + DNS 초기화",
            bg=COLORS["bg"],
            fg=COLORS["sub_text"],
            font=("맑은 고딕", 8),
            wraplength=470,
            justify="left"
        )
        self.desc_label.pack(pady=(4, 8))

        # Admin-related quick actions
        self.btn_row2 = tk.Frame(self.content, bg=COLORS["bg"])
        self.btn_row2.pack(fill="x", pady=(0, 4))
        self.btn_run_admin = ModernButton(self.btn_row2, "🔐 관리자 권한으로 다시 실행", self._run_as_admin, width=228, height=40, bg_color=COLORS["surface"])
        self.btn_run_admin.pack(side="left")
        self.btn_hosts_restore = ModernButton(self.btn_row2, "🧯 Hosts 복구(차단 해제)", self._restore_hosts, width=228, height=40, bg_color=COLORS["surface"])
        self.btn_hosts_restore.pack(side="right")

        self.admin_hint = tk.Label(
            self.content,
            text="",
            bg=COLORS["bg"],
            fg=COLORS["sub_text"],
            font=("맑은 고딕", 8),
            wraplength=470,
            justify="left"
        )
        self.admin_hint.pack(pady=(0, 14))
        
        # Controls
        self.ctrl = tk.LabelFrame(self.content, text="설정", bg=COLORS["bg"], font=FONTS["title"], padx=15, pady=10)
        self.ctrl.pack(fill="x", pady=5)
        
        self.v_auto = tk.BooleanVar(value=StartupManager.is_enabled())
        self.v_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.v_realtime = tk.BooleanVar(value=self.settings.realtime_protection)
        self.v_hide = tk.BooleanVar(value=self.settings.hide_layout)
        self.v_adfit = tk.BooleanVar(value=self.settings.block_adfit)
        self.v_theme = tk.StringVar(value=self.settings.theme)
        chk = {"bg": COLORS["bg"], "activebackground": COLORS["bg"], "font": FONTS["body"], "pady": 2}
        
        self.chk_auto = tk.Checkbutton(self.ctrl, text="윈도우 시작 시 자동 실행", variable=self.v_auto, command=self._save, **chk)
        self.chk_auto.pack(anchor="w")
        self.chk_tray = tk.Checkbutton(self.ctrl, text="닫을 때 트레이로 최소화", variable=self.v_tray, command=self._save, **chk)
        self.chk_tray.pack(anchor="w")
        self.chk_realtime = tk.Checkbutton(self.ctrl, text="실시간 보호", variable=self.v_realtime, command=self._save, **chk)
        self.chk_realtime.pack(anchor="w")
        self.chk_hide = tk.Checkbutton(self.ctrl, text="광고 레이아웃 자동 제거 (이벤트 기반)", variable=self.v_hide, command=self._save, **chk)
        self.chk_hide.pack(anchor="w")
        self.chk_adfit = tk.Checkbutton(self.ctrl, text="팝업 광고 차단 (AdFit 레지스트리)", variable=self.v_adfit, command=self._save, **chk)
        self.chk_adfit.pack(anchor="w")

        self.theme_row = tk.Frame(self.ctrl, bg=COLORS["bg"])
        self.theme_row.pack(fill="x", pady=(6, 0))
        self.theme_label = tk.Label(self.theme_row, text="테마", bg=COLORS["bg"], font=FONTS["body"])
        self.theme_label.pack(side="left")
        self.theme_combo = ttk.Combobox(self.theme_row, textvariable=self.v_theme, values=list(THEMES.keys()),
                                        state="readonly", width=10)
        self.theme_combo.pack(side="left", padx=(8, 0))
        self.theme_combo.bind("<<ComboboxSelected>>", lambda _e: self._save())
        self.theme_hint = tk.Label(self.theme_row, text="즉시 적용", bg=COLORS["bg"], fg=COLORS["sub_text"], font=("맑은 고딕", 8))
        self.theme_hint.pack(side="left", padx=(8, 0))
        
        # Log
        self.log_f = tk.LabelFrame(self.content, text="실시간 로그", bg=COLORS["bg"], font=FONTS["title"], padx=5, pady=5)
        self.log_f.pack(fill="both", expand=True, pady=5)
        self.log_controls = tk.Frame(self.log_f, bg=COLORS["bg"])
        self.log_controls.pack(fill="x", padx=4, pady=(0, 4))
        self.btn_clear_log = ModernButton(self.log_controls, "🧹 로그 지우기", self._clear_log, width=110, height=26, bg_color=COLORS["surface"])
        self.btn_clear_log.pack(side="right")
        self.log_widget = scrolledtext.ScrolledText(self.log_f, height=5, font=FONTS["log"], state='disabled', bg=COLORS["surface"])
        self.log_widget.pack(fill="both", expand=True)
        
        # Footer
        self.footer = tk.Frame(self.content, bg=COLORS["bg"])
        self.footer.pack(fill="x", side="bottom")
        self.btn_logs = ModernButton(self.footer, "📂 폴더", lambda: os.startfile(APPDATA_DIR), 80, 28, COLORS["surface"])
        self.btn_logs.pack(side="left")
        self.btn_patterns = ModernButton(self.footer, "⚙️ 패턴", lambda: os.startfile(PATTERNS_FILE) if os.path.exists(PATTERNS_FILE) else None, 80, 28, COLORS["surface"])
        self.btn_patterns.pack(side="left", padx=5)
        self.btn_dump = ModernButton(self.footer, "🧪 덤프", self._dump_tree, 80, 28, COLORS["surface"])
        self.btn_dump.pack(side="left")
        self.btn_domains = ModernButton(self.footer, "📝 도메인", lambda: os.startfile(DOMAINS_FILE) if os.path.exists(DOMAINS_FILE) else None, 80, 28, COLORS["surface"])
        self.btn_domains.pack(side="right")
    
    def _log(self, msg):
        self.log_widget.config(state='normal')
        self.log_widget.insert('end', f"{msg}\n")
        self.log_widget.see('end')
        lines = int(self.log_widget.index('end-1c').split('.')[0])
        if lines > 150: self.log_widget.delete('1.0', '50.0')
        self.log_widget.config(state='disabled')

    def _clear_log(self):
        self.log_widget.config(state='normal')
        self.log_widget.delete('1.0', 'end')
        self.log_widget.config(state='disabled')

    def _is_descendant(self, widget, ancestor) -> bool:
        current = widget
        while current:
            if current == ancestor:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_mousewheel(self, event):
        if not getattr(self, "canvas", None):
            return
        if not self._is_descendant(event.widget, self.content):
            return
        if getattr(self, "log_widget", None) and self._is_descendant(event.widget, self.log_widget):
            return
        if self.canvas.winfo_height() >= self.content.winfo_height():
            return
        delta = -1 * int(event.delta / 120)
        self.canvas.yview_scroll(delta, "units")

    def _on_content_configure(self, _event=None):
        if getattr(self, "canvas", None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        if getattr(self, "canvas", None):
            self.canvas.itemconfigure(self._content_window, width=event.width)
    
    def _start_log_consumer(self):
        flush_ms = max(int(getattr(self.settings, "ui_batch_log_interval_ms", 100)), 30)

        def ingest_loop():
            while self._running:
                try:
                    msg = self.log_queue.get(timeout=0.2)
                    with self._log_buffer_lock:
                        self._log_buffer.append(msg)
                except queue.Empty:
                    continue

        def flush_tick():
            if not self._running:
                return
            batch: List[str] = []
            with self._log_buffer_lock:
                while self._log_buffer and len(batch) < 100:
                    batch.append(self._log_buffer.popleft())
            for msg in batch:
                self._log(msg)
            self.root.after(flush_ms, flush_tick)

        threading.Thread(target=ingest_loop, daemon=True).start()
        self.root.after(flush_ms, flush_tick)
    
    def _start_monitor(self):
        interval_sec = max(float(getattr(self.settings, "ui_status_interval_ms", 2000)) / 1000.0, 0.5)

        def loop():
            prev_payload: Optional[Tuple[bool, bool, int, int, str]] = None
            while self._running:
                try:
                    is_run = SystemManager.is_process_running("KakaoTalk")
                    stats = self.ad_blocker.stats
                    if self.pattern_config.uia_enabled:
                        uia_label = "🧩 UIA ON" if PYWINAUTO_AVAILABLE else "🧩 UIA (미설치)"
                    else:
                        uia_label = "🧩 UIA OFF"
                    payload = (
                        bool(is_run),
                        bool(self.settings.realtime_protection),
                        int(stats.get("ads_hidden", 0)),
                        int(stats.get("events_received", 0)),
                        uia_label,
                    )
                    if self._running and payload != prev_payload:
                        prev_payload = payload
                        self.root.after(0, self._update_status, is_run, stats)
                except Exception:
                    pass
                time.sleep(interval_sec)
        threading.Thread(target=loop, daemon=True).start()
    
    def _update_status(self, is_run, stats):
        if self.pattern_config.uia_enabled:
            uia_label = "🧩 UIA ON" if PYWINAUTO_AVAILABLE else "🧩 UIA (미설치)"
        else:
            uia_label = "🧩 UIA OFF"
        snapshot = (
            bool(is_run),
            bool(self.settings.realtime_protection),
            int(stats.get('ads_hidden', 0)),
            int(stats.get('events_received', 0)),
            uia_label,
        )
        if snapshot == self._last_status_snapshot:
            return
        self._last_status_snapshot = snapshot
        if is_run:
            self.card_proc.update_status("✅ 실행 중", COLORS["success"])
        else:
            self.card_proc.update_status("💤 종료됨", COLORS["sub_text"])
        if not self.settings.realtime_protection:
            self.card_engine.update_status("⏸️ 일시 중지", COLORS["warning"])
        elif self.ad_blocker.active:
            self.card_engine.update_status("⚡ 이벤트 모드", COLORS["success"])
        else:
            self.card_engine.update_status("⏳ 대기 중", COLORS["sub_text"])
        self.card_stats.update_status(
            f"🚫 {stats.get('ads_hidden', 0)}개 광고 차단 | 📊 {stats.get('events_received', 0)} 이벤트 | {uia_label}",
            COLORS["success"]
        )
    
    def _refresh_scan(self):
        """Force immediate scan without restarting KakaoTalk."""
        self.ad_blocker.force_scan()

    def _update_admin_ui(self):
        is_admin = SystemManager.is_admin()
        if getattr(self, "admin_hint", None):
            if is_admin:
                self.admin_hint.config(text="관리자 권한: 활성화됨 (Hosts/DNS 기능 사용 가능)")
            else:
                self.admin_hint.config(text="관리자 권한: 비활성화됨 (Hosts/DNS 기능은 '관리자 권한으로 다시 실행'이 필요)")

        if getattr(self, "btn_opt", None):
            self.btn_opt.set_enabled(is_admin)
        if getattr(self, "btn_hosts_restore", None):
            self.btn_hosts_restore.set_enabled(is_admin)

        if getattr(self, "btn_run_admin", None):
            if is_admin:
                self.btn_run_admin.itemconfig(self.btn_run_admin.label, text="🔐 관리자 권한 실행 중")
                self.btn_run_admin.set_enabled(False)
            else:
                self.btn_run_admin.itemconfig(self.btn_run_admin.label, text="🔐 관리자 권한으로 다시 실행")
                self.btn_run_admin.set_enabled(True)

    def _run_as_admin(self):
        if SystemManager.is_admin():
            messagebox.showinfo("정보", "이미 관리자 권한으로 실행 중입니다.")
            return
        if messagebox.askyesno("관리자 권한", "관리자 권한으로 다시 실행할까요? (UAC 창이 표시될 수 있습니다)"):
            SystemManager.run_as_admin()

    def _restore_hosts(self):
        if not SystemManager.is_admin():
            messagebox.showerror("오류", "관리자 권한이 필요합니다.")
            return
        if not messagebox.askyesno("Hosts 복구", "hosts 파일에서 KakaoTalk AdBlock 블록을 제거하고 DNS 캐시를 초기화할까요?"):
            return
        ok = self.hosts_mgr.unblock()
        if ok:
            SystemManager.flush_dns()
            messagebox.showinfo("완료", "Hosts 복구가 완료되었습니다.")
        else:
            messagebox.showwarning("주의", "Hosts 복구에 실패했습니다. 로그를 확인하세요.")

    def _dump_tree(self):
        """Dump KakaoTalk window subtree snapshot for diagnostics (JSON)."""
        try:
            path = self.ad_blocker.dump_window_tree()
            if path:
                messagebox.showinfo("덤프 완료", f"윈도우 트리 덤프가 생성되었습니다.\n{path}")
            else:
                messagebox.showwarning("덤프 실패", "카카오톡을 찾지 못했습니다. (실행 중인지 확인)")
        except Exception as e:
            messagebox.showerror("덤프 오류", f"덤프에 실패했습니다: {e}")
    
    def _optimize(self):
        if not SystemManager.is_admin():
            messagebox.showerror("오류", "관리자 권한이 필요합니다."); return
        self.logger.info("Starting smart optimization...")
        domains = DEFAULT_AD_DOMAINS
        if os.path.exists(DOMAINS_FILE):
            try:
                with open(DOMAINS_FILE, 'r', encoding='utf-8') as f:
                    custom = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                    if custom: domains = custom
            except: pass
        self.hosts_mgr.block(domains)
        SystemManager.flush_dns()
        self.logger.info("DNS cache flushed")
        if SystemManager.restart_process("kakaotalk.exe"):
            self.logger.info("KakaoTalk restarted")
            messagebox.showinfo("완료", "스마트 최적화가 완료되었습니다.")
        else:
            messagebox.showwarning("주의", "카카오톡 재시작에 실패했습니다.")
    
    def _save(self):
        self.settings.auto_start = self.v_auto.get()
        self.settings.minimize_to_tray = self.v_tray.get()
        self.settings.realtime_protection = self.v_realtime.get()
        self.settings.hide_layout = self.v_hide.get()
        self.settings.block_adfit = self.v_adfit.get()
        self.settings.ui_batch_log_interval_ms = max(int(getattr(self.settings, "ui_batch_log_interval_ms", 100)), 30)
        self.settings.ui_status_interval_ms = max(int(getattr(self.settings, "ui_status_interval_ms", 2000)), 500)
        theme = (self.v_theme.get() or "light").lower()
        if theme not in THEMES:
            theme = "light"
            self.v_theme.set(theme)
        if theme != self.settings.theme:
            self._apply_theme(theme)
        self.settings.save()
        StartupManager.set_enabled(self.settings.auto_start)
        self._update_realtime_state()
        if not self.settings.realtime_protection:
            self.ad_blocker.stop()
            self.adfit_blocker.stop()
            return
        if self.settings.hide_layout:
            self.ad_blocker.start()
        else:
            self.ad_blocker.stop()
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        else:
            self.adfit_blocker.stop()

    def _update_realtime_state(self):
        state = "normal" if self.v_realtime.get() else "disabled"
        if getattr(self, "chk_hide", None):
            self.chk_hide.configure(state=state)
        if getattr(self, "chk_adfit", None):
            self.chk_adfit.configure(state=state)

    def _apply_theme(self, theme: str):
        theme_key = apply_theme(theme, self.logger)
        self.settings.theme = theme_key
        self.v_theme.set(theme_key)

        self.root.configure(bg=COLORS["bg"])
        for frame in (self.header, self.icon_frame, self.title_f):
            frame.configure(bg=COLORS["primary"])
        self.icon_label.configure(bg=COLORS["primary"])
        self.title_label.configure(bg=COLORS["primary"], fg=COLORS["on_primary"])
        self.subtitle_label.configure(bg=COLORS["primary"], fg=COLORS["on_primary_sub"])

        for frame in (self.body, self.content, self.dash, self.stats_f, self.btn_row, self.btn_row2, self.ctrl, self.theme_row, self.log_f, self.footer, self.log_controls):
            frame.configure(bg=COLORS["bg"])
        if getattr(self, "canvas", None):
            self.canvas.configure(bg=COLORS["bg"])
        self.ctrl.configure(fg=COLORS["text"])
        self.log_f.configure(fg=COLORS["text"])
        self.desc_label.configure(bg=COLORS["bg"], fg=COLORS["sub_text"])
        if getattr(self, "admin_hint", None):
            self.admin_hint.configure(bg=COLORS["bg"], fg=COLORS["sub_text"])
        self.section_status.configure(bg=COLORS["bg"], fg=COLORS["text"])
        self.section_actions.configure(bg=COLORS["bg"], fg=COLORS["text"])
        self.theme_label.configure(bg=COLORS["bg"], fg=COLORS["text"])
        self.theme_hint.configure(bg=COLORS["bg"], fg=COLORS["sub_text"])

        for chk in (self.chk_auto, self.chk_tray, self.chk_realtime, self.chk_hide, self.chk_adfit):
            chk.configure(bg=COLORS["bg"], activebackground=COLORS["bg"], fg=COLORS["text"], selectcolor=COLORS["bg"])

        for card in (self.card_engine, self.card_proc, self.card_stats):
            card.update_theme()

        self.btn_opt.update_colors(
            bg_color=COLORS["primary"], fg_color=COLORS["text"],
            hover_color=COLORS["primary_dark"], canvas_bg=COLORS["bg"]
        )
        self.btn_refresh.update_colors(
            bg_color=COLORS["surface"], fg_color=COLORS["text"],
            hover_color=COLORS["surface"], canvas_bg=COLORS["bg"]
        )
        for btn in (self.btn_run_admin, self.btn_hosts_restore):
            btn.update_colors(
                bg_color=COLORS["surface"], fg_color=COLORS["text"],
                hover_color=COLORS["surface"], canvas_bg=COLORS["bg"]
            )
        for btn in (self.btn_logs, self.btn_patterns, self.btn_dump, self.btn_domains):
            btn.update_colors(bg_color=COLORS["surface"], fg_color=COLORS["text"], hover_color=COLORS["surface"], canvas_bg=COLORS["bg"])

        self.btn_clear_log.update_colors(bg_color=COLORS["surface"], fg_color=COLORS["text"], hover_color=COLORS["surface"], canvas_bg=COLORS["bg"])

        self.log_widget.configure(bg=COLORS["surface"], fg=COLORS["text"], insertbackground=COLORS["text"])

        try:
            style = ttk.Style(self.root)
            style.configure(
                "TCombobox",
                fieldbackground=COLORS["surface"],
                background=COLORS["surface"],
                foreground=COLORS["text"]
            )
        except Exception:
            pass

        self.logger.info(f"Theme applied: {theme_key}")
        self._update_admin_ui()
    
    def _on_close(self):
        if self.settings.minimize_to_tray: self.hide_to_tray()
        else: self.quit_app()
    
    def hide_to_tray(self):
        self.root.withdraw()
        if self.tray.icon:
            try: self.tray.icon.notify("백그라운드에서 실행 중입니다.", APP_NAME)
            except: pass
    
    def show_window(self):
        self.root.deiconify(); self.root.lift()
    
    def quit_app(self):
        self._running = False  # Stop monitor/log consumer threads first
        self.ad_blocker.stop()
        self.adfit_blocker.stop()
        self.tray.stop()
        self.root.quit()
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    migrate_legacy_user_files()

    # Ensure user-editable config files exist under AppData.
    ensure_user_file(
        SETTINGS_FILE,
        copy_from_resource=True,
        default_text=json.dumps(AppSettings().__dict__, indent=2, ensure_ascii=False),
    )
    ensure_user_file(
        PATTERNS_FILE,
        copy_from_resource=True,
        default_text=json.dumps(PatternConfig.DEFAULT_CONFIG, indent=2, ensure_ascii=False),
    )
    ensure_user_file(
        DOMAINS_FILE,
        copy_from_resource=True,
        default_text="# 카카오톡 광고 차단 도메인 목록\n\n" + "\n".join(DEFAULT_AD_DOMAINS) + "\n",
    )

    # CLI diagnostics: dump current KakaoTalk window tree without starting GUI.
    # Usage:
    #   python "카카오톡 광고제거 v10.0.py" --dump-tree
    #   python "카카오톡 광고제거 v10.0.py" --dump-tree --dump-dir "C:\\path"
    if "--dump-tree" in sys.argv:
        dump_dir = None
        try:
            if "--dump-dir" in sys.argv:
                idx = sys.argv.index("--dump-dir")
                if idx + 1 < len(sys.argv):
                    dump_dir = sys.argv[idx + 1]
        except Exception:
            dump_dir = None

        logger, _log_queue = setup_logging()
        pattern_config = PatternConfig(PATTERNS_FILE, logger)
        engine = EventDrivenAdBlocker(logger, pattern_config)
        path = engine.dump_window_tree(out_dir=dump_dir)
        if path:
            print(path)
            return
        print("KakaoTalk not running (or root not found)")
        return
    
    root = tk.Tk()
    app = MainWindow(root, "--minimized" in sys.argv)
    if "--minimized" in sys.argv: root.withdraw()
    root.mainloop()

if __name__ == "__main__":
    main()
