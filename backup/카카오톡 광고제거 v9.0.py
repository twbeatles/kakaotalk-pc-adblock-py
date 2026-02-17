# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v9.0 (Refactored Architecture)
=======================================================
- v9.0 Changes:
    - External pattern configuration (ad_patterns.json)
    - PatternMatcher class for flexible ad detection
    - Enhanced error handling with retry logic
    - Improved logging with context
    - Thread-safe processed window tracking
    - Graceful degradation on config errors
"""

import os
import sys
import ctypes
import ctypes.wintypes
import json
import threading
import time
import logging
import queue
import platform
import subprocess
import winreg
from datetime import datetime
from typing import Optional, List, Dict, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import re

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


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & Configuration
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "9.0.0"
APP_NAME = "KakaoTalk AdBlocker Pro"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "adblock_settings.json")
DOMAINS_FILE = os.path.join(BASE_DIR, "blocked_domains.txt")
PATTERNS_FILE = os.path.join(BASE_DIR, "ad_patterns.json")
LOG_FILE = os.path.join(BASE_DIR, "adblock.log")

# UI Colors (Kakao Theme)
COLORS = {
    "primary": "#FEE500",
    "primary_dark": "#FDD835",
    "bg": "#FFFFFF",
    "text": "#191919",
    "sub_text": "#757575",
    "success": "#2E7D32",
    "warning": "#FF6F00",
    "error": "#D32F2F",
    "surface": "#F8F9FA",
    "border": "#E9ECEF"
}

FONTS = {
    "header": ("맑은 고딕", 14, "bold"),
    "title": ("맑은 고딕", 11, "bold"),
    "body": ("맑은 고딕", 10),
    "log": ("Consolas", 9)
}

# Default ad domains (fallback)
DEFAULT_AD_DOMAINS = [
    "display.ad.daum.net", "analytics.ad.daum.net", "ad.daum.net",
    "alea.adam.ad.daum.net", "adam.ad.daum.net", "wat.ad.daum.net",
    "biz.ad.daum.net", "cs.ad.daum.net", "ad.mad.daum.net",
    "ams.ad.daum.net", "amsv2.daum.net",
    "ad.smart.kakao.com", "ad.kakao.com", "display.ad.kakao.com",
    "business.kakao.com", "ad.kakaocdn.net", "ad.kakaocdn.com",
    "track.tiara.kakao.com", "stat.tiara.kakao.com", "kakaoad.criteo.com"
] + [f"adimg{i}.kakaocdn.net" for i in range(1, 11)]


# ═══════════════════════════════════════════════════════════════════════════════
# Logging System
# ═══════════════════════════════════════════════════════════════════════════════
class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass  # Drop log if queue is full

def setup_logging() -> tuple:
    log_queue = queue.Queue(maxsize=200)
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        logger.handlers.clear()
    
    fmt = logging.Formatter(
        '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File Handler with rotation-like behavior
    try:
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Failed to create file handler: {e}")
    
    # Queue Handler for GUI
    qh = QueueHandler(log_queue)
    qh.setLevel(logging.INFO)
    qh.setFormatter(fmt)
    logger.addHandler(qh)
    
    return logger, log_queue


# ═══════════════════════════════════════════════════════════════════════════════
# Pattern Matching System (NEW in v9.0)
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
    """Represents a single ad detection pattern."""
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


class PatternConfig:
    """Loads and manages ad patterns from external config file."""
    
    DEFAULT_CONFIG = {
        "window_classes": {"main_window": ["EVA_Window"]},
        "title_filters": {"main_window_titles": ["카카오톡", "KakaoTalk"]},
        "ad_patterns": {"hide": [
            {"type": "text_startswith", "value": "BannerAdView"},
            {"type": "text_startswith", "value": "AdView"}
        ]},
        "resize_patterns": {"targets": [
            {"type": "text_startswith", "value": "OnlineMainView"}
        ]},
        "timing": {
            "scan_interval_active_ms": 1500,
            "scan_interval_idle_ms": 3000,
            "resize_threshold_px": 5,
            "min_view_height_px": 100
        },
        "logging": {"log_hidden_ads": True, "log_resizes": False}
    }
    
    def __init__(self, config_path: str, logger: logging.Logger):
        self.config_path = config_path
        self.logger = logger
        self.config = self._load_config()
        self.hide_patterns = self._parse_patterns(self.config.get("ad_patterns", {}).get("hide", []))
        self.resize_patterns = self._parse_patterns(self.config.get("resize_patterns", {}).get("targets", []))
    
    def _load_config(self) -> Dict:
        """Load config from file with fallback to defaults."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.logger.info(f"Loaded ad patterns from {self.config_path}")
                    return config
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
        
        self.logger.warning("Using default ad patterns")
        return self.DEFAULT_CONFIG
    
    def _parse_patterns(self, pattern_list: List[Dict]) -> List[AdPattern]:
        """Parse pattern dictionaries into AdPattern objects."""
        patterns = []
        for p in pattern_list:
            try:
                ptype = PatternType(p.get("type", "text_startswith"))
                patterns.append(AdPattern(
                    pattern_type=ptype,
                    value=p.get("value", ""),
                    description=p.get("description", "")
                ))
            except ValueError as e:
                self.logger.warning(f"Unknown pattern type: {p.get('type')} - {e}")
        return patterns
    
    @property
    def main_window_classes(self) -> List[str]:
        return self.config.get("window_classes", {}).get("main_window", ["EVA_Window"])
    
    @property
    def main_window_titles(self) -> List[str]:
        return self.config.get("title_filters", {}).get("main_window_titles", ["카카오톡", "KakaoTalk"])
    
    @property
    def scan_interval_active(self) -> float:
        return self.config.get("timing", {}).get("scan_interval_active_ms", 1500) / 1000.0
    
    @property
    def scan_interval_idle(self) -> float:
        return self.config.get("timing", {}).get("scan_interval_idle_ms", 3000) / 1000.0
    
    @property
    def resize_threshold(self) -> int:
        return self.config.get("timing", {}).get("resize_threshold_px", 5)
    
    @property
    def min_view_height(self) -> int:
        return self.config.get("timing", {}).get("min_view_height_px", 100)
    
    @property
    def log_hidden_ads(self) -> bool:
        return self.config.get("logging", {}).get("log_hidden_ads", True)


class PatternMatcher:
    """Matches window properties against configured ad patterns."""
    
    def __init__(self, config: PatternConfig):
        self.config = config
    
    def is_ad_window(self, window_text: str, window_class: str) -> bool:
        """Check if window matches any hide pattern."""
        return self._matches_any(window_text, window_class, self.config.hide_patterns)
    
    def is_resize_target(self, window_text: str, window_class: str) -> bool:
        """Check if window matches any resize pattern."""
        return self._matches_any(window_text, window_class, self.config.resize_patterns)
    
    def is_main_window(self, window_class: str, window_title: str) -> bool:
        """Check if this is a KakaoTalk main window."""
        class_match = window_class in self.config.main_window_classes
        title_match = any(t in window_title for t in self.config.main_window_titles)
        return class_match and title_match
    
    def _matches_any(self, text: str, cls: str, patterns: List[AdPattern]) -> bool:
        """Check if text/class matches any pattern in the list."""
        for p in patterns:
            if self._matches_pattern(text, cls, p):
                return True
        return False
    
    def _matches_pattern(self, text: str, cls: str, pattern: AdPattern) -> bool:
        """Check if text/class matches a single pattern."""
        match pattern.pattern_type:
            case PatternType.TEXT_STARTSWITH:
                return text.startswith(pattern.value)
            case PatternType.TEXT_CONTAINS:
                return pattern.value in text
            case PatternType.TEXT_EQUALS:
                return text == pattern.value
            case PatternType.TEXT_REGEX:
                if pattern.compiled_regex:
                    return bool(pattern.compiled_regex.search(text))
                return False
            case PatternType.CLASS_EQUALS:
                return cls == pattern.value
            case PatternType.CLASS_STARTSWITH:
                return cls.startswith(pattern.value)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Settings Management
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class AppSettings:
    auto_start: bool = False
    minimize_to_tray: bool = True
    hide_layout: bool = True
    block_adfit: bool = True
    realtime_protection: bool = True
    
    @classmethod
    def load(cls):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            pass
        return cls()
    
    def save(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Wrapper
# ═══════════════════════════════════════════════════════════════════════════════
class User32:
    """Windows User32 API wrapper with error handling."""
    lib = ctypes.windll.user32 if platform.system() == "Windows" else None
    
    @staticmethod
    def get_pid(hwnd: int) -> int:
        if not User32.lib:
            return 0
        pid = ctypes.c_ulong()
        User32.lib.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    
    @staticmethod
    def get_class(hwnd: int) -> str:
        if not User32.lib:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        User32.lib.GetClassNameW(hwnd, buf, 256)
        return buf.value
    
    @staticmethod
    def get_text(hwnd: int) -> str:
        if not User32.lib:
            return ""
        length = User32.lib.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        User32.lib.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    
    @staticmethod
    def is_visible(hwnd: int) -> bool:
        if not User32.lib:
            return False
        return bool(User32.lib.IsWindowVisible(hwnd))
    
    @staticmethod
    def show_window(hwnd: int, cmd: int) -> bool:
        if not User32.lib:
            return False
        return bool(User32.lib.ShowWindow(hwnd, cmd))
    
    @staticmethod
    def set_window_pos(hwnd: int, x: int, y: int, w: int, h: int, flags: int) -> bool:
        if not User32.lib:
            return False
        return bool(User32.lib.SetWindowPos(hwnd, 0, x, y, w, h, flags))
    
    @staticmethod
    def get_client_rect(hwnd: int) -> Optional[ctypes.wintypes.RECT]:
        if not User32.lib:
            return None
        rect = ctypes.wintypes.RECT()
        if User32.lib.GetClientRect(hwnd, ctypes.byref(rect)):
            return rect
        return None
    
    @staticmethod
    def get_window_rect(hwnd: int) -> Optional[ctypes.wintypes.RECT]:
        if not User32.lib:
            return None
        rect = ctypes.wintypes.RECT()
        if User32.lib.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect
        return None
    
    @staticmethod
    def screen_to_client(hwnd: int, x: int, y: int) -> tuple:
        if not User32.lib:
            return (0, 0)
        pt = ctypes.wintypes.POINT(x, y)
        User32.lib.ScreenToClient(hwnd, ctypes.byref(pt))
        return (pt.x, pt.y)


# ═══════════════════════════════════════════════════════════════════════════════
# Ad Layout Hider (Refactored with Pattern Matching)
# ═══════════════════════════════════════════════════════════════════════════════
class AdLayoutHider:
    """Windows API-based ad hiding with pattern matching support."""
    
    SW_HIDE = 0
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    
    def __init__(self, logger: logging.Logger, pattern_config: PatternConfig):
        self.logger = logger.getChild("LayoutHider")
        self.config = pattern_config
        self.matcher = PatternMatcher(pattern_config)
        self.active = False
        self.thread: Optional[threading.Thread] = None
        self.user32 = ctypes.windll.user32 if platform.system() == "Windows" else None
        self.kakao_pid: Optional[int] = None
        
        # Thread-safe tracking of processed windows
        self._lock = threading.RLock()
        self._hidden_hwnds: Set[int] = set()
        self._stats = {"hidden": 0, "resized": 0, "errors": 0}
    
    def start(self):
        if not self.user32 or self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="AdLayoutHider")
        self.thread.start()
        self.logger.info("Layout optimizer started (Pattern-based)")
    
    def stop(self):
        self.active = False
        self.logger.info(f"Layout optimizer stopped. Stats: {self._stats}")
    
    def _loop(self):
        while self.active:
            try:
                self._scan_and_fix()
                interval = self.config.scan_interval_active if self.kakao_pid else self.config.scan_interval_idle
                time.sleep(interval)
            except Exception as e:
                self.logger.error(f"Scan error: {e}", exc_info=True)
                self._stats["errors"] += 1
                time.sleep(self.config.scan_interval_idle)
    
    def _get_kakao_pid(self) -> Optional[int]:
        """Find KakaoTalk process ID with fallback methods."""
        # Method 1: psutil
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name', 'pid']):
                    if 'kakaotalk.exe' in (p.info['name'] or '').lower():
                        return p.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Method 2: tasklist fallback
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq kakaotalk.exe', '/FO', 'CSV', '/NH'],
                capture_output=True, text=True, creationflags=0x08000000, timeout=5
            )
            line = result.stdout.strip()
            if line and 'kakaotalk.exe' in line.lower():
                parts = line.split(',')
                if len(parts) >= 2:
                    return int(parts[1].replace('"', ''))
        except Exception:
            pass
        return None
    
    def _scan_and_fix(self):
        self.kakao_pid = self._get_kakao_pid()
        
        def enum_callback(hwnd, _):
            try:
                # PID filtering
                if self.kakao_pid and User32.get_pid(hwnd) != self.kakao_pid:
                    return True
                
                cls = User32.get_class(hwnd)
                title = User32.get_text(hwnd)
                
                # Check if this is a KakaoTalk main window
                if self.matcher.is_main_window(cls, title):
                    self._process_main_window(hwnd)
            except Exception as e:
                self.logger.debug(f"Error processing window {hwnd}: {e}")
            return True
        
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumWindows(WNDPROC(enum_callback), 0)
    
    def _process_main_window(self, parent_hwnd: int):
        """Process child windows of KakaoTalk main window."""
        
        def child_callback(hwnd, _):
            try:
                text = User32.get_text(hwnd)
                cls = User32.get_class(hwnd)
                
                # Check for ad windows
                if self.matcher.is_ad_window(text, cls):
                    self._hide_ad(hwnd, text)
                
                # Check for resize targets
                elif self.matcher.is_resize_target(text, cls):
                    self._resize_view(hwnd, parent_hwnd)
            except Exception as e:
                self.logger.debug(f"Error processing child {hwnd}: {e}")
            return True
        
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumChildWindows(parent_hwnd, WNDPROC(child_callback), 0)
    
    def _hide_ad(self, hwnd: int, text: str):
        """Hide an ad window if not already hidden."""
        with self._lock:
            if hwnd in self._hidden_hwnds:
                return
            
            if User32.is_visible(hwnd):
                if User32.show_window(hwnd, self.SW_HIDE):
                    self._hidden_hwnds.add(hwnd)
                    self._stats["hidden"] += 1
                    if self.config.log_hidden_ads:
                        self.logger.info(f"Hidden ad: {text[:50]}")
    
    def _resize_view(self, hwnd: int, parent_hwnd: int):
        """Resize main view to fill space left by hidden ads."""
        try:
            # Get parent client area height
            parent_rect = User32.get_client_rect(parent_hwnd)
            if not parent_rect:
                return
            parent_height = parent_rect.bottom - parent_rect.top
            
            # Get child window rect
            child_rect = User32.get_window_rect(hwnd)
            if not child_rect:
                return
            
            # Convert to parent client coordinates
            client_x, client_y = User32.screen_to_client(parent_hwnd, child_rect.left, child_rect.top)
            
            # Calculate target height
            target_height = parent_height - client_y
            
            if target_height < self.config.min_view_height:
                return
            
            current_height = child_rect.bottom - child_rect.top
            current_width = child_rect.right - child_rect.left
            
            # Resize if difference is significant
            if abs(target_height - current_height) > self.config.resize_threshold:
                flags = self.SWP_NOMOVE | self.SWP_NOZORDER | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED
                if User32.set_window_pos(hwnd, 0, 0, current_width, target_height, flags):
                    self._stats["resized"] += 1
        except Exception as e:
            self.logger.debug(f"Resize error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# AdFit Registry Blocker
# ═══════════════════════════════════════════════════════════════════════════════
class AdFitBlocker:
    """Blocks AdFit popup ads via registry manipulation."""
    KEY = r"SOFTWARE\Kakao\AdFit"
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger.getChild("AdFitBlocker")
        self.active = False
    
    def start(self):
        if self.active:
            return
        self.active = True
        threading.Thread(target=self._loop, daemon=True, name="AdFitBlocker").start()
        self.logger.info("AdFit blocker started")
    
    def stop(self):
        self.active = False
    
    def _loop(self):
        while self.active:
            self._update()
            time.sleep(10)
    
    def _update(self):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.KEY, 0,
                winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
            )
            idx = 0
            current_time = str(int(time.time()))
            
            while True:
                try:
                    name = winreg.EnumKey(key, idx)
                    path = f"{self.KEY}\\{name}"
                    try:
                        subkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE)
                        winreg.SetValueEx(subkey, "LUD", 0, winreg.REG_SZ, current_time)
                        winreg.CloseKey(subkey)
                    except Exception:
                        pass
                    idx += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# System Manager
# ═══════════════════════════════════════════════════════════════════════════════
class SystemManager:
    @staticmethod
    def is_admin() -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    
    @staticmethod
    def run_as_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            " ".join(f'"{a}"' for a in sys.argv), None, 1
        )
        sys.exit(0)
    
    @staticmethod
    def flush_dns() -> bool:
        try:
            subprocess.run("ipconfig /flushdns", capture_output=True, creationflags=0x08000000, timeout=10)
            return True
        except Exception:
            return False
    
    @staticmethod
    def is_process_running(name: str) -> bool:
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name']):
                    if name.lower() in (p.info['name'] or '').lower():
                        return True
            except Exception:
                pass
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {name}.exe', '/NH'],
                capture_output=True, text=True, creationflags=0x08000000, timeout=5
            )
            return name.lower() in result.stdout.lower()
        except Exception:
            return False
    
    @staticmethod
    def restart_process(name: str) -> bool:
        exe_path = None
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name', 'exe']):
                    if name.lower() in (p.info['name'] or '').lower():
                        exe_path = p.info['exe']
                        break
            except Exception:
                pass
        
        subprocess.run(['taskkill', '/f', '/im', name], capture_output=True, creationflags=0x08000000)
        time.sleep(1.5)
        
        if exe_path and os.path.exists(exe_path):
            os.startfile(exe_path)
            return True
        
        paths = [
            os.path.join(os.environ.get(k, ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe')
            for k in ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA']
        ]
        for p in paths:
            if os.path.exists(p):
                os.startfile(p)
                return True
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Hosts Manager
# ═══════════════════════════════════════════════════════════════════════════════
class HostsManager:
    PATH = r"C:\Windows\System32\drivers\etc\hosts"
    START, END = "# [KakaoTalk AdBlock Start]", "# [KakaoTalk AdBlock End]"
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger.getChild("HostsManager")
    
    def block(self, domains: List[str]) -> bool:
        try:
            with open(self.PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"Failed to read hosts file: {e}")
            return False
        
        # Remove existing block and clean up domain entries
        lines = []
        skip = False
        for line in content.splitlines():
            if self.START in line:
                skip = True
                continue
            if self.END in line:
                skip = False
                continue
            if not skip and not any(d in line and ("0.0.0.0" in line or "127.0.0.1" in line) for d in domains):
                lines.append(line)
        
        # Build new content
        new_content = "\n".join(lines).strip()
        new_content += f"\n\n{self.START}\n# Updated: {datetime.now()}\n"
        new_content += "\n".join(f"0.0.0.0 {d}" for d in domains)
        new_content += f"\n{self.END}\n"
        
        try:
            os.chmod(self.PATH, 0o777)
            with open(self.PATH, 'w', encoding='utf-8') as f:
                f.write(new_content)
            self.logger.info(f"Blocked {len(domains)} domains")
            return True
        except Exception as e:
            self.logger.error(f"Failed to write hosts file: {e}")
            return False
    
    def get_status(self, domains: List[str]) -> float:
        try:
            with open(self.PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return sum(1 for d in domains if f"0.0.0.0 {d}" in content) / len(domains) if domains else 0
        except Exception:
            return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Startup Manager
# ═══════════════════════════════════════════════════════════════════════════════
class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerPro"
    
    @staticmethod
    def is_enabled() -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, StartupManager.NAME)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False
    
    @staticmethod
    def set_enabled(enable: bool) -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                exe = sys.executable
                if exe.endswith('python.exe'):
                    path = f'"{exe}" "{os.path.abspath(sys.argv[0])}" --minimized'
                else:
                    path = f'"{exe}" --minimized'
                winreg.SetValueEx(key, StartupManager.NAME, 0, winreg.REG_SZ, path)
            else:
                try:
                    winreg.DeleteValue(key, StartupManager.NAME)
                except Exception:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Tray Manager
# ═══════════════════════════════════════════════════════════════════════════════
class TrayManager:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self.running = False
    
    def setup(self):
        if not TRAY_AVAILABLE:
            return
        self.icon = pystray.Icon(
            "KakaoTalkAdBlocker",
            self._create_icon(),
            APP_NAME,
            pystray.Menu(
                pystray.MenuItem("열기", lambda: self.app.root.after(0, self.app.show_window)),
                pystray.MenuItem("종료", lambda: self.app.root.after(0, self.app.quit_app))
            )
        )
    
    def _create_icon(self) -> Image.Image:
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Shield shape
        draw.polygon(
            [(32, 4), (60, 14), (60, 32), (32, 60), (4, 32), (4, 14)],
            fill=(254, 229, 0, 255), outline=(200, 180, 0, 255)
        )
        # Checkmark
        draw.line([(18, 32), (26, 42), (46, 20)], fill=(25, 25, 25, 255), width=5)
        return img
    
    def start(self):
        if not self.running and TRAY_AVAILABLE and self.icon:
            self.running = True
            threading.Thread(target=self.icon.run, daemon=True).start()
    
    def stop(self):
        if self.icon:
            self.icon.stop()
            self.running = False


# ═══════════════════════════════════════════════════════════════════════════════
# UI Components
# ═══════════════════════════════════════════════════════════════════════════════
class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=120, height=40,
                 bg_color=COLORS["primary"], fg_color=COLORS["text"], hover_color=COLORS["primary_dark"]):
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0)
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        
        self.rect = self._create_rounded_rect(2, 2, width - 2, height - 2, 8, fill=bg_color, outline="")
        self.label = self.create_text(width / 2, height / 2, text=text, fill=fg_color, font=("맑은 고딕", 10, "bold"))
        
        self.bind("<Enter>", lambda e: (self.itemconfig(self.rect, fill=self.hover_color), self.config(cursor="hand2")))
        self.bind("<Leave>", lambda e: (self.itemconfig(self.rect, fill=self.bg_color), self.config(cursor="")))
        self.bind("<Button-1>", lambda e: self.move(self.label, 1, 1))
        self.bind("<ButtonRelease-1>", self._on_release)
    
    def _create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
            x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
            x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1
        ]
        return self.create_polygon(points, **kwargs, smooth=True)
    
    def _on_release(self, e):
        self.move(self.label, -1, -1)
        if self.command:
            self.command()


class StatusCard(tk.Frame):
    def __init__(self, parent, title, value, icon="ℹ️", color=COLORS["success"]):
        super().__init__(parent, bg=COLORS["surface"], padx=15, pady=15)
        self.config(highlightbackground=COLORS["border"], highlightthickness=1)
        
        tk.Label(self, text=title, bg=COLORS["surface"], fg=COLORS["sub_text"],
                 font=("맑은 고딕", 9)).pack(anchor="w")
        self.value_lbl = tk.Label(self, text=f"{icon} {value}", bg=COLORS["surface"],
                                   fg=color, font=("맑은 고딕", 11, "bold"))
        self.value_lbl.pack(anchor="w", pady=(5, 0))
    
    def update_status(self, text, color=None):
        self.value_lbl.config(text=text)
        if color:
            self.value_lbl.config(fg=color)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk, minimized=False):
        self.root = root
        self._setup_hidpi()
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        
        # Load pattern configuration
        self.pattern_config = PatternConfig(PATTERNS_FILE, self.logger)
        
        # Initialize components
        self.layout_hider = AdLayoutHider(self.logger, self.pattern_config)
        self.adfit_blocker = AdFitBlocker(self.logger)
        self.hosts_mgr = HostsManager(self.logger)
        self.tray = TrayManager(self)
        
        self._setup_ui()
        self.tray.setup()
        self.tray.start()
        
        if self.settings.hide_layout:
            self.layout_hider.start()
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        
        self._start_monitor()
        self._start_log_consumer()
        
        self.logger.info(f"KakaoTalk AdBlocker Pro v{VERSION} started")
    
    def _setup_hidpi(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    
    def _setup_ui(self):
        self.root.title(APP_NAME)
        self.root.geometry("520x700")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Header
        header = tk.Frame(self.root, bg=COLORS["primary"], height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        icon_frame = tk.Frame(header, bg=COLORS["primary"])
        icon_frame.pack(side="left", padx=20)
        tk.Label(icon_frame, text="🛡️", bg=COLORS["primary"], font=("Segoe UI Emoji", 24)).pack()
        
        title_frame = tk.Frame(header, bg=COLORS["primary"])
        title_frame.pack(side="left", fill="y", pady=18)
        tk.Label(title_frame, text=APP_NAME, bg=COLORS["primary"], fg="#3A1D1D",
                 font=FONTS["header"]).pack(anchor="w")
        tk.Label(title_frame, text=f"v{VERSION} | Pattern-based Engine",
                 bg=COLORS["primary"], fg="#665500", font=("맑은 고딕", 9)).pack(anchor="w")
        
        # Content
        content = tk.Frame(self.root, bg=COLORS["bg"], padx=25, pady=20)
        content.pack(fill="both", expand=True)
        
        # Dashboard
        dash = tk.Frame(content, bg=COLORS["bg"])
        dash.pack(fill="x", pady=(0, 20))
        self.card_status = StatusCard(dash, "보호 모듈", "⚡ 작동 중")
        self.card_status.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.card_proc = StatusCard(dash, "카카오톡", "💤 감지 안됨", color=COLORS["sub_text"])
        self.card_proc.pack(side="left", fill="x", expand=True)
        
        # Smart Optimize Button
        self.btn_opt = ModernButton(content, "✨ 스마트 최적화", self._optimize, width=470, height=50)
        self.btn_opt.pack(pady=5)
        tk.Label(content, text="광고 차단 + DNS 초기화 + 프로세스 재시작",
                 bg=COLORS["bg"], fg=COLORS["sub_text"], font=("맑은 고딕", 8)).pack(pady=(2, 20))
        
        # Controls
        ctrl_frame = tk.LabelFrame(content, text="설정", bg=COLORS["bg"], font=FONTS["title"], padx=15, pady=15)
        ctrl_frame.pack(fill="x", pady=10)
        
        self.v_auto = tk.BooleanVar(value=StartupManager.is_enabled())
        self.v_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.v_hide = tk.BooleanVar(value=self.settings.hide_layout)
        self.v_adfit = tk.BooleanVar(value=self.settings.block_adfit)
        
        chk_style = {"bg": COLORS["bg"], "activebackground": COLORS["bg"], "font": FONTS["body"], "pady": 2}
        
        tk.Checkbutton(ctrl_frame, text="윈도우 시작 시 자동 실행", variable=self.v_auto,
                       command=self._save_settings, **chk_style).pack(anchor="w")
        tk.Checkbutton(ctrl_frame, text="닫을 때 트레이로 최소화", variable=self.v_tray,
                       command=self._save_settings, **chk_style).pack(anchor="w")
        tk.Checkbutton(ctrl_frame, text="광고 레이아웃 자동 제거 (패턴 기반)", variable=self.v_hide,
                       command=self._save_settings, **chk_style).pack(anchor="w")
        tk.Checkbutton(ctrl_frame, text="팝업 광고 차단 (AdFit 레지스트리)", variable=self.v_adfit,
                       command=self._save_settings, **chk_style).pack(anchor="w")
        
        # Log
        log_frame = tk.LabelFrame(content, text="실시간 로그", bg=COLORS["bg"], font=FONTS["title"], padx=5, pady=5)
        log_frame.pack(fill="both", expand=True, pady=10)
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=6, font=FONTS["log"],
                                                     state='disabled', bg="#F8F8F8")
        self.log_widget.pack(fill="both", expand=True)
        
        # Footer
        footer = tk.Frame(content, bg=COLORS["bg"])
        footer.pack(fill="x", side="bottom")
        ModernButton(footer, "📂 로그 폴더", lambda: os.startfile(BASE_DIR),
                     width=100, height=30, bg_color="#E0E0E0").pack(side="left")
        ModernButton(footer, "⚙️ 패턴 설정", lambda: os.startfile(PATTERNS_FILE) if os.path.exists(PATTERNS_FILE) else None,
                     width=100, height=30, bg_color="#E0E0E0").pack(side="left", padx=10)
        ModernButton(footer, "📝 차단 목록", lambda: os.startfile(DOMAINS_FILE) if os.path.exists(DOMAINS_FILE) else None,
                     width=100, height=30, bg_color="#E0E0E0").pack(side="right")
    
    def _log(self, msg):
        self.log_widget.config(state='normal')
        self.log_widget.insert('end', f"{msg}\n")
        self.log_widget.see('end')
        # Limit log size
        lines = int(self.log_widget.index('end-1c').split('.')[0])
        if lines > 200:
            self.log_widget.delete('1.0', '50.0')
        self.log_widget.config(state='disabled')
    
    def _start_log_consumer(self):
        def loop():
            while True:
                try:
                    msg = self.log_queue.get(timeout=0.5)
                    self.root.after(0, self._log, msg)
                except queue.Empty:
                    pass
        threading.Thread(target=loop, daemon=True, name="LogConsumer").start()
    
    def _start_monitor(self):
        def loop():
            while True:
                is_running = SystemManager.is_process_running("KakaoTalk")
                self.root.after(0, self._update_status, is_running)
                time.sleep(2)
        threading.Thread(target=loop, daemon=True, name="ProcessMonitor").start()
    
    def _update_status(self, is_running):
        if is_running:
            self.card_proc.update_status("✅ 실행 중", COLORS["success"])
        else:
            self.card_proc.update_status("💤 종료됨", COLORS["sub_text"])
    
    def _optimize(self):
        if not SystemManager.is_admin():
            messagebox.showerror("오류", "관리자 권한이 필요합니다.")
            return
        
        self.logger.info("Starting smart optimization...")
        
        # 1. Block domains
        domains = DEFAULT_AD_DOMAINS
        if os.path.exists(DOMAINS_FILE):
            try:
                with open(DOMAINS_FILE, 'r', encoding='utf-8') as f:
                    custom_domains = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                    if custom_domains:
                        domains = custom_domains
            except Exception:
                pass
        
        self.hosts_mgr.block(domains)
        
        # 2. Flush DNS
        SystemManager.flush_dns()
        self.logger.info("DNS cache flushed")
        
        # 3. Restart KakaoTalk
        if SystemManager.restart_process("kakaotalk.exe"):
            self.logger.info("KakaoTalk restarted successfully")
            messagebox.showinfo("완료", "스마트 최적화가 완료되었습니다.")
        else:
            self.logger.warning("KakaoTalk not found or restart failed")
            messagebox.showwarning("주의", "카카오톡 재시작에 실패했습니다.\n수동으로 실행해주세요.")
    
    def _save_settings(self):
        self.settings.auto_start = self.v_auto.get()
        self.settings.minimize_to_tray = self.v_tray.get()
        self.settings.hide_layout = self.v_hide.get()
        self.settings.block_adfit = self.v_adfit.get()
        self.settings.save()
        
        StartupManager.set_enabled(self.settings.auto_start)
        
        if self.settings.hide_layout:
            self.layout_hider.start()
        else:
            self.layout_hider.stop()
        
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        else:
            self.adfit_blocker.stop()
    
    def _on_close(self):
        if self.settings.minimize_to_tray:
            self.hide_to_tray()
        else:
            self.quit_app()
    
    def hide_to_tray(self):
        self.root.withdraw()
        if self.settings.minimize_to_tray and self.tray.icon:
            try:
                self.tray.icon.notify("백그라운드에서 실행 중입니다.", APP_NAME)
            except Exception:
                pass
    
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
    
    def quit_app(self):
        self.layout_hider.stop()
        self.adfit_blocker.stop()
        self.tray.stop()
        self.root.quit()
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    # HiDPI Support
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    
    # Create patterns file if not exists
    if not os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, 'w', encoding='utf-8') as f:
            json.dump(PatternConfig.DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    
    # Create domains file if not exists
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
            f.write("# 카카오톡 광고 차단 도메인 목록\n")
            f.write("# Generated by KakaoTalk AdBlocker Pro\n\n")
            f.write("\n".join(DEFAULT_AD_DOMAINS))
    
    root = tk.Tk()
    start_minimized = "--minimized" in sys.argv
    app = MainWindow(root, minimized=start_minimized)
    
    if start_minimized:
        root.withdraw()
    
    root.mainloop()


if __name__ == "__main__":
    main()
