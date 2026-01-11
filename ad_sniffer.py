# -*- coding: utf-8 -*-
"""
KakaoTalk Ad Layout Sniffer v10.0
=================================
Advanced window hierarchy analysis and ad pattern detection engine
for KakaoTalk PC advertisement removal.

Features:
- Recursive window tree analysis
- Multi-strategy ad detection (class, size, position heuristics)
- Real-time monitoring with caching
- Popup ad interception
"""

import ctypes
import ctypes.wintypes
import platform
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Dict, Set, Tuple
from enum import Enum, auto
from collections import OrderedDict
import struct

# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Constants
# ═══════════════════════════════════════════════════════════════════════════════
SW_HIDE = 0
SW_SHOW = 5
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOSIZE = 0x0001
WM_CLOSE = 0x0010

GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════
class AdType(Enum):
    """광고 유형 분류"""
    UNKNOWN = auto()
    BANNER_TOP = auto()      # 상단 배너 광고
    BANNER_BOTTOM = auto()   # 하단 배너 광고
    POPUP = auto()           # 팝업 광고
    SIDEBAR = auto()         # 사이드바 광고
    EMBEDDED = auto()        # 임베디드 웹뷰 광고


@dataclass
class WindowInfo:
    """윈도우 정보 구조체"""
    hwnd: int
    class_name: str
    title: str
    x: int
    y: int
    width: int
    height: int
    style: int = 0
    ex_style: int = 0
    is_visible: bool = True
    parent_hwnd: Optional[int] = None
    children: List['WindowInfo'] = field(default_factory=list)
    
    @property
    def is_popup(self) -> bool:
        return bool(self.style & WS_POPUP)
    
    @property
    def is_topmost(self) -> bool:
        return bool(self.ex_style & WS_EX_TOPMOST)
    
    @property
    def is_toolwindow(self) -> bool:
        return bool(self.ex_style & WS_EX_TOOLWINDOW)
    
    def __hash__(self):
        return hash(self.hwnd)


@dataclass
class AdDetectionResult:
    """광고 감지 결과"""
    window: WindowInfo
    ad_type: AdType
    confidence: float  # 0.0 ~ 1.0
    reason: str
    action_taken: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Wrapper
# ═══════════════════════════════════════════════════════════════════════════════
class WinAPIWrapper:
    """향상된 Windows API 래퍼"""
    
    def __init__(self):
        self.available = platform.system() == "Windows"
        self._callback_refs = []  # Store callback references to prevent GC
        if not self.available:
            return
            
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        
        # Callback type
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )
        
        # Setup function signatures
        self.user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        self.user32.FindWindowW.restype = ctypes.c_void_p
        
        self.user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.GetWindowLongW.restype = ctypes.c_long
        
        self.user32.GetParent.argtypes = [ctypes.c_void_p]
        self.user32.GetParent.restype = ctypes.c_void_p
        
        self.user32.EnumChildWindows.argtypes = [
            ctypes.c_void_p, self.WNDENUMPROC, ctypes.c_void_p
        ]
        
        self.user32.GetClassNameW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int
        ]
        
        self.user32.GetWindowTextW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int
        ]
        
        self.user32.GetWindowRect.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)
        ]
        
        self.user32.GetClientRect.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)
        ]
        
        self.user32.SetWindowPos.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint
        ]
        
        self.user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        self.user32.PostMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
        ]

    def find_window(self, class_name: Optional[str], title: Optional[str]) -> Optional[int]:
        if not self.available:
            return None
        hwnd = self.user32.FindWindowW(class_name, title)
        return hwnd if hwnd else None

    def get_class_name(self, hwnd: int) -> str:
        if not self.available:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def get_window_text(self, hwnd: int) -> str:
        if not self.available:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        self.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value

    def get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """Returns (x, y, width, height)"""
        if not self.available:
            return (0, 0, 0, 0)
        rect = ctypes.wintypes.RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def get_client_rect(self, hwnd: int) -> Tuple[int, int]:
        """Returns (width, height) of client area"""
        if not self.available:
            return (0, 0)
        rect = ctypes.wintypes.RECT()
        self.user32.GetClientRect(hwnd, ctypes.byref(rect))
        return (rect.right, rect.bottom)

    def get_window_style(self, hwnd: int) -> int:
        if not self.available:
            return 0
        if struct.calcsize("P") == 8:
            # Use GetWindowLongPtrW for 64-bit compatibility
            self.user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.user32.GetWindowLongPtrW.restype = ctypes.c_longlong
            return self.user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
        return self.user32.GetWindowLongW(hwnd, GWL_STYLE)

    def get_window_ex_style(self, hwnd: int) -> int:
        if not self.available:
            return 0
        if struct.calcsize("P") == 8:
            # Use GetWindowLongPtrW for 64-bit compatibility
            self.user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.user32.GetWindowLongPtrW.restype = ctypes.c_longlong
            return self.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        return self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

    def get_parent(self, hwnd: int) -> Optional[int]:
        if not self.available:
            return None
        parent = self.user32.GetParent(hwnd)
        return parent if parent else None

    def is_visible(self, hwnd: int) -> bool:
        if not self.available:
            return False
        return bool(self.user32.IsWindowVisible(hwnd))

    def show_window(self, hwnd: int, cmd: int):
        if self.available:
            self.user32.ShowWindow(hwnd, cmd)

    def set_window_pos(self, hwnd: int, x: int, y: int, w: int, h: int, flags: int):
        if self.available:
            self.user32.SetWindowPos(hwnd, None, x, y, w, h, flags)

    def post_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0):
        if self.available:
            self.user32.PostMessageW(hwnd, msg, wparam, lparam)

    def enum_child_windows(self, hwnd: int, callback: Callable[[int], bool]):
        """Enumerates all child windows"""
        if not self.available:
            return
            
        def _callback(child_hwnd, _):
            return callback(child_hwnd)
        
        # Store callback reference to prevent garbage collection during enumeration
        wrapped_callback = self.WNDENUMPROC(_callback)
        self._callback_refs.append(wrapped_callback)
        
        try:
            self.user32.EnumChildWindows(hwnd, wrapped_callback, 0)
        finally:
            # Clean up callback reference after enumeration completes
            if wrapped_callback in self._callback_refs:
                self._callback_refs.remove(wrapped_callback)

    def get_window_info(self, hwnd: int) -> WindowInfo:
        """Full window information retrieval"""
        x, y, w, h = self.get_window_rect(hwnd)
        return WindowInfo(
            hwnd=hwnd,
            class_name=self.get_class_name(hwnd),
            title=self.get_window_text(hwnd),
            x=x, y=y, width=w, height=h,
            style=self.get_window_style(hwnd),
            ex_style=self.get_window_ex_style(hwnd),
            is_visible=self.is_visible(hwnd),
            parent_hwnd=self.get_parent(hwnd)
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Window Hierarchy Analyzer
# ═══════════════════════════════════════════════════════════════════════════════
class WindowHierarchyAnalyzer:
    """카카오톡 윈도우 계층 구조 분석기"""
    
    # KakaoTalk window patterns
    MAIN_CLASS = "EVA_Window_Dblclk"
    MAIN_TITLES = ["카카오톡", "KakaoTalk", "カカオトーク"]
    
    def __init__(self, api: WinAPIWrapper, logger: Optional[logging.Logger] = None):
        self.api = api
        self.logger = logger or logging.getLogger(__name__)
        self._cache: Dict[int, WindowInfo] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 0.5  # 500ms cache
        self._cache_lock = threading.Lock()  # Thread safety for cache access
    
    def find_main_window(self) -> Optional[int]:
        """카카오톡 메인 윈도우 찾기"""
        for title in self.MAIN_TITLES:
            hwnd = self.api.find_window(self.MAIN_CLASS, title)
            if hwnd:
                return hwnd
        # Fallback: class name only
        return self.api.find_window(self.MAIN_CLASS, None)
    
    def build_window_tree(self, root_hwnd: int, max_depth: int = 10) -> Optional[WindowInfo]:
        """재귀적으로 윈도우 트리 구축 (thread-safe)"""
        if not root_hwnd:
            return None
            
        # Check cache with lock
        now = time.time()
        with self._cache_lock:
            if root_hwnd in self._cache and (now - self._cache_time) < self._cache_ttl:
                return self._cache[root_hwnd]
        
        root_info = self.api.get_window_info(root_hwnd)
        
        # Collect children
        children_hwnds: List[int] = []
        def collect_children(hwnd: int) -> bool:
            children_hwnds.append(hwnd)
            return True
        
        self.api.enum_child_windows(root_hwnd, collect_children)
        
        # Build child infos (only direct children for real tree structure)
        for child_hwnd in children_hwnds:
            parent = self.api.get_parent(child_hwnd)
            if parent == root_hwnd:
                child_info = self.api.get_window_info(child_hwnd)
                child_info.parent_hwnd = root_hwnd
                root_info.children.append(child_info)
        
        # Cache result with lock
        with self._cache_lock:
            self._cache[root_hwnd] = root_info
            self._cache_time = now
        
        return root_info
    
    def get_all_descendants(self, root_hwnd: int) -> List[WindowInfo]:
        """모든 자손 윈도우 목록 (flat)"""
        descendants: List[WindowInfo] = []
        
        def collect(hwnd: int) -> bool:
            info = self.api.get_window_info(hwnd)
            descendants.append(info)
            return True
        
        self.api.enum_child_windows(root_hwnd, collect)
        return descendants
    
    def dump_hierarchy(self, root_hwnd: int, indent: int = 0) -> str:
        """계층 구조를 문자열로 덤프 (디버깅용)"""
        lines = []
        info = self.api.get_window_info(root_hwnd)
        prefix = "  " * indent
        lines.append(
            f"{prefix}[{hex(info.hwnd)}] {info.class_name} "
            f"'{self._sanitize_title(info.title)}' {info.width}x{info.height} "
            f"{'V' if info.is_visible else 'H'}"
        )
        
        children: List[int] = []
        def collect(hwnd: int) -> bool:
            if self.api.get_parent(hwnd) == root_hwnd:
                children.append(hwnd)
            return True
        
        self.api.enum_child_windows(root_hwnd, collect)
        
        for child_hwnd in children:
            lines.append(self.dump_hierarchy(child_hwnd, indent + 1))
        
        return "\n".join(lines)

    def _sanitize_title(self, title: str) -> str:
        """Sanitize window title to remove PII"""
        if not title:
            return ""
        # Safe list of known system/app titles
        SAFE_TITLES = {"KakaoTalk", "카카오톡", "KakaoTalkEdgeWnd", "Default IME", "MSCTFIME UI"}
        if title in SAFE_TITLES:
            return title
        return f"{title[:2]}***{title[-1:]}" if len(title) > 3 else "***"


# ═══════════════════════════════════════════════════════════════════════════════
# Ad Pattern Matcher
# ═══════════════════════════════════════════════════════════════════════════════
class AdPatternMatcher:
    """광고 패턴 휴리스틱 매칭"""
    
    # Class name patterns that indicate ads
    AD_CLASS_PATTERNS = [
        "Chrome_WidgetWin_",     # Chromium-based web views (common for ads)
        "RichPopWnd",            # Rich popup windows (ad popups)
        "BannerAd",              # Direct banner class
        "AdView",                # Generic ad view
    ]
    
    # Class patterns for main content (to avoid false positives)
    SAFE_CLASS_PATTERNS = [
        "EVA_Window",            # Main KakaoTalk windows
        "Edit",                  # Text input fields
        "Button",                # Buttons
        "Static",                # Labels
        "SysListView",           # List views
        "SysTreeView",           # Tree views
    ]
    
    # Size thresholds for banner detection
    BANNER_HEIGHT_MIN = 60
    BANNER_HEIGHT_MAX = 200
    MAX_DETECTED_CACHE_SIZE = 500  # Limit cache size to prevent memory leak
    
    # Sensitivity thresholds - higher means more strict (fewer false positives)
    SENSITIVITY_THRESHOLDS = {
        "low": 0.90,    # Only very confident detections
        "medium": 0.75, # Default - balanced
        "high": 0.60    # Aggressive - may have more false positives
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None, sensitivity: str = "medium"):
        self.logger = logger or logging.getLogger(__name__)
        self._detected_ads: OrderedDict[int, bool] = OrderedDict()  # LRU cache for detected hwnds
        self._sensitivity = sensitivity
        self._confidence_threshold = self.SENSITIVITY_THRESHOLDS.get(sensitivity, 0.75)
    
    def set_sensitivity(self, sensitivity: str):
        """Set detection sensitivity level"""
        self._sensitivity = sensitivity
        self._confidence_threshold = self.SENSITIVITY_THRESHOLDS.get(sensitivity, 0.75)
        self.logger.info(f"Sensitivity set to: {sensitivity} (threshold: {self._confidence_threshold})")
    
    def analyze_window(self, window: WindowInfo, parent: Optional[WindowInfo] = None) -> Optional[AdDetectionResult]:
        """단일 윈도우 광고 분석"""
        
        # Skip invisible windows
        if not window.is_visible:
            return None
        
        # Skip already detected (with LRU cache limit)
        if window.hwnd in self._detected_ads:
            # Move to end (recently accessed)
            self._detected_ads.move_to_end(window.hwnd)
            return None
        
        # Check for popup ads first (high priority)
        if self._is_popup_ad(window):
            self._add_to_cache(window.hwnd)
            result = AdDetectionResult(
                window=window,
                ad_type=AdType.POPUP,
                confidence=0.95,
                reason="Popup window pattern detected (RichPopWnd)"
            )
            return self._filter_by_confidence(result)
        
        # Check for Chrome widget ads (embedded web ads)
        if self._is_chrome_widget_ad(window, parent):
            self._add_to_cache(window.hwnd)
            result = AdDetectionResult(
                window=window,
                ad_type=AdType.EMBEDDED,
                confidence=0.85,
                reason="Chrome WidgetWin detected (embedded web ad)"
            )
            return self._filter_by_confidence(result)
        
        # Check for banner ads by size/position
        banner_result = self._check_banner_heuristics(window, parent)
        if banner_result:
            self._add_to_cache(window.hwnd)
            return self._filter_by_confidence(banner_result)
        
        return None
    
    def _filter_by_confidence(self, result: Optional[AdDetectionResult]) -> Optional[AdDetectionResult]:
        """Filter result by confidence threshold based on sensitivity setting"""
        if result and result.confidence >= self._confidence_threshold:
            return result
        return None
    
    def _is_popup_ad(self, window: WindowInfo) -> bool:
        """팝업 광고 감지"""
        # RichPopWnd is the main popup ad class
        if "RichPopWnd" in window.class_name:
            return True
        
        # Topmost popup without meaningful title
        if window.is_popup and window.is_topmost:
            if not window.title or len(window.title) < 3:
                return True
        
        return False
    
    def _is_chrome_widget_ad(self, window: WindowInfo, parent: Optional[WindowInfo]) -> bool:
        """Chrome 기반 광고 웹뷰 감지"""
        if not window.class_name.startswith("Chrome_WidgetWin_"):
            return False
        
        # Chrome widget in KakaoTalk context is likely an ad
        # Additional checks to reduce false positives
        if parent:
            # If it's taking small portion of parent, likely an ad banner
            if window.height < 200 and window.width > 200:
                return True
            
            # Full-size Chrome widget might be legitimate (e.g., login page)
            if window.height > parent.height * 0.8:
                return False
        
        # Default: consider it an ad
        return True
    
    def _check_banner_heuristics(self, window: WindowInfo, parent: Optional[WindowInfo]) -> Optional[AdDetectionResult]:
        """배너 광고 휴리스틱 검사"""
        if not parent:
            return None
        
        # Check if window spans full width of parent
        width_match = abs(window.width - parent.width) < 50
        
        # Check if height is in banner range
        is_banner_height = self.BANNER_HEIGHT_MIN <= window.height <= self.BANNER_HEIGHT_MAX
        
        if not (width_match and is_banner_height):
            return None
        
        # Position analysis
        relative_top = window.y - parent.y
        relative_bottom = (parent.y + parent.height) - (window.y + window.height)
        
        # Top banner
        if relative_top < 100:
            return AdDetectionResult(
                window=window,
                ad_type=AdType.BANNER_TOP,
                confidence=0.75,
                reason=f"Top banner heuristic: {window.width}x{window.height}, pos={relative_top}"
            )
        
        # Bottom banner
        if relative_bottom < 100:
            return AdDetectionResult(
                window=window,
                ad_type=AdType.BANNER_BOTTOM,
                confidence=0.75,
                reason=f"Bottom banner heuristic: {window.width}x{window.height}, pos_bottom={relative_bottom}"
            )
        
        return None
    
    def _add_to_cache(self, hwnd: int):
        """Add hwnd to LRU cache with size limit"""
        self._detected_ads[hwnd] = True
        # Evict oldest entries if cache exceeds limit
        while len(self._detected_ads) > self.MAX_DETECTED_CACHE_SIZE:
            self._detected_ads.popitem(last=False)
    
    def reset_detection_cache(self):
        """감지 캐시 초기화"""
        self._detected_ads.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Ad Layout Sniffer (Main Engine)
# ═══════════════════════════════════════════════════════════════════════════════
class AdLayoutSniffer:
    """메인 광고 레이아웃 스니핑 엔진"""
    
    def __init__(self, logger: Optional[logging.Logger] = None, 
                 on_ad_detected: Optional[Callable[[AdDetectionResult], None]] = None,
                 on_log: Optional[Callable[[str, str], None]] = None,
                 sensitivity: str = "medium"):
        self.logger = logger or logging.getLogger(__name__)
        self.api = WinAPIWrapper()
        self.analyzer = WindowHierarchyAnalyzer(self.api, self.logger)
        self.matcher = AdPatternMatcher(self.logger, sensitivity=sensitivity)
        
        self.on_ad_detected = on_ad_detected
        self.on_log = on_log
        
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._last_main_hwnd: Optional[int] = None
        self._lock = threading.Lock()  # Thread safety for stats
        
        # Statistics (protected by _lock)
        self._stats = {
            "ads_detected": 0,
            "popups_blocked": 0,
            "banners_hidden": 0,
            "last_scan": None,
            "scan_count": 0
        }
    
    def start(self):
        """스니핑 시작"""
        if self._active:
            return
        
        self._active = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("INFO", "AdLayoutSniffer 엔진 시작됨")
    
    def stop(self):
        """스니핑 중지"""
        self._active = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._log("INFO", "AdLayoutSniffer 엔진 중지됨")
    
    def is_running(self) -> bool:
        return self._active
    
    def set_sensitivity(self, sensitivity: str):
        """Set detection sensitivity level (low, medium, high)"""
        self.matcher.set_sensitivity(sensitivity)
        self._log("INFO", f"감도 설정 변경: {sensitivity}")
    
    def _log(self, level: str, message: str):
        if self.on_log:
            self.on_log(level, message)
        
        if level == "INFO":
            self.logger.info(message)
        elif level == "WARN":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)
        else:
            self.logger.debug(message)
    
    def _run_loop(self):
        """메인 스니핑 루프"""
        while self._active:
            try:
                self._scan_and_process()
            except OSError as e:
                # Window handle invalid or access denied - expected during window changes
                self.logger.debug(f"OS error during scan (expected): {e}")
            except ctypes.ArgumentError as e:
                # ctypes argument error - usually invalid handle
                self.logger.debug(f"ctypes error: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected scan error: {type(e).__name__}: {e}")
            
            time.sleep(0.5)  # 500ms interval
    
    def _scan_and_process(self):
        """스캔 및 처리"""
        main_hwnd = self.analyzer.find_main_window()
        
        if not main_hwnd:
            self._last_main_hwnd = None
            return
        
        # Log when KakaoTalk is detected
        if main_hwnd != self._last_main_hwnd:
            self._log("INFO", f"카카오톡 감지됨: {hex(main_hwnd)}")
            self._last_main_hwnd = main_hwnd
            self.matcher.reset_detection_cache()
        
        # Get main window info
        main_info = self.api.get_window_info(main_hwnd)
        
        # Scan all descendants
        descendants = self.analyzer.get_all_descendants(main_hwnd)
        
        ads_found = []
        for window in descendants:
            result = self.matcher.analyze_window(window, main_info)
            if result:
                ads_found.append(result)
        
        # Process detected ads
        for ad in ads_found:
            self._handle_ad(ad, main_info)
        
        # Update stats (thread-safe)
        with self._lock:
            self._stats["last_scan"] = time.time()
            self._stats["scan_count"] += 1
    
    def _handle_ad(self, ad: AdDetectionResult, main_window: WindowInfo):
        """감지된 광고 처리"""
        with self._lock:
            self._stats["ads_detected"] += 1
        
        if ad.ad_type == AdType.POPUP:
            # Close popup ads
            self.api.post_message(ad.window.hwnd, WM_CLOSE)
            ad.action_taken = "Closed via WM_CLOSE"
            with self._lock:
                self._stats["popups_blocked"] += 1
            self._log("INFO", f"팝업 광고 차단: {ad.window.class_name}")
            
        elif ad.ad_type in (AdType.BANNER_TOP, AdType.BANNER_BOTTOM, AdType.EMBEDDED):
            # Hide banner/embedded ads
            self.api.show_window(ad.window.hwnd, SW_HIDE)
            ad.action_taken = "Hidden via ShowWindow"
            with self._lock:
                self._stats["banners_hidden"] += 1
            self._log("DEBUG", f"배너 숨김: {ad.window.class_name} ({ad.window.width}x{ad.window.height})")
            
            # Resize main content area to fill the gap
            self._resize_main_content(main_window, ad)
        
        # Callback (outside lock to avoid deadlock)
        if self.on_ad_detected:
            try:
                self.on_ad_detected(ad)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
    
    def _resize_main_content(self, main_window: WindowInfo, ad: AdDetectionResult):
        """메인 콘텐츠 영역 리사이즈 (개선판)"""
        # Content area class patterns - flexible matching for different KakaoTalk versions
        CONTENT_CLASS_PATTERNS = [
            "EVA_ChildWindow",
            "EVA_Window",
            "KakaoContent",
            "ChatView",
        ]
        
        descendants = self.analyzer.get_all_descendants(main_window.hwnd)
        client_w, client_h = self.api.get_client_rect(main_window.hwnd)
        
        # Find main content areas matching patterns
        content_windows = []
        for window in descendants:
            if not window.is_visible:
                continue
            # Check if class matches any content pattern
            for pattern in CONTENT_CLASS_PATTERNS:
                if pattern in window.class_name:
                    # Must be similar width to main window and have decent height
                    if abs(window.width - main_window.width) < 50 and window.height > 100:
                        content_windows.append(window)
                    break
        
        # Sort by size (largest first) - main content is usually the biggest
        content_windows.sort(key=lambda w: w.width * w.height, reverse=True)
        
        for window in content_windows:
            # Calculate new size based on ad type
            # window.y is screen coordinate, we need client-relative. 
            # Approximate by subtracting main window Y, ensuring non-negative.
            new_y = max(0, window.y - main_window.y) 
            new_h = window.height
            
            if ad.ad_type == AdType.BANNER_TOP:
                # Top banner removed - expand upward
                # Start from top of client area
                new_y = 0
                new_h = window.height + ad.window.height
            elif ad.ad_type == AdType.BANNER_BOTTOM:
                # Bottom banner removed - expand downward
                # Y remains the same, new height should be current height + ad height
                new_h = window.height + ad.window.height
            else:
                # Generic: try to fill available space
                new_h = client_h
            
            # Ensure we don't exceed client area
            if new_h > client_h:
                new_h = client_h
            
            # Only resize if the new height is actually larger
            if window.height < new_h:
                try:
                    self.api.set_window_pos(
                        window.hwnd, 0, new_y, client_w, new_h,
                        SWP_NOZORDER | SWP_NOACTIVATE
                    )
                    self._log("DEBUG", f"콘텐츠 영역 리사이즈: {window.class_name} -> {client_w}x{new_h} (y={new_y})")
                except (OSError, ctypes.ArgumentError) as e:
                    self._log("DEBUG", f"리사이즈 실패: {e}")
            break  # Only resize the first (largest) content window
    
    def get_stats(self) -> Dict:
        """통계 반환 (thread-safe)"""
        with self._lock:
            return self._stats.copy()
    
    def inspect(self) -> str:
        """현재 윈도우 계층 구조 덤프"""
        main_hwnd = self.analyzer.find_main_window()
        if not main_hwnd:
            return "KakaoTalk window not found"
        return self.analyzer.dump_hierarchy(main_hwnd)


# ═══════════════════════════════════════════════════════════════════════════════
# Module Test
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    def on_log(level, msg):
        print(f"[{level}] {msg}")
    
    def on_ad(result):
        print(f"AD DETECTED: {result.ad_type.name} - {result.reason}")
    
    sniffer = AdLayoutSniffer(on_log=on_log, on_ad_detected=on_ad)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--inspect":
        print("=== Window Hierarchy ===")
        print(sniffer.inspect())
    else:
        print("Starting Ad Layout Sniffer... (Press Ctrl+C to stop)")
        sniffer.start()
        try:
            while True:
                time.sleep(5)
                stats = sniffer.get_stats()
                print(f"Stats: {stats}")
        except KeyboardInterrupt:
            sniffer.stop()
            print("\nStopped.")
