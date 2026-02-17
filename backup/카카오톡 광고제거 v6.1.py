# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v6.1 (Simplified & Fixed)
==================================================
- Simplified window detection using FindWindowEx iteration
- Fixed HiDPI font scaling
- Based on KakaoTalkAdGuard window detection logic
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
from typing import Optional, List
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ═══════════════════════════════════════════════════════════════════════════════
# 서드파티 라이브러리 (선택적)
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
# HiDPI 설정
# ═══════════════════════════════════════════════════════════════════════════════
def setup_hidpi():
    if platform.system() != "Windows":
        return 1.0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    # DPI 스케일 팩터 반환
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0

DPI_SCALE = setup_hidpi()


# ═══════════════════════════════════════════════════════════════════════════════
# 상수 및 설정
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "6.2.0"
APP_NAME = "KakaoTalk AdBlocker Pro"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "adblock_settings.json")
DOMAINS_FILE = os.path.join(BASE_DIR, "blocked_domains.txt")
LOG_FILE = os.path.join(BASE_DIR, "adblock.log")

# 폰트 크기 (기본 + HiDPI 대응)
FONT_LARGE = ("맑은 고딕", 13, "bold")
FONT_MEDIUM = ("맑은 고딕", 11)
FONT_SMALL = ("맑은 고딕", 10)
FONT_LOG = ("Consolas", 10)

COLORS = {
    "primary": "#FEE500",
    "primary_dark": "#E6CF00",
    "bg": "#FFFFFF",
    "fg": "#191919",
    "sub_text": "#757575",
    "success": "#4CAF50",
    "warning": "#FF9800",
    "error": "#F44336",
    "surface": "#F5F5F5",
    "log_bg": "#1E1E1E",
    "log_fg": "#D4D4D4",
}

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
# 로깅
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


def setup_logging():
    log_queue = queue.Queue(maxsize=500)
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        logger.handlers.clear()
    
    fmt = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    
    try:
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    
    qh = QueueHandler(log_queue)
    qh.setLevel(logging.DEBUG)
    qh.setFormatter(fmt)
    logger.addHandler(qh)
    
    return logger, log_queue


# ═══════════════════════════════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class AppSettings:
    auto_start: bool = False
    minimize_to_tray: bool = True
    start_minimized: bool = False
    hide_layout: bool = True
    block_adfit: bool = True
    
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
# Windows API (단순화)
# ═══════════════════════════════════════════════════════════════════════════════
class WinAPI:
    """단순화된 Windows API 래퍼 - FindWindowEx 반복 사용"""
    
    SW_HIDE = 0
    SW_SHOW = 5
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    
    def __init__(self):
        if platform.system() != "Windows":
            self.available = False
            return
        
        self.available = True
        self.user32 = ctypes.windll.user32
        
        # 함수 정의
        self.user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        self.user32.FindWindowW.restype = ctypes.c_void_p
        
        self.user32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
        self.user32.FindWindowExW.restype = ctypes.c_void_p
        
        self.user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        self.user32.GetClassNameW.restype = ctypes.c_int
        
        self.user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        
        self.user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.ShowWindow.restype = ctypes.c_bool
        
        self.user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        self.user32.IsWindowVisible.restype = ctypes.c_bool
        
        self.user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        self.user32.GetClientRect.restype = ctypes.c_bool
        
        self.user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, 
                                              ctypes.c_int, ctypes.c_int, 
                                              ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        self.user32.SetWindowPos.restype = ctypes.c_bool
    
    def find_window(self, class_name: str, window_name: str = None):
        if not self.available:
            return None
        hwnd = self.user32.FindWindowW(class_name, window_name)
        return hwnd if hwnd else None
    
    def find_window_ex(self, parent, child_after, class_name: str = None, window_name: str = None):
        if not self.available:
            return None
        hwnd = self.user32.FindWindowExW(parent, child_after, class_name, window_name)
        return hwnd if hwnd else None
    
    def get_class_name(self, hwnd) -> str:
        if not self.available or not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    
    def get_window_text(self, hwnd) -> str:
        if not self.available or not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        self.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value
    
    def show_window(self, hwnd, cmd: int):
        if self.available and hwnd:
            self.user32.ShowWindow(hwnd, cmd)
    
    def is_visible(self, hwnd) -> bool:
        if not self.available or not hwnd:
            return False
        return bool(self.user32.IsWindowVisible(hwnd))
    
    def get_client_size(self, hwnd):
        if not self.available or not hwnd:
            return (0, 0)
        rect = ctypes.wintypes.RECT()
        if self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return (rect.right - rect.left, rect.bottom - rect.top)
        return (0, 0)
    
    def set_size(self, hwnd, width: int, height: int):
        if self.available and hwnd:
            flags = self.SWP_NOMOVE | self.SWP_NOZORDER | self.SWP_NOACTIVATE
            self.user32.SetWindowPos(hwnd, None, 0, 0, width, height, flags)
    
    def find_all_children(self, parent) -> list:
        """FindWindowEx를 반복하여 모든 자식 윈도우 찾기"""
        children = []
        if not self.available or not parent:
            return children
        
        child = None
        while True:
            child = self.find_window_ex(parent, child, None, None)
            if not child:
                break
            children.append(child)
        return children


# ═══════════════════════════════════════════════════════════════════════════════
# 광고 레이아웃 숨김 (단순화된 버전)
# ═══════════════════════════════════════════════════════════════════════════════
class AdLayoutHider:
    """
    단순화된 광고 레이아웃 숨김
    - FindWindowEx 반복으로 모든 자식 윈도우 탐색
    - 콜백 없이 직접 반복문 사용
    """
    
    MAIN_CLASS = "EVA_Window_Dblclk"
    MAIN_TITLES = ["카카오톡", "カカオトーク", "KakaoTalk"]
    AD_CLASS_PREFIX = "Chrome_WidgetWin_"
    CHILD_CLASS = "EVA_ChildWindow"
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.api = WinAPI()
        self.active = False
        self.thread = None
        self._last_main_hwnd = None
        self._hidden_count = 0
    
    def start(self):
        if not self.api.available or self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.logger.info("광고 레이아웃 숨김 시작")
    
    def stop(self):
        self.active = False
        self.logger.info("광고 레이아웃 숨김 중지")
    
    @property
    def hidden_count(self) -> int:
        return self._hidden_count
    
    def _loop(self):
        while self.active:
            try:
                self._process()
            except Exception as e:
                self.logger.debug(f"처리 오류: {e}")
            time.sleep(0.1)
    
    def _process(self):
        # 메인 윈도우 찾기
        main_hwnd = None
        for title in self.MAIN_TITLES:
            main_hwnd = self.api.find_window(self.MAIN_CLASS, title)
            if main_hwnd:
                break
        
        if not main_hwnd:
            # 타이틀 없이 클래스만으로 시도
            main_hwnd = self.api.find_window(self.MAIN_CLASS, None)
        
        if not main_hwnd:
            self._last_main_hwnd = None
            return
        
        if main_hwnd != self._last_main_hwnd:
            self._last_main_hwnd = main_hwnd
            self.logger.info(f"카카오톡 발견: {hex(main_hwnd)}")
        
        # 메인 윈도우 크기
        width, height = self.api.get_client_size(main_hwnd)
        if width == 0 or height == 0:
            return
        
        # 자식 윈도우 처리
        self._process_children(main_hwnd, width, height)
    
    def _process_children(self, parent, parent_width: int, parent_height: int):
        """자식 윈도우 순회 및 처리"""
        hidden = 0
        children = self.api.find_all_children(parent)
        
        for child in children:
            class_name = self.api.get_class_name(child)
            window_text = self.api.get_window_text(child)
            
            # Chrome 광고 숨기기
            if class_name.startswith(self.AD_CLASS_PREFIX):
                if self.api.is_visible(child):
                    self.api.show_window(child, WinAPI.SW_HIDE)
                    hidden += 1
                    self.logger.debug(f"광고 숨김: {class_name}")
            
            # EVA_ChildWindow 처리
            elif class_name == self.CHILD_CLASS:
                if window_text.startswith("OnlineMainView"):
                    # 메인 뷰 리사이징 (상단 여백 32 제외)
                    new_height = parent_height - 32
                    if new_height > 100:
                        self.api.set_size(child, parent_width, new_height)
                
                elif window_text.startswith("LockModeView"):
                    self.api.set_size(child, parent_width, parent_height)
            
            # 재귀적으로 처리
            hidden += self._process_children_recursive(child)
        
        self._hidden_count = hidden
    
    def _process_children_recursive(self, parent) -> int:
        """재귀적으로 Chrome 광고 탐색"""
        hidden = 0
        children = self.api.find_all_children(parent)
        
        for child in children:
            class_name = self.api.get_class_name(child)
            
            if class_name.startswith(self.AD_CLASS_PREFIX):
                if self.api.is_visible(child):
                    self.api.show_window(child, WinAPI.SW_HIDE)
                    hidden += 1
            
            # 더 깊은 계층 탐색
            hidden += self._process_children_recursive(child)
        
        return hidden


# ═══════════════════════════════════════════════════════════════════════════════
# AdFit 레지스트리 차단
# ═══════════════════════════════════════════════════════════════════════════════
class AdFitBlocker:
    ADFIT_KEY = r"SOFTWARE\Kakao\AdFit"
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.active = False
        self.thread = None
    
    def start(self):
        if self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.logger.info("AdFit 레지스트리 차단 시작")
    
    def stop(self):
        self.active = False
    
    def _loop(self):
        while self.active:
            try:
                self._update_lud()
            except Exception:
                pass
            time.sleep(5)
    
    def _update_lud(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.ADFIT_KEY, 0, 
                                 winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS)
        except FileNotFoundError:
            return
        
        try:
            idx = 0
            current_time = str(int(time.time()))
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, idx)
                    subkey_path = f"{self.ADFIT_KEY}\\{subkey_name}"
                    try:
                        sk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey_path, 0, winreg.KEY_WRITE)
                        winreg.SetValueEx(sk, "LUD", 0, winreg.REG_SZ, current_time)
                        winreg.CloseKey(sk)
                    except Exception:
                        pass
                    idx += 1
                except OSError:
                    break
        finally:
            winreg.CloseKey(key)


# ═══════════════════════════════════════════════════════════════════════════════
# 시스템 매니저
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
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                " ".join(f'"{a}"' for a in sys.argv), None, 1
            )
            sys.exit(0)
        except Exception:
            pass

    @staticmethod
    def flush_dns() -> bool:
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, 
                          creationflags=0x08000000)
            return True
        except Exception:
            return False

    @staticmethod
    def is_process_running(name: str) -> bool:
        # psutil 사용
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name']):
                    if name.lower() in (p.info['name'] or '').lower():
                        return True
                return False
            except Exception:
                pass
        
        # 폴백: tasklist 명령 사용
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {name}.exe', '/NH'],
                capture_output=True, text=True, creationflags=0x08000000
            )
            return name.lower() in result.stdout.lower()
        except Exception:
            pass
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
        
        try:
            subprocess.run(["taskkill", "/f", "/im", name], capture_output=True,
                          creationflags=0x08000000)
            time.sleep(1.5)
            
            if exe_path and os.path.exists(exe_path):
                os.startfile(exe_path)
                return True
            
            for path in [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
            ]:
                if os.path.exists(path):
                    os.startfile(path)
                    return True
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 시작프로그램 매니저
# ═══════════════════════════════════════════════════════════════════════════════
class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerPro"
    
    @staticmethod
    def is_enabled() -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, StartupManager.NAME)
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
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    exe = sys.executable
                    if exe.endswith(("python.exe", "pythonw.exe")):
                        script = os.path.abspath(sys.argv[0])
                        path = f'"{exe}" "{script}" --minimized'
                    else:
                        path = f'"{exe}" --minimized'
                    winreg.SetValueEx(key, StartupManager.NAME, 0, winreg.REG_SZ, path)
                else:
                    try:
                        winreg.DeleteValue(key, StartupManager.NAME)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Hosts 매니저
# ═══════════════════════════════════════════════════════════════════════════════
class HostsManager:
    PATH = r"C:\Windows\System32\drivers\etc\hosts"
    START = "# [KakaoTalk AdBlock Start]"
    END = "# [KakaoTalk AdBlock End]"

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def block(self, domains: List[str]) -> bool:
        try:
            with open(self.PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"Hosts 읽기 실패: {e}")
            return False
        
        lines = []
        skip = False
        for line in content.splitlines():
            if self.START in line:
                skip = True
                continue
            if self.END in line:
                skip = False
                continue
            if not skip:
                is_ad = any(d in line and ("0.0.0.0" in line or "127.0.0.1" in line) for d in domains)
                if not is_ad:
                    lines.append(line)
        
        new = "\n".join(lines).strip() + "\n\n"
        new += f"{self.START}\n"
        new += f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        for d in domains:
            new += f"0.0.0.0 {d}\n"
        new += f"{self.END}\n"
        
        try:
            os.chmod(self.PATH, 0o777)
            with open(self.PATH, 'w', encoding='utf-8') as f:
                f.write(new)
            self.logger.info(f"{len(domains)}개 도메인 차단")
            return True
        except Exception as e:
            self.logger.error(f"Hosts 쓰기 실패: {e}")
            return False

    def get_status(self, domains: List[str]) -> float:
        try:
            with open(self.PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            count = sum(1 for d in domains if f"0.0.0.0 {d}" in content or f"127.0.0.1 {d}" in content)
            return count / len(domains) if domains else 0.0
        except Exception:
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 트레이 아이콘
# ═══════════════════════════════════════════════════════════════════════════════
class TrayManager:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self._running = False
    
    def create_icon(self):
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        points = [(32, 4), (60, 14), (60, 32), (32, 60), (4, 32), (4, 14)]
        draw.polygon(points, fill=(254, 229, 0, 255), outline=(200, 180, 0, 255))
        draw.line([(18, 32), (26, 42), (46, 20)], fill=(25, 25, 25, 255), width=5)
        return img
    
    def setup(self):
        if not TRAY_AVAILABLE:
            return
        menu = pystray.Menu(
            pystray.MenuItem(f"{APP_NAME} v{VERSION}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("열기", lambda: self._show()),
            pystray.MenuItem("종료", lambda: self._quit()),
        )
        self.icon = pystray.Icon("KakaoTalkAdBlocker", self.create_icon(), APP_NAME, menu)
    
    def start(self):
        if not TRAY_AVAILABLE or self._running:
            return
        self._running = True
        threading.Thread(target=lambda: self.icon.run(), daemon=True).start()
    
    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        self._running = False
    
    def _show(self):
        self.app.root.after(0, self.app.show_window)
    
    def _quit(self):
        self.stop()
        self.app.root.after(0, self.app.quit_app)


# ═══════════════════════════════════════════════════════════════════════════════
# Toast 알림
# ═══════════════════════════════════════════════════════════════════════════════
class Toast:
    _toasts = []
    
    @classmethod
    def show(cls, parent, msg: str, duration: int = 3000, type_: str = "info"):
        t = tk.Toplevel(parent)
        t.overrideredirect(True)
        t.attributes('-topmost', True)
        
        colors = {"info": COLORS["primary"], "success": COLORS["success"],
                  "warning": COLORS["warning"], "error": COLORS["error"]}
        bg = colors.get(type_, COLORS["primary"])
        
        f = tk.Frame(t, bg=bg, padx=15, pady=10)
        f.pack(fill="both", expand=True)
        tk.Label(f, text=msg, bg=bg, fg=COLORS["fg"], font=FONT_SMALL, wraplength=300).pack()
        
        t.update_idletasks()
        sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
        tw, th = t.winfo_width(), t.winfo_height()
        y_off = sum(x.winfo_height() + 10 for x in cls._toasts if x.winfo_exists())
        t.geometry(f"+{sw-tw-20}+{sh-th-60-y_off}")
        cls._toasts.append(t)
        
        def destroy():
            if t in cls._toasts:
                cls._toasts.remove(t)
            t.destroy()
        t.after(duration, destroy)


# ═══════════════════════════════════════════════════════════════════════════════
# 메인 윈도우
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk, minimized: bool = False):
        self.root = root
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        
        self.hosts_mgr = HostsManager(self.logger)
        self.layout_hider = AdLayoutHider(self.logger)
        self.adfit_blocker = AdFitBlocker(self.logger)
        self.tray_manager = None
        
        self._quitting = False
        self._log_job = None
        
        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._start_services()
        self._start_log_updates()
        
        if minimized or self.settings.start_minimized:
            self.root.after(100, self.hide_to_tray)
    
    def _setup_window(self):
        self.root.title(APP_NAME)
        # 원래 UI 크기 사용 (DPI 스케일링 제거)
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
        # 헤더
        header = tk.Frame(self.root, bg=COLORS["primary"], height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text="🛡️", bg=COLORS["primary"], 
                font=("Segoe UI Emoji", 22)).pack(side="left", padx=(20, 10))
        
        tf = tk.Frame(header, bg=COLORS["primary"])
        tf.pack(side="left", fill="y", pady=12)
        tk.Label(tf, text=APP_NAME, bg=COLORS["primary"], fg=COLORS["fg"], 
                font=FONT_LARGE).pack(anchor="w")
        tk.Label(tf, text=f"v{VERSION}", bg=COLORS["primary"], fg="#555", 
                font=FONT_SMALL).pack(anchor="w")
        
        # 컨텐츠
        container = tk.Frame(self.root, bg=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # 상태 카드
        sf = tk.Frame(container, bg=COLORS["bg"])
        sf.pack(fill="x", pady=(0, 15))
        
        self.card_protect = self._card(sf, "보호 상태", "확인 중...")
        self.card_protect.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.card_process = self._card(sf, "카카오톡", "감지 안됨", COLORS["sub_text"])
        self.card_process.pack(side="left", fill="x", expand=True)
        
        # 스마트 최적화
        tk.Button(container, text="✨ 스마트 최적화", command=self._optimize,
                 bg=COLORS["primary"], fg=COLORS["fg"], activebackground=COLORS["primary_dark"],
                 font=FONT_LARGE, relief="flat", cursor="hand2", 
                 height=2).pack(fill="x", pady=(0, 15))
        
        # 설정
        stf = tk.LabelFrame(container, text="설정", bg=COLORS["bg"], fg=COLORS["sub_text"],
                           font=FONT_MEDIUM, padx=15, pady=10)
        stf.pack(fill="x", pady=(0, 15))
        
        self.var_autostart = tk.BooleanVar(value=StartupManager.is_enabled())
        self.var_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.var_hidden = tk.BooleanVar(value=self.settings.start_minimized)
        self.var_layout = tk.BooleanVar(value=self.settings.hide_layout)
        self.var_adfit = tk.BooleanVar(value=self.settings.block_adfit)
        
        for text, var, cmd in [
            ("Windows 시작 시 자동 실행", self.var_autostart, self._toggle_autostart),
            ("닫을 때 트레이로 최소화", self.var_tray, self._save),
            ("시작 시 트레이로 최소화", self.var_hidden, self._save),
            ("광고 레이아웃 자동 제거", self.var_layout, self._toggle_layout),
            ("팝업 광고 차단 (AdFit)", self.var_adfit, self._toggle_adfit),
        ]:
            tk.Checkbutton(stf, text=text, variable=var, command=cmd,
                          bg=COLORS["bg"], activebackground=COLORS["bg"],
                          font=FONT_MEDIUM, anchor="w").pack(fill="x", pady=2)
        
        # 로그
        lf = tk.LabelFrame(container, text="실시간 로그", bg=COLORS["bg"], fg=COLORS["sub_text"],
                          font=FONT_MEDIUM, padx=10, pady=10)
        lf.pack(fill="both", expand=True, pady=(0, 15))
        
        self.log_text = scrolledtext.ScrolledText(lf, bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                                  font=FONT_LOG, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        
        # 하단 버튼
        bf = tk.Frame(container, bg=COLORS["bg"])
        bf.pack(fill="x")
        for text, cmd in [("📂 로그", self._open_log), ("🔄 DNS", self._flush_dns), ("📝 도메인", self._domains)]:
            tk.Button(bf, text=text, command=cmd, bg=COLORS["surface"], fg=COLORS["fg"],
                     font=FONT_SMALL, relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(0, 8))
    
    def _card(self, parent, title: str, value: str, color=None):
        c = tk.Frame(parent, bg=COLORS["surface"], padx=int(15 * DPI_SCALE), pady=int(12 * DPI_SCALE))
        tk.Label(c, text=title, bg=COLORS["surface"], fg=COLORS["sub_text"], font=FONT_SMALL).pack(anchor="w")
        lbl = tk.Label(c, text=value, bg=COLORS["surface"], fg=color or COLORS["success"], font=FONT_MEDIUM)
        lbl.pack(anchor="w", pady=(4, 0))
        c._lbl = lbl
        return c
    
    def _update_card(self, card, text: str, color=None):
        if hasattr(card, '_lbl'):
            card._lbl.config(text=text)
            if color:
                card._lbl.config(fg=color)
    
    def _start_services(self):
        if self.settings.hide_layout:
            self.layout_hider.start()
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        threading.Thread(target=self._monitor, daemon=True).start()
    
    def _start_log_updates(self):
        def update():
            try:
                while True:
                    msg = self.log_queue.get_nowait()
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", msg + "\n")
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")
                    lines = int(self.log_text.index('end-1c').split('.')[0])
                    if lines > 300:
                        self.log_text.config(state="normal")
                        self.log_text.delete("1.0", "50.0")
                        self.log_text.config(state="disabled")
            except queue.Empty:
                pass
            self._log_job = self.root.after(200, update)
        update()
    
    def _monitor(self):
        while not self._quitting:
            try:
                ratio = self.hosts_mgr.get_status(DEFAULT_AD_DOMAINS)
                if ratio >= 1.0:
                    self._update_card(self.card_protect, "🛡️ 완전 보호", COLORS["success"])
                elif ratio > 0:
                    self._update_card(self.card_protect, f"⚠️ 부분 ({ratio*100:.0f}%)", COLORS["warning"])
                else:
                    self._update_card(self.card_protect, "❌ 미보호", COLORS["error"])
                
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
        if self._quitting:
            return
        self._quitting = True
        self.layout_hider.stop()
        self.adfit_blocker.stop()
        if self.tray_manager:
            self.tray_manager.stop()
        if self._log_job:
            self.root.after_cancel(self._log_job)
        self.root.quit()
        self.root.destroy()
    
    def _optimize(self):
        if not SystemManager.is_admin():
            Toast.show(self.root, "관리자 권한 필요", type_="warning")
            return
        
        domains = DEFAULT_AD_DOMAINS
        if os.path.exists(DOMAINS_FILE):
            try:
                with open(DOMAINS_FILE, 'r', encoding='utf-8') as f:
                    custom = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                if custom:
                    domains = custom
            except Exception:
                pass
        
        ok = self.hosts_mgr.block(domains)
        SystemManager.flush_dns()
        restarted = SystemManager.restart_process("kakaotalk.exe")
        
        if ok and restarted:
            Toast.show(self.root, "✅ 최적화 완료!", type_="success")
        elif ok:
            Toast.show(self.root, "⚠️ 차단됨, 카톡 재시작 실패", type_="warning")
        else:
            Toast.show(self.root, "❌ 최적화 실패", type_="error")
    
    def _flush_dns(self):
        if SystemManager.flush_dns():
            Toast.show(self.root, "DNS 초기화 완료", type_="success")
    
    def _domains(self):
        if not os.path.exists(DOMAINS_FILE):
            with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
                f.write("\n".join(DEFAULT_AD_DOMAINS))
        os.startfile(DOMAINS_FILE)
    
    def _open_log(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
    
    def _save(self):
        self.settings.minimize_to_tray = self.var_tray.get()
        self.settings.start_minimized = self.var_hidden.get()
        self.settings.hide_layout = self.var_layout.get()
        self.settings.block_adfit = self.var_adfit.get()
        self.settings.save()
    
    def _toggle_autostart(self):
        enabled = self.var_autostart.get()
        if StartupManager.set_enabled(enabled):
            self.settings.auto_start = enabled
            self.settings.save()
            Toast.show(self.root, "자동 시작 " + ("등록" if enabled else "해제"), type_="success")
        else:
            self.var_autostart.set(not enabled)
            Toast.show(self.root, "자동 시작 설정 실패", type_="error")
    
    def _toggle_layout(self):
        self._save()
        if self.settings.hide_layout:
            self.layout_hider.start()
        else:
            self.layout_hider.stop()
    
    def _toggle_adfit(self):
        self._save()
        if self.settings.block_adfit:
            self.adfit_blocker.start()
        else:
            self.adfit_blocker.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 엔트리 포인트
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    minimized = "--minimized" in sys.argv
    
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(DEFAULT_AD_DOMAINS))
    
    root = tk.Tk()
    MainWindow(root, minimized=minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
