# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v6.0 (Complete Redesign)
================================================
- Correctly targets EVA_Window_Dblclk and Chrome_WidgetWin_ ads
- HiDPI Per-Monitor DPI Awareness
- AdFit Registry blocking
- Modern UI with real-time logging
- Windows startup and system tray integration
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
from typing import Optional, List, Tuple
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 서드파티 라이브러리 (선택적)
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
# HiDPI 설정 (프로그램 시작 전에 호출해야 함)
# ═══════════════════════════════════════════════════════════════════════════════
def setup_hidpi():
    """HiDPI 디스플레이 지원 설정"""
    if platform.system() != "Windows":
        return
    
    try:
        # Per-Monitor DPI Awareness V2 (Windows 10 1703+)
        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        if awareness.value == 0:  # 아직 설정되지 않음
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE_V2
    except Exception:
        try:
            # 폴백: System DPI Aware
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# 프로그램 시작 전에 HiDPI 설정
setup_hidpi()


# ═══════════════════════════════════════════════════════════════════════════════
# 상수 및 설정
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "6.0.0"
APP_NAME = "KakaoTalk AdBlocker Pro"

# 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "adblock_settings.json")
DOMAINS_FILE = os.path.join(BASE_DIR, "blocked_domains.txt")
LOG_FILE = os.path.join(BASE_DIR, "adblock.log")

# 색상 테마
COLORS = {
    "primary": "#FEE500",
    "primary_dark": "#E6CF00",
    "bg": "#FFFFFF",
    "bg_dark": "#1A1A1A",
    "fg": "#191919",
    "fg_light": "#FFFFFF",
    "sub_text": "#757575",
    "success": "#4CAF50",
    "warning": "#FF9800",
    "error": "#F44336",
    "surface": "#F5F5F5",
    "border": "#E0E0E0",
    "log_bg": "#1E1E1E",
    "log_fg": "#D4D4D4",
}

# 광고 도메인 목록
DEFAULT_AD_DOMAINS = [
    "display.ad.daum.net", "analytics.ad.daum.net", "ad.daum.net",
    "alea.adam.ad.daum.net", "adam.ad.daum.net", "wat.ad.daum.net",
    "biz.ad.daum.net", "cs.ad.daum.net", "ad.mad.daum.net",
    "ams.ad.daum.net", "amsv2.daum.net",
    "ad.smart.kakao.com", "ad.kakao.com", "display.ad.kakao.com",
    "business.kakao.com",
    "ad.kakaocdn.net", "ad.kakaocdn.com", "t1.kakaocdn.net",
    "st.kakaocdn.net", "adimg.imkakao.com", "adimg.daumcdn.net",
    "track.tiara.kakao.com", "stat.tiara.kakao.com", "kakaoad.criteo.com"
] + [f"adimg{i}.kakaocdn.net" for i in range(1, 11)]


# ═══════════════════════════════════════════════════════════════════════════════
# 로깅 시스템
# ═══════════════════════════════════════════════════════════════════════════════
class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


def setup_logging() -> Tuple[logging.Logger, queue.Queue]:
    log_queue = queue.Queue(maxsize=1000)
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        logger.handlers.clear()
    
    formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    
    try:
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass
    
    qh = QueueHandler(log_queue)
    qh.setLevel(logging.DEBUG)
    qh.setFormatter(formatter)
    logger.addHandler(qh)
    
    return logger, log_queue


# ═══════════════════════════════════════════════════════════════════════════════
# 설정 클래스
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class AppSettings:
    auto_start: bool = False
    minimize_to_tray: bool = True
    start_minimized: bool = False
    hide_layout: bool = True
    block_adfit: bool = True  # AdFit 레지스트리 차단
    
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
# Windows API 래퍼
# ═══════════════════════════════════════════════════════════════════════════════
class WinAPI:
    """Windows API 함수 래퍼"""
    
    def __init__(self):
        if platform.system() != "Windows":
            self.available = False
            return
        
        self.available = True
        self.user32 = ctypes.windll.user32
        
        # 콜백 타입 정의
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(ctypes.py_object))
        
        # 함수 설정
        self.user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        self.user32.FindWindowW.restype = ctypes.c_void_p
        
        self.user32.EnumChildWindows.argtypes = [ctypes.c_void_p, self.WNDENUMPROC, ctypes.POINTER(ctypes.py_object)]
        self.user32.EnumChildWindows.restype = ctypes.c_bool
        
        self.user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        self.user32.GetClassNameW.restype = ctypes.c_int
        
        self.user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        
        self.user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        
        self.user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.ShowWindow.restype = ctypes.c_bool
        
        self.user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        self.user32.IsWindowVisible.restype = ctypes.c_bool
        
        self.user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        self.user32.GetClientRect.restype = ctypes.c_bool
        
        self.user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        self.user32.GetWindowRect.restype = ctypes.c_bool
        
        self.user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        self.user32.SetWindowPos.restype = ctypes.c_bool
        
        self.user32.InvalidateRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        self.user32.InvalidateRect.restype = ctypes.c_bool
        
        self.user32.GetParent.argtypes = [ctypes.c_void_p]
        self.user32.GetParent.restype = ctypes.c_void_p

    def find_window(self, class_name: str, window_name: str = None) -> Optional[int]:
        if not self.available:
            return None
        hwnd = self.user32.FindWindowW(class_name, window_name)
        return hwnd if hwnd else None
    
    def get_class_name(self, hwnd) -> str:
        if not self.available:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    
    def get_window_text(self, hwnd) -> str:
        if not self.available:
            return ""
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    
    def show_window(self, hwnd, cmd: int) -> bool:
        if not self.available:
            return False
        return self.user32.ShowWindow(hwnd, cmd)
    
    def is_window_visible(self, hwnd) -> bool:
        if not self.available:
            return False
        return self.user32.IsWindowVisible(hwnd)
    
    def get_client_rect(self, hwnd) -> Optional[Tuple[int, int, int, int]]:
        if not self.available:
            return None
        rect = ctypes.wintypes.RECT()
        if self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return None
    
    def set_window_pos(self, hwnd, x: int, y: int, width: int, height: int, flags: int = 0x0002) -> bool:
        if not self.available:
            return False
        return self.user32.SetWindowPos(hwnd, None, x, y, width, height, flags)
    
    def invalidate_rect(self, hwnd) -> bool:
        if not self.available:
            return False
        return self.user32.InvalidateRect(hwnd, None, True)
    
    def get_parent(self, hwnd):
        if not self.available:
            return None
        return self.user32.GetParent(hwnd)


# ═══════════════════════════════════════════════════════════════════════════════
# 광고 레이아웃 숨김 (완전 재설계)
# ═══════════════════════════════════════════════════════════════════════════════
class AdLayoutHider:
    """
    Windows API를 사용하여 카카오톡 광고 영역 숨김 및 레이아웃 조정
    
    Based on KakaoTalkAdGuard (loopback-kr) implementation:
    - Main window class: EVA_Window_Dblclk
    - Ad windows: Chrome_WidgetWin_ (Chromium-based ads)
    - Main view: EVA_ChildWindow with OnlineMainView_ prefix
    """
    
    # 카카오톡 윈도우 설정
    MAIN_CLASS = "EVA_Window_Dblclk"
    MAIN_TITLES = ["카카오톡", "カカオトーク", "KakaoTalk"]
    CHILD_CLASS = "EVA_ChildWindow"
    AD_CLASS_PREFIX = "Chrome_WidgetWin_"
    MAIN_VIEW_PREFIX = "OnlineMainView_"
    LOCK_VIEW_PREFIX = "LockModeView_"
    
    # Windows 상수
    SW_HIDE = 0
    SW_SHOW = 5
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    HWND_TOP = 0
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.winapi = WinAPI()
        self.active = False
        self.thread = None
        self._ads_hidden_count = 0
        self._main_hwnd = None
    
    def start(self):
        if not self.winapi.available or self.active:
            return
        
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="AdLayoutHider")
        self.thread.start()
        self.logger.info("광고 레이아웃 숨김 시작 (EVA_Window_Dblclk 탐색)")
    
    def stop(self):
        self.active = False
        self.logger.info("광고 레이아웃 숨김 중지")
    
    @property
    def ads_hidden(self) -> int:
        return self._ads_hidden_count
    
    def _loop(self):
        while self.active:
            try:
                self._process_kakaotalk()
                time.sleep(0.1)  # 100ms 주기
            except Exception as e:
                self.logger.debug(f"처리 중 오류: {e}")
                time.sleep(1)
    
    def _process_kakaotalk(self):
        """카카오톡 메인 윈도우 찾기 및 처리"""
        main_hwnd = None
        
        # 다국어 타이틀로 메인 윈도우 찾기
        for title in self.MAIN_TITLES:
            hwnd = self.winapi.find_window(self.MAIN_CLASS, title)
            if hwnd:
                main_hwnd = hwnd
                break
        
        if not main_hwnd:
            self._main_hwnd = None
            return
        
        if self._main_hwnd != main_hwnd:
            self._main_hwnd = main_hwnd
            self.logger.info(f"카카오톡 메인 윈도우 발견: {main_hwnd}")
        
        # 메인 윈도우 크기 가져오기
        main_rect = self.winapi.get_client_rect(main_hwnd)
        if not main_rect:
            return
        
        main_width = main_rect[2] - main_rect[0]
        main_height = main_rect[3] - main_rect[1]
        
        # 하위 윈도우 처리
        self._process_child_windows(main_hwnd, main_width, main_height)
    
    def _process_child_windows(self, parent_hwnd, parent_width: int, parent_height: int):
        """하위 윈도우 순회 및 처리"""
        
        context = {
            'ads_hidden': 0,
            'parent_width': parent_width,
            'parent_height': parent_height,
            'logger': self.logger,
            'winapi': self.winapi,
            'SW_HIDE': self.SW_HIDE,
            'SWP_NOMOVE': self.SWP_NOMOVE,
            'CHILD_CLASS': self.CHILD_CLASS,
            'AD_CLASS_PREFIX': self.AD_CLASS_PREFIX,
            'MAIN_VIEW_PREFIX': self.MAIN_VIEW_PREFIX,
            'LOCK_VIEW_PREFIX': self.LOCK_VIEW_PREFIX,
        }
        
        def enum_callback(hwnd, lParam):
            try:
                ctx = lParam.contents.value
                winapi = ctx['winapi']
                
                class_name = winapi.get_class_name(hwnd)
                window_text = winapi.get_window_text(hwnd)
                
                # Chrome 기반 광고 숨기기
                if class_name.startswith(ctx['AD_CLASS_PREFIX']):
                    if winapi.is_window_visible(hwnd):
                        winapi.show_window(hwnd, ctx['SW_HIDE'])
                        ctx['ads_hidden'] += 1
                        ctx['logger'].debug(f"광고 숨김: {class_name}")
                
                # EVA_ChildWindow 처리
                if class_name == ctx['CHILD_CLASS']:
                    # OnlineMainView 리사이징
                    if window_text.startswith(ctx['MAIN_VIEW_PREFIX']):
                        new_height = ctx['parent_height'] - 32  # 상단 여백
                        winapi.set_window_pos(
                            hwnd, 0, 0, 
                            ctx['parent_width'], new_height,
                            ctx['SWP_NOMOVE']
                        )
                    
                    # LockModeView 처리
                    elif window_text.startswith(ctx['LOCK_VIEW_PREFIX']):
                        winapi.set_window_pos(
                            hwnd, 0, 0,
                            ctx['parent_width'], ctx['parent_height'],
                            ctx['SWP_NOMOVE']
                        )
                
                # 재귀적으로 자식 윈도우 탐색 (Chrome 광고가 중첩될 수 있음)
                self._enum_child_recursive(hwnd, ctx)
                
            except Exception:
                pass
            return True
        
        # 콜백 호출
        try:
            ctx_ptr = ctypes.pointer(ctypes.py_object(context))
            callback = self.winapi.WNDENUMPROC(enum_callback)
            self.winapi.user32.EnumChildWindows(parent_hwnd, callback, ctx_ptr)
            self._ads_hidden_count = context['ads_hidden']
        except Exception as e:
            self.logger.debug(f"EnumChildWindows 오류: {e}")
    
    def _enum_child_recursive(self, parent_hwnd, ctx):
        """재귀적으로 자식 윈도우 탐색하여 Chrome 광고 숨김"""
        
        def inner_callback(hwnd, lParam):
            try:
                inner_ctx = lParam.contents.value
                winapi = inner_ctx['winapi']
                class_name = winapi.get_class_name(hwnd)
                
                if class_name.startswith(inner_ctx['AD_CLASS_PREFIX']):
                    if winapi.is_window_visible(hwnd):
                        winapi.show_window(hwnd, inner_ctx['SW_HIDE'])
                        inner_ctx['ads_hidden'] += 1
                
                # 더 깊은 계층도 탐색
                self._enum_child_recursive(hwnd, inner_ctx)
                
            except Exception:
                pass
            return True
        
        try:
            ctx_ptr = ctypes.pointer(ctypes.py_object(ctx))
            callback = self.winapi.WNDENUMPROC(inner_callback)
            self.winapi.user32.EnumChildWindows(parent_hwnd, callback, ctx_ptr)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# AdFit 레지스트리 차단
# ═══════════════════════════════════════════════════════════════════════════════
class AdFitBlocker:
    """AdFit 레지스트리의 LUD 값 업데이트로 팝업 광고 차단"""
    
    ADFIT_KEY = r"SOFTWARE\Kakao\AdFit"
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.active = False
        self.thread = None
    
    def start(self):
        if self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="AdFitBlocker")
        self.thread.start()
        self.logger.info("AdFit 레지스트리 차단 시작")
    
    def stop(self):
        self.active = False
        self.logger.info("AdFit 레지스트리 차단 중지")
    
    def _loop(self):
        while self.active:
            try:
                self._update_lud_values()
                time.sleep(5)  # 5초마다 업데이트
            except Exception as e:
                self.logger.debug(f"AdFit 처리 오류: {e}")
                time.sleep(10)
    
    def _update_lud_values(self):
        """모든 AdFit 서브키의 LUD 값을 현재 시간으로 업데이트"""
        try:
            parent_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, 
                self.ADFIT_KEY, 
                0, 
                winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
            )
        except FileNotFoundError:
            return  # AdFit 키 없음
        except Exception:
            return
        
        try:
            index = 0
            current_time = str(int(time.time()))
            
            while True:
                try:
                    subkey_name = winreg.EnumKey(parent_key, index)
                    subkey_path = f"{self.ADFIT_KEY}\\{subkey_name}"
                    
                    try:
                        subkey = winreg.OpenKey(
                            winreg.HKEY_CURRENT_USER,
                            subkey_path,
                            0,
                            winreg.KEY_WRITE
                        )
                        winreg.SetValueEx(subkey, "LUD", 0, winreg.REG_SZ, current_time)
                        winreg.CloseKey(subkey)
                    except Exception:
                        pass
                    
                    index += 1
                except OSError:
                    break  # 더 이상 서브키 없음
        finally:
            winreg.CloseKey(parent_key)


# ═══════════════════════════════════════════════════════════════════════════════
# 시스템 관리자
# ═══════════════════════════════════════════════════════════════════════════════
class SystemManager:
    """시스템 레벨 작업 관리"""
    
    @staticmethod
    def is_admin() -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @staticmethod
    def run_as_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, 
                " ".join(f'"{a}"' for a in sys.argv), 
                None, 1
            )
            sys.exit(0)
        except Exception:
            pass

    @staticmethod
    def flush_dns() -> bool:
        try:
            subprocess.run(
                ["ipconfig", "/flushdns"], 
                capture_output=True, 
                creationflags=0x08000000
            )
            return True
        except Exception:
            return False

    @staticmethod
    def is_process_running(process_name: str) -> bool:
        if not PSUTIL_AVAILABLE:
            return False
        try:
            for p in psutil.process_iter(['name']):
                if process_name.lower() in (p.info['name'] or '').lower():
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def restart_process(process_name: str) -> bool:
        exe_path = None
        
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name', 'exe']):
                    if process_name.lower() in (p.info['name'] or '').lower():
                        exe_path = p.info['exe']
                        break
            except Exception:
                pass
        
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                capture_output=True,
                creationflags=0x08000000
            )
            time.sleep(1.5)
            
            if exe_path and os.path.exists(exe_path):
                os.startfile(exe_path)
                return True
            
            # 기본 경로 시도
            default_paths = [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
            ]
            for path in default_paths:
                if os.path.exists(path):
                    os.startfile(path)
                    return True
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 시작프로그램 관리
# ═══════════════════════════════════════════════════════════════════════════════
class StartupManager:
    STARTUP_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "KakaoTalkAdBlockerPro"
    
    @staticmethod
    def is_enabled() -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.STARTUP_KEY, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, StartupManager.APP_NAME)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    
    @staticmethod
    def set_enabled(enable: bool) -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    exe_path = sys.executable
                    if exe_path.endswith(("python.exe", "pythonw.exe")):
                        script_path = os.path.abspath(sys.argv[0])
                        exe_path = f'"{exe_path}" "{script_path}" --minimized'
                    else:
                        exe_path = f'"{exe_path}" --minimized'
                    
                    winreg.SetValueEx(key, StartupManager.APP_NAME, 0, winreg.REG_SZ, exe_path)
                else:
                    try:
                        winreg.DeleteValue(key, StartupManager.APP_NAME)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Hosts 파일 관리
# ═══════════════════════════════════════════════════════════════════════════════
class HostsManager:
    HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
    MARKER_START = "# [KakaoTalk AdBlock Start]"
    MARKER_END = "# [KakaoTalk AdBlock End]"

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def block(self, domains: List[str]) -> bool:
        try:
            with open(self.HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"Hosts 읽기 실패: {e}")
            return False
        
        # 기존 항목 제거
        lines = []
        skip = False
        for line in content.splitlines():
            if self.MARKER_START in line:
                skip = True
                continue
            if self.MARKER_END in line:
                skip = False
                continue
            if not skip:
                # 기존 광고 도메인 제거
                is_ad_line = False
                for d in domains:
                    if d in line and ("0.0.0.0" in line or "127.0.0.1" in line):
                        is_ad_line = True
                        break
                if not is_ad_line:
                    lines.append(line)
        
        # 새 항목 추가
        new_content = "\n".join(lines).strip() + "\n\n"
        new_content += f"{self.MARKER_START}\n"
        new_content += f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        for d in domains:
            new_content += f"0.0.0.0 {d}\n"
        new_content += f"{self.MARKER_END}\n"
        
        try:
            os.chmod(self.HOSTS_PATH, 0o777)
            with open(self.HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write(new_content)
            self.logger.info(f"{len(domains)}개 도메인 차단 완료")
            return True
        except Exception as e:
            self.logger.error(f"Hosts 쓰기 실패: {e}")
            return False

    def get_status(self, domains: List[str]) -> float:
        try:
            with open(self.HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return 0.0
        
        count = sum(1 for d in domains if f"0.0.0.0 {d}" in content or f"127.0.0.1 {d}" in content)
        return count / len(domains) if domains else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 트레이 아이콘 관리
# ═══════════════════════════════════════════════════════════════════════════════
class TrayManager:
    def __init__(self, app: 'MainWindow'):
        self.app = app
        self.icon = None
        self._running = False
    
    def create_icon_image(self):
        """노란 방패 아이콘 생성"""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 방패 외곽
        shield_color = (254, 229, 0, 255)
        outline_color = (200, 180, 0, 255)
        points = [
            (size//2, 4), (size-4, 14), (size-4, size//2),
            (size//2, size-4), (4, size//2), (4, 14)
        ]
        draw.polygon(points, fill=shield_color, outline=outline_color)
        
        # 체크마크
        check_color = (25, 25, 25, 255)
        draw.line([(18, 32), (26, 42), (46, 20)], fill=check_color, width=5)
        
        return image
    
    def setup(self):
        if not TRAY_AVAILABLE:
            return
        
        image = self.create_icon_image()
        
        menu = pystray.Menu(
            pystray.MenuItem(f"{APP_NAME} v{VERSION}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("열기", lambda: self._on_show()),
            pystray.MenuItem("종료", lambda: self._on_quit()),
        )
        
        self.icon = pystray.Icon(
            name="KakaoTalkAdBlocker",
            icon=image,
            title=APP_NAME,
            menu=menu
        )
    
    def start(self):
        if not TRAY_AVAILABLE or self._running:
            return
        self._running = True
        threading.Thread(target=self._run, daemon=True, name="TrayIcon").start()
    
    def _run(self):
        try:
            self.icon.run()
        except Exception:
            pass
        self._running = False
    
    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        self._running = False
    
    def _on_show(self):
        self.app.root.after(0, self.app.show_window)
    
    def _on_quit(self):
        self.stop()
        self.app.root.after(0, self.app.quit_app)


# ═══════════════════════════════════════════════════════════════════════════════
# Toast 알림
# ═══════════════════════════════════════════════════════════════════════════════
class Toast:
    """화면 우측 하단에 표시되는 Toast 알림"""
    
    _active_toasts = []
    
    @classmethod
    def show(cls, parent, message: str, duration: int = 3000, toast_type: str = "info"):
        toast = tk.Toplevel(parent)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        
        colors = {
            "info": COLORS["primary"],
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "error": COLORS["error"]
        }
        bg_color = colors.get(toast_type, COLORS["primary"])
        
        frame = tk.Frame(toast, bg=bg_color, padx=15, pady=10)
        frame.pack(fill="both", expand=True)
        
        tk.Label(
            frame, text=message, bg=bg_color, fg=COLORS["fg"],
            font=("맑은 고딕", 10), wraplength=300
        ).pack()
        
        # 위치 계산 (기존 토스트 아래에)
        toast.update_idletasks()
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()
        toast_width = toast.winfo_width()
        toast_height = toast.winfo_height()
        
        y_offset = sum(t.winfo_height() + 10 for t in cls._active_toasts if t.winfo_exists())
        
        x = screen_width - toast_width - 20
        y = screen_height - toast_height - 60 - y_offset
        
        toast.geometry(f"+{x}+{y}")
        cls._active_toasts.append(toast)
        
        def destroy():
            if toast in cls._active_toasts:
                cls._active_toasts.remove(toast)
            toast.destroy()
        
        toast.after(duration, destroy)


# ═══════════════════════════════════════════════════════════════════════════════
# 메인 윈도우
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk, start_minimized: bool = False):
        self.root = root
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        
        # 매니저 초기화
        self.hosts_mgr = HostsManager(self.logger)
        self.layout_hider = AdLayoutHider(self.logger)
        self.adfit_blocker = AdFitBlocker(self.logger)
        self.tray_manager = None
        
        self._is_quitting = False
        self._log_update_job = None
        
        self._apply_dpi_scaling()
        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._start_services()
        self._start_log_updates()
        
        if start_minimized or self.settings.start_minimized:
            self.root.after(100, self.hide_to_tray)
    
    def _apply_dpi_scaling(self):
        """DPI 스케일링 적용"""
        try:
            dpi = self.root.winfo_fpixels('1i')
            scale_factor = dpi / 96.0
            self.root.tk.call('tk', 'scaling', scale_factor)
        except Exception:
            pass
    
    def _setup_window(self):
        self.root.title(APP_NAME)
        self.root.geometry("550x700")
        self.root.minsize(500, 600)
        self.root.configure(bg=COLORS["bg"])
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        if not SystemManager.is_admin():
            if messagebox.askyesno("권한 필요", "광고 차단을 위해 관리자 권한이 필요합니다.\n재실행 하시겠습니까?"):
                SystemManager.run_as_admin()
            else:
                self.logger.warning("관리자 권한 없이 실행됨")
    
    def _setup_tray(self):
        if TRAY_AVAILABLE:
            self.tray_manager = TrayManager(self)
            self.tray_manager.setup()
            self.tray_manager.start()
    
    def _setup_ui(self):
        # 스타일 설정
        style = ttk.Style()
        style.configure("TCheckbutton", background=COLORS["bg"], font=("맑은 고딕", 10))
        
        # 헤더
        header = tk.Frame(self.root, bg=COLORS["primary"], height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header, text="🛡️", bg=COLORS["primary"], 
            font=("Segoe UI Emoji", 22)
        ).pack(side="left", padx=(20, 10))
        
        title_frame = tk.Frame(header, bg=COLORS["primary"])
        title_frame.pack(side="left", fill="y", pady=12)
        
        tk.Label(
            title_frame, text=APP_NAME, bg=COLORS["primary"], fg=COLORS["fg"],
            font=("맑은 고딕", 13, "bold")
        ).pack(anchor="w")
        tk.Label(
            title_frame, text=f"v{VERSION}", bg=COLORS["primary"], fg="#555",
            font=("맑은 고딕", 9)
        ).pack(anchor="w")
        
        # 메인 컨텐츠 (스크롤 가능)
        container = tk.Frame(self.root, bg=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # 상태 카드
        status_frame = tk.Frame(container, bg=COLORS["bg"])
        status_frame.pack(fill="x", pady=(0, 15))
        
        # 보호 상태
        self.card_protect = self._create_status_card(status_frame, "보호 상태", "확인 중...")
        self.card_protect.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # 카카오톡 상태
        self.card_process = self._create_status_card(status_frame, "카카오톡", "감지 안됨", COLORS["sub_text"])
        self.card_process.pack(side="left", fill="x", expand=True)
        
        # 스마트 최적화 버튼
        opt_btn = tk.Button(
            container, text="✨ 스마트 최적화", command=self._smart_optimize,
            bg=COLORS["primary"], fg=COLORS["fg"], activebackground=COLORS["primary_dark"],
            font=("맑은 고딕", 12, "bold"), relief="flat", cursor="hand2",
            height=2
        )
        opt_btn.pack(fill="x", pady=(0, 15))
        
        # 설정 프레임
        settings_frame = tk.LabelFrame(
            container, text="설정", bg=COLORS["bg"], fg=COLORS["sub_text"],
            font=("맑은 고딕", 10), padx=15, pady=10
        )
        settings_frame.pack(fill="x", pady=(0, 15))
        
        # 체크박스들
        self.var_autostart = tk.BooleanVar(value=StartupManager.is_enabled())
        self.var_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.var_start_hidden = tk.BooleanVar(value=self.settings.start_minimized)
        self.var_hide_layout = tk.BooleanVar(value=self.settings.hide_layout)
        self.var_block_adfit = tk.BooleanVar(value=self.settings.block_adfit)
        
        checks = [
            ("Windows 시작 시 자동 실행", self.var_autostart, self._toggle_autostart),
            ("닫을 때 트레이로 최소화", self.var_tray, self._save_settings),
            ("시작 시 트레이로 바로 최소화", self.var_start_hidden, self._save_settings),
            ("광고 레이아웃(빈 공간) 자동 제거", self.var_hide_layout, self._toggle_layout_hider),
            ("팝업 광고 차단 (AdFit 레지스트리)", self.var_block_adfit, self._toggle_adfit),
        ]
        
        for text, var, cmd in checks:
            cb = tk.Checkbutton(
                settings_frame, text=text, variable=var, command=cmd,
                bg=COLORS["bg"], activebackground=COLORS["bg"],
                font=("맑은 고딕", 10), anchor="w"
            )
            cb.pack(fill="x", pady=2)
        
        # 실시간 로그
        log_frame = tk.LabelFrame(
            container, text="실시간 로그", bg=COLORS["bg"], fg=COLORS["sub_text"],
            font=("맑은 고딕", 10), padx=10, pady=10
        )
        log_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, bg=COLORS["log_bg"], fg=COLORS["log_fg"],
            font=("Consolas", 9), height=8, state="disabled",
            wrap="word"
        )
        self.log_text.pack(fill="both", expand=True)
        
        # 하단 버튼
        btn_frame = tk.Frame(container, bg=COLORS["bg"])
        btn_frame.pack(fill="x")
        
        for text, cmd in [("📂 로그", self._open_logs), ("🔄 DNS 초기화", self._flush_dns), ("📝 도메인", self._manage_domains)]:
            tk.Button(
                btn_frame, text=text, command=cmd,
                bg=COLORS["surface"], fg=COLORS["fg"],
                font=("맑은 고딕", 9), relief="flat", padx=10, cursor="hand2"
            ).pack(side="left", padx=(0, 8))
    
    def _create_status_card(self, parent, title: str, value: str, color=None) -> tk.Frame:
        card = tk.Frame(parent, bg=COLORS["surface"], padx=15, pady=12)
        
        tk.Label(
            card, text=title, bg=COLORS["surface"], fg=COLORS["sub_text"],
            font=("맑은 고딕", 9)
        ).pack(anchor="w")
        
        value_label = tk.Label(
            card, text=value, bg=COLORS["surface"], 
            fg=color or COLORS["success"], font=("맑은 고딕", 11, "bold")
        )
        value_label.pack(anchor="w", pady=(4, 0))
        
        card._value_label = value_label
        return card
    
    def _update_card(self, card, text: str, color=None):
        if hasattr(card, '_value_label'):
            card._value_label.config(text=text)
            if color:
                card._value_label.config(fg=color)
    
    def _start_services(self):
        if self.settings.hide_layout:
            self.layout_hider.start()
        
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        
        threading.Thread(target=self._monitor_loop, daemon=True, name="Monitor").start()
    
    def _start_log_updates(self):
        """로그 큐에서 메시지를 가져와 UI에 표시"""
        def update():
            try:
                while True:
                    msg = self.log_queue.get_nowait()
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", msg + "\n")
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")
                    
                    # 최대 500줄 유지
                    lines = int(self.log_text.index('end-1c').split('.')[0])
                    if lines > 500:
                        self.log_text.config(state="normal")
                        self.log_text.delete("1.0", "100.0")
                        self.log_text.config(state="disabled")
            except queue.Empty:
                pass
            
            self._log_update_job = self.root.after(200, update)
        
        update()
    
    def _monitor_loop(self):
        while not self._is_quitting:
            try:
                # Hosts 상태
                ratio = self.hosts_mgr.get_status(DEFAULT_AD_DOMAINS)
                if ratio >= 1.0:
                    self._update_card(self.card_protect, "🛡️ 완전 보호", COLORS["success"])
                elif ratio > 0:
                    self._update_card(self.card_protect, f"⚠️ 부분 ({ratio*100:.0f}%)", COLORS["warning"])
                else:
                    self._update_card(self.card_protect, "❌ 미보호", COLORS["error"])
                
                # 카카오톡 프로세스
                if SystemManager.is_process_running("KakaoTalk"):
                    self._update_card(self.card_process, "💬 실행 중", COLORS["success"])
                else:
                    self._update_card(self.card_process, "💬 종료됨", COLORS["sub_text"])
                
            except Exception:
                pass
            
            time.sleep(2)
    
    def _on_close(self):
        if self.settings.minimize_to_tray and TRAY_AVAILABLE:
            self.hide_to_tray()
        else:
            self.quit_app()
    
    def hide_to_tray(self):
        self.root.withdraw()
        self.logger.info("트레이로 최소화")
    
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def quit_app(self):
        if self._is_quitting:
            return
        self._is_quitting = True
        
        self.layout_hider.stop()
        self.adfit_blocker.stop()
        if self.tray_manager:
            self.tray_manager.stop()
        
        if self._log_update_job:
            self.root.after_cancel(self._log_update_job)
        
        self.root.quit()
        self.root.destroy()
    
    def _smart_optimize(self):
        if not SystemManager.is_admin():
            Toast.show(self.root, "관리자 권한이 필요합니다", toast_type="warning")
            return
        
        # 도메인 로드
        domains = DEFAULT_AD_DOMAINS
        if os.path.exists(DOMAINS_FILE):
            try:
                with open(DOMAINS_FILE, 'r', encoding='utf-8') as f:
                    custom = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                if custom:
                    domains = custom
            except Exception:
                pass
        
        # 실행
        success = self.hosts_mgr.block(domains)
        SystemManager.flush_dns()
        restarted = SystemManager.restart_process("kakaotalk.exe")
        
        if success and restarted:
            Toast.show(self.root, "✅ 최적화 완료!", toast_type="success")
        elif success:
            Toast.show(self.root, "⚠️ 도메인 차단됨, 카톡 재시작 실패", toast_type="warning")
        else:
            Toast.show(self.root, "❌ 최적화 실패", toast_type="error")
    
    def _flush_dns(self):
        if SystemManager.flush_dns():
            Toast.show(self.root, "DNS 캐시 초기화 완료", toast_type="success")
    
    def _manage_domains(self):
        if os.path.exists(DOMAINS_FILE):
            os.startfile(DOMAINS_FILE)
        else:
            with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
                f.write("\n".join(DEFAULT_AD_DOMAINS))
            os.startfile(DOMAINS_FILE)
    
    def _open_logs(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
    
    def _save_settings(self):
        self.settings.minimize_to_tray = self.var_tray.get()
        self.settings.start_minimized = self.var_start_hidden.get()
        self.settings.hide_layout = self.var_hide_layout.get()
        self.settings.block_adfit = self.var_block_adfit.get()
        self.settings.save()
    
    def _toggle_autostart(self):
        enabled = self.var_autostart.get()
        if StartupManager.set_enabled(enabled):
            self.settings.auto_start = enabled
            self.settings.save()
            Toast.show(self.root, "자동 시작 " + ("등록" if enabled else "해제"), toast_type="success")
        else:
            self.var_autostart.set(not enabled)
            Toast.show(self.root, "자동 시작 설정 실패", toast_type="error")
    
    def _toggle_layout_hider(self):
        self._save_settings()
        if self.settings.hide_layout:
            self.layout_hider.start()
        else:
            self.layout_hider.stop()
    
    def _toggle_adfit(self):
        self._save_settings()
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        else:
            self.adfit_blocker.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 엔트리 포인트
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    start_minimized = "--minimized" in sys.argv
    
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(DEFAULT_AD_DOMAINS))
    
    root = tk.Tk()
    app = MainWindow(root, start_minimized=start_minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
