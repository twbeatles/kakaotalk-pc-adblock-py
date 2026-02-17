# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v5.1 (Enhanced)
=====================================
- Modern UI/UX (Flat Design, Kakao Theme)
- Fixed Ad Layout Hiding (Window Class Name Fix)
- Windows Startup Registration
- System Tray Minimization
- Enhanced Stability & Performance
"""

import os
import sys
import ctypes
import ctypes.wintypes
import shutil
import json
import threading
import time
import logging
import queue
import webbrowser
import platform
import subprocess
import winreg
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from enum import Enum, auto
from contextlib import contextmanager

import tkinter as tk
from tkinter import ttk, messagebox, font, filedialog

# 서드파티 라이브러리 (선택적)
try:
    import psutil
except ImportError:
    psutil = None

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# 상수 및 설정
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "5.1.0"
APP_NAME = "KakaoTalk AdBlocker Pro"
GITHUB_REPO = "blurfx/KakaoTalkAdBlock"

# 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "adblock_settings.json")
DOMAINS_FILE = os.path.join(BASE_DIR, "blocked_domains.txt")
LOG_FILE = os.path.join(BASE_DIR, "adblock.log")

# 색상 테마 (카카오 스타일)
COLORS = {
    "primary": "#FEE500",       # 카카오 옐로우
    "primary_dark": "#FDD835",  # 눌렀을 때
    "bg": "#FFFFFF",           # 배경색
    "fg": "#191919",           # 기본 텍스트
    "sub_text": "#757575",     # 보조 텍스트
    "success": "#2E7D32",      # 성공 초록
    "warning": "#FF6F00",      # 경고 주황
    "error": "#C62828",        # 에러 빨강
    "surface": "#F5F5F5",      # 카드 배경
    "border": "#E0E0E0"        # 테두리
}

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

# 카카오톡 윈도우 클래스 및 컨트롤 이름
KAKAO_WINDOW_CLASSES = [
    "EVA_Window_Class__",  # 최신 카카오톡
    "EVA_Window",          # 구버전 호환
    "EVA_ChildWindow",
]

AD_VIEW_PATTERNS = [
    "BannerAdView",
    "AdView",
    "BannerWrap",
    "AdContainer",
    "ad_banner",
]

MAIN_VIEW_PATTERNS = [
    "OnlineMainView",
    "MainView",
    "ContactListView",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 로깅 시스템
# ═══════════════════════════════════════════════════════════════════════════════
class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

def setup_logging() -> tuple[logging.Logger, queue.Queue]:
    log_queue = queue.Queue()
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.DEBUG)
    
    # 포맷터
    formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    
    # 파일 핸들러
    try:
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass
    
    # 큐 핸들러 (GUI용)
    qh = QueueHandler(log_queue)
    qh.setLevel(logging.INFO)
    qh.setFormatter(formatter)
    logger.addHandler(qh)
    
    return logger, log_queue


# ═══════════════════════════════════════════════════════════════════════════════
# 비즈니스 로직 (Core Logic)
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class AppSettings:
    auto_start: bool = False
    minimize_to_tray: bool = True
    realtime_protection: bool = True
    hide_layout: bool = True
    start_minimized: bool = False  # 시작 시 트레이로 바로
    theme: str = "light"
    
    @classmethod
    def load(cls):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 호환성: 새 필드가 없으면 기본값 사용
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


class StartupManager:
    """Windows 시작프로그램 등록 관리"""
    STARTUP_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "KakaoTalkAdBlockerPro"
    
    @staticmethod
    def is_startup_enabled() -> bool:
        """시작프로그램 등록 여부 확인"""
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
    def set_startup_enabled(enable: bool) -> bool:
        """시작프로그램 등록/해제"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    # 현재 실행 파일 경로
                    exe_path = sys.executable
                    if exe_path.endswith("python.exe") or exe_path.endswith("pythonw.exe"):
                        # 스크립트로 실행 중인 경우
                        script_path = os.path.abspath(sys.argv[0])
                        exe_path = f'"{exe_path}" "{script_path}"'
                    else:
                        exe_path = f'"{exe_path}"'
                    
                    # --minimized 인자 추가
                    exe_path += " --minimized"
                    winreg.SetValueEx(key, StartupManager.APP_NAME, 0, winreg.REG_SZ, exe_path)
                else:
                    try:
                        winreg.DeleteValue(key, StartupManager.APP_NAME)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            return False


class SystemManager:
    """시스템 레벨 작업 관리 (Process, DNS, Admin 등)"""
    
    @staticmethod
    def is_admin() -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @staticmethod
    def run_as_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
            sys.exit(0)
        except Exception:
            pass

    @staticmethod
    def flush_dns() -> bool:
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=0x08000000)
            return True
        except Exception:
            return False

    @staticmethod
    def is_process_running(process_name: str) -> bool:
        if not psutil:
            return False
        try:
            for p in psutil.process_iter(['name']):
                if process_name.lower() in (p.info['name'] or '').lower():
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def restart_process(process_name: str, exe_path: str = None) -> bool:
        if not exe_path and psutil:
            try:
                for p in psutil.process_iter(['name', 'exe']):
                    if process_name.lower() in (p.info['name'] or '').lower():
                        exe_path = p.info['exe']
                        break
            except Exception:
                pass

        try:
            subprocess.run(["taskkill", "/f", "/im", process_name], capture_output=True, creationflags=0x08000000)
            time.sleep(1.5)
            
            if exe_path and os.path.exists(exe_path):
                os.startfile(exe_path)
                return True
            
            if platform.system() == "Windows":
                paths = [
                    os.path.join(os.environ.get('PROGRAMFILES', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                    os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe'),
                ]
                for p in paths:
                    if os.path.exists(p):
                        os.startfile(p)
                        return True
        except Exception:
            pass
        return False


class HostsManager:
    """Hosts 파일 조작 담당"""
    HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
    MARKER_START = "# [KakaoTalk AdBlock Start]"
    MARKER_END = "# [KakaoTalk AdBlock End]"

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _read_hosts(self) -> str:
        try:
            with open(self.HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"Hosts 읽기 실패: {e}")
            return ""

    def _write_hosts(self, content: str) -> bool:
        try:
            os.chmod(self.HOSTS_PATH, 0o777)
            with open(self.HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            self.logger.error(f"Hosts 쓰기 실패: {e}")
            return False

    def block(self, domains: List[str]) -> bool:
        content = self._read_hosts()
        lines = [line for line in content.splitlines() if self.MARKER_START not in line and self.MARKER_END not in line]
        clean_lines = []
        for line in lines:
            is_target = False
            for d in domains:
                if d in line and ("127.0.0.1" in line or "0.0.0.0" in line):
                    is_target = True
                    break
            if not is_target:
                clean_lines.append(line)
        
        new_content = "\n".join(clean_lines).strip() + "\n\n"
        new_content += f"{self.MARKER_START}\n"
        new_content += f"# Updated: {datetime.now()}\n"
        for d in domains:
            new_content += f"0.0.0.0 {d}\n"
        new_content += f"{self.MARKER_END}\n"
        
        if self._write_hosts(new_content):
            self.logger.info(f"{len(domains)}개 도메인 차단 적용 완료")
            return True
        return False

    def unblock(self) -> bool:
        content = self._read_hosts()
        lines = content.splitlines()
        new_lines = []
        skip = False
        for line in lines:
            if self.MARKER_START in line:
                skip = True
            if not skip:
                new_lines.append(line)
            if self.MARKER_END in line:
                skip = False
        
        if self._write_hosts("\n".join(new_lines)):
            self.logger.info("광고 차단 해제 완료")
            return True
        return False

    def get_status(self, domains: List[str]) -> float:
        """차단율 반환 (0.0 ~ 1.0)"""
        content = self._read_hosts()
        if not content:
            return 0.0
        count = 0
        for d in domains:
            if f"0.0.0.0 {d}" in content or f"127.0.0.1 {d}" in content:
                count += 1
        return count / len(domains) if domains else 0.0


class AdLayoutHider:
    """Windows API를 이용한 광고 영역 숨김 및 리사이징 (Enhanced)"""
    
    # Windows API 상수
    SW_HIDE = 0
    SW_SHOW = 5
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.active = False
        self.thread = None
        self._setup_winapi()
        
    def _setup_winapi(self):
        """Windows API 함수 설정"""
        if platform.system() != "Windows":
            self.user32 = None
            return
            
        self.user32 = ctypes.windll.user32
        
        # EnumWindows 콜백 타입 정의
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        
        # 함수 시그니처 명시
        self.user32.EnumWindows.argtypes = [self.WNDENUMPROC, ctypes.c_void_p]
        self.user32.EnumWindows.restype = ctypes.c_bool
        
        self.user32.EnumChildWindows.argtypes = [ctypes.c_void_p, self.WNDENUMPROC, ctypes.c_void_p]
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
        
        self.user32.ScreenToClient.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.POINT)]
        self.user32.ScreenToClient.restype = ctypes.c_bool

    def start(self):
        if not self.user32 or self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.logger.info("레이아웃 숨김 기능 시작")

    def stop(self):
        self.active = False
        self.logger.info("레이아웃 숨김 기능 중지")

    def _loop(self):
        while self.active:
            try:
                self._scan_and_fix()
                time.sleep(0.5)  # 0.5초마다 스캔 (더 반응성 좋게)
            except Exception as e:
                self.logger.debug(f"스캔 중 오류: {e}")
                time.sleep(1)

    def _scan_and_fix(self):
        """모든 윈도우를 스캔하여 카카오톡 윈도우 찾기"""
        found_windows = []
        
        def enum_cb(hwnd, _):
            try:
                class_name = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(hwnd, class_name, 256)
                
                # 카카오톡 윈도우 클래스 확인
                for kakao_class in KAKAO_WINDOW_CLASSES:
                    if class_name.value.startswith(kakao_class.rstrip('_')):
                        found_windows.append(hwnd)
                        break
            except Exception:
                pass
            return True
        
        callback = self.WNDENUMPROC(enum_cb)
        self.user32.EnumWindows(callback, 0)
        
        # 발견된 각 윈도우 처리
        for hwnd in found_windows:
            self._process_kakao_window(hwnd)

    def _process_kakao_window(self, parent_hwnd):
        """카카오톡 윈도우의 하위 컨트롤 처리"""
        ad_views = []
        main_views = []
        
        def child_cb(hwnd, _):
            try:
                # 클래스 이름 확인
                class_name = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(hwnd, class_name, 256)
                
                # 윈도우 텍스트 확인
                length = self.user32.GetWindowTextLengthW(hwnd)
                text = ""
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, buf, length + 1)
                    text = buf.value
                
                # 광고 뷰 확인 (텍스트 또는 클래스명으로)
                is_ad = False
                for pattern in AD_VIEW_PATTERNS:
                    if pattern.lower() in text.lower() or pattern.lower() in class_name.value.lower():
                        is_ad = True
                        break
                
                if is_ad:
                    ad_views.append(hwnd)
                
                # 메인 뷰 확인
                for pattern in MAIN_VIEW_PATTERNS:
                    if pattern.lower() in text.lower() or pattern.lower() in class_name.value.lower():
                        main_views.append((hwnd, parent_hwnd))
                        break
                        
            except Exception:
                pass
            return True
        
        callback = self.WNDENUMPROC(child_cb)
        self.user32.EnumChildWindows(parent_hwnd, callback, 0)
        
        # 광고 뷰 숨기기
        for hwnd in ad_views:
            if self.user32.IsWindowVisible(hwnd):
                self.user32.ShowWindow(hwnd, self.SW_HIDE)
                self.logger.debug(f"광고 뷰 숨김: {hwnd}")
        
        # 메인 뷰 리사이징
        for hwnd, parent in main_views:
            self._resize_main_view(hwnd, parent)

    def _resize_main_view(self, hwnd, parent_hwnd):
        """메인 뷰를 부모 크기에 맞게 리사이징"""
        try:
            # 부모 클라이언트 영역
            pr = ctypes.wintypes.RECT()
            if not self.user32.GetClientRect(parent_hwnd, ctypes.byref(pr)):
                return
            p_height = pr.bottom - pr.top
            p_width = pr.right - pr.left

            # 자식 현재 위치
            cr = ctypes.wintypes.RECT()
            if not self.user32.GetWindowRect(hwnd, ctypes.byref(cr)):
                return
            
            pt = ctypes.wintypes.POINT(cr.left, cr.top)
            self.user32.ScreenToClient(parent_hwnd, ctypes.byref(pt))
            
            # 목표 크기
            target_h = p_height - pt.y
            target_w = p_width - pt.x
            
            curr_h = cr.bottom - cr.top
            curr_w = cr.right - cr.left

            # 5픽셀 이상 차이날 때만 리사이즈 (깜빡임 방지)
            if (abs(target_h - curr_h) > 5 or abs(target_w - curr_w) > 5) and target_h > 100:
                self.user32.SetWindowPos(
                    hwnd, None, 0, 0, target_w, target_h,
                    self.SWP_NOMOVE | self.SWP_NOZORDER | self.SWP_NOACTIVATE
                )
                self.logger.debug(f"메인 뷰 리사이징: {curr_h} -> {target_h}")
        except Exception as e:
            self.logger.debug(f"리사이징 오류: {e}")


class TrayManager:
    """시스템 트레이 아이콘 관리"""
    
    def __init__(self, app: 'MainWindow'):
        self.app = app
        self.icon = None
        self._running = False
        
    def create_icon_image(self) -> 'Image.Image':
        """트레이 아이콘 이미지 생성 (노란 방패)"""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 방패 모양 그리기
        shield_color = (254, 229, 0)  # 카카오 옐로우
        
        # 방패 외곽선
        points = [
            (size//2, 5),           # 상단 중앙
            (size-5, 15),           # 우측 상단
            (size-5, size//2),      # 우측 중앙
            (size//2, size-5),      # 하단 중앙
            (5, size//2),           # 좌측 중앙
            (5, 15),                # 좌측 상단
        ]
        draw.polygon(points, fill=shield_color, outline=(200, 180, 0))
        
        # 체크마크
        check_color = (25, 25, 25)
        draw.line([(20, 32), (28, 42), (44, 22)], fill=check_color, width=4)
        
        return image
    
    def setup(self):
        """트레이 아이콘 설정"""
        if not TRAY_AVAILABLE:
            return
            
        image = self.create_icon_image()
        
        menu = pystray.Menu(
            pystray.MenuItem(f"🛡️ {APP_NAME} v{VERSION}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("열기", self._on_show),
            pystray.MenuItem("종료", self._on_quit),
        )
        
        self.icon = pystray.Icon(
            name="KakaoTalkAdBlocker",
            icon=image,
            title=APP_NAME,
            menu=menu,
        )
        
        # 더블클릭 시 창 열기
        self.icon.on_double_click = lambda: self._on_show(None, None)
        
    def start(self):
        """트레이 아이콘 시작 (백그라운드 스레드)"""
        if not TRAY_AVAILABLE or self._running:
            return
            
        self._running = True
        threading.Thread(target=self._run_tray, daemon=True).start()
        
    def _run_tray(self):
        """트레이 아이콘 실행"""
        try:
            self.icon.run()
        except Exception as e:
            self.app.logger.error(f"트레이 아이콘 오류: {e}")
        finally:
            self._running = False
    
    def stop(self):
        """트레이 아이콘 중지"""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        self._running = False
    
    def _on_show(self, icon, item):
        """창 표시"""
        self.app.root.after(0, self.app.show_window)
    
    def _on_quit(self, icon, item):
        """프로그램 종료"""
        self.stop()
        self.app.root.after(0, self.app.quit_app)


# ═══════════════════════════════════════════════════════════════════════════════
# UI 컴포넌트 (Modern UI)
# ═══════════════════════════════════════════════════════════════════════════════
class ModernButton(tk.Canvas):
    """둥근 모서리와 호버 효과가 있는 커스텀 버튼"""
    def __init__(self, parent, text, command=None, width=120, height=40, 
                 bg_color=COLORS["primary"], fg_color=COLORS["fg"], hover_color=COLORS["primary_dark"]):
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0)
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text = text
        self.fg_color = fg_color
        
        self.rect = self.create_rounded_rect(2, 2, width-2, height-2, 10, fill=bg_color, outline="")
        self.label = self.create_text(width/2, height/2, text=text, fill=fg_color, font=("맑은 고딕", 10, "bold"))
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", self._on_release)

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y1+r, x2, y2-r, x2, y2-r, x2, y2, x2-r, y2, x2-r, y2, x1+r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y2-r, x1, y1+r, x1, y1+r, x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def _on_enter(self, e):
        self.itemconfig(self.rect, fill=self.hover_color)
        self.config(cursor="hand2")

    def _on_leave(self, e):
        self.itemconfig(self.rect, fill=self.bg_color)
        self.config(cursor="")

    def _on_click(self, e):
        self.move(self.label, 1, 1)

    def _on_release(self, e):
        self.move(self.label, -1, -1)
        if self.command:
            self.command()


class StatusCard(tk.Frame):
    """상태 표시 카드"""
    def __init__(self, parent, title, value, icon="ℹ️", color=COLORS["success"]):
        super().__init__(parent, bg=COLORS["surface"], padx=15, pady=15)
        self.title_lbl = tk.Label(self, text=title, bg=COLORS["surface"], fg=COLORS["sub_text"], font=("맑은 고딕", 9))
        self.title_lbl.pack(anchor="w")
        
        self.value_lbl = tk.Label(self, text=f"{icon} {value}", bg=COLORS["surface"], fg=color, font=("맑은 고딕", 11, "bold"))
        self.value_lbl.pack(anchor="w", pady=(5, 0))

    def update_status(self, text, color=None):
        self.value_lbl.config(text=text)
        if color:
            self.value_lbl.config(fg=color)


# ═══════════════════════════════════════════════════════════════════════════════
# 메인 윈도우
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk, start_minimized: bool = False):
        self.root = root
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        self.hosts_mgr = HostsManager(self.logger)
        self.layout_hider = AdLayoutHider(self.logger)
        self.tray_manager = None
        self._is_quitting = False
        
        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._start_services()
        
        # 시작 시 최소화 처리
        if start_minimized or self.settings.start_minimized:
            self.root.after(100, self.hide_to_tray)
    
    def _setup_window(self):
        self.root.title(APP_NAME)
        self.root.geometry("500x650")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)
        
        # 창 닫기 이벤트 오버라이드
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 관리자 권한 체크
        if not SystemManager.is_admin():
            if messagebox.askyesno("권한 필요", "광고 차단을 위해 관리자 권한이 필요합니다.\n재실행 하시겠습니까?"):
                SystemManager.run_as_admin()
            else:
                self.logger.warning("관리자 권한 없이 실행됨 - 기능 제한")

    def _setup_tray(self):
        """트레이 아이콘 설정"""
        if TRAY_AVAILABLE:
            self.tray_manager = TrayManager(self)
            self.tray_manager.setup()
            self.tray_manager.start()
        
    def _setup_ui(self):
        # 1. 헤더 영역 (노란색 배경)
        header = tk.Frame(self.root, bg=COLORS["primary"], height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text="🛡️", bg=COLORS["primary"], font=("Segoe UI Emoji", 24)).pack(side="left", padx=(20, 10))
        
        title_frame = tk.Frame(header, bg=COLORS["primary"])
        title_frame.pack(side="left", fill="y", pady=15)
        
        tk.Label(title_frame, text=APP_NAME, bg=COLORS["primary"], fg="#3A1D1D", 
                 font=("맑은 고딕", 14, "bold")).pack(anchor="w")
        tk.Label(title_frame, text=f"v{VERSION} | System Protected", bg=COLORS["primary"], fg="#554400",
                 font=("맑은 고딕", 9)).pack(anchor="w")

        # 2. 메인 컨텐츠
        content = tk.Frame(self.root, bg=COLORS["bg"], padx=20, pady=20)
        content.pack(fill="both", expand=True)

        # 상태 대시보드
        dashboard = tk.Frame(content, bg=COLORS["bg"])
        dashboard.pack(fill="x", pady=(0, 20))
        
        self.card_protect = StatusCard(dashboard, "보호 상태", "확인 중...", "🛡️")
        self.card_protect.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.card_process = StatusCard(dashboard, "카카오톡", "감지 안됨", "💬", COLORS["sub_text"])
        self.card_process.pack(side="left", fill="x", expand=True)

        # 메인 액션 버튼 (스마트 원클릭)
        action_frame = tk.Frame(content, bg=COLORS["bg"])
        action_frame.pack(fill="x", pady=10)
        
        self.btn_optimize = ModernButton(action_frame, "✨ 스마트 최적화", self._smart_optimize, width=460, height=50)
        self.btn_optimize.pack()
        
        # 세부 컨트롤
        controls = tk.LabelFrame(content, text="세부 설정", bg=COLORS["bg"], fg=COLORS["sub_text"], font=("맑은 고딕", 9), padx=15, pady=15)
        controls.pack(fill="x", pady=20)
        
        # 스위치 옵션들
        self.var_autostart = tk.BooleanVar(value=StartupManager.is_startup_enabled())
        self.var_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.var_start_hidden = tk.BooleanVar(value=self.settings.start_minimized)
        self.var_mon = tk.BooleanVar(value=self.settings.realtime_protection)
        self.var_hide = tk.BooleanVar(value=self.settings.hide_layout)
        
        cb_style = {"bg": COLORS["bg"], "activebackground": COLORS["bg"], "font": ("맑은 고딕", 9)}
        
        tk.Checkbutton(controls, text="Windows 시작 시 자동 실행", variable=self.var_autostart, command=self._toggle_autostart, **cb_style).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="닫을 때 트레이로 최소화", variable=self.var_tray, command=self._save_settings, **cb_style).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="시작 시 트레이로 바로 최소화", variable=self.var_start_hidden, command=self._save_settings, **cb_style).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="실시간 프로세스 모니터링", variable=self.var_mon, command=self._save_settings, **cb_style).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="광고 레이아웃(빈 공간) 자동 제거", variable=self.var_hide, command=self._toggle_layout_hider, **cb_style).pack(anchor="w", pady=2)

        # 트레이 안내 메시지
        if TRAY_AVAILABLE:
            tray_info = tk.Label(content, text="💡 트레이 아이콘을 더블클릭하면 창이 다시 열립니다.", 
                                bg=COLORS["bg"], fg=COLORS["sub_text"], font=("맑은 고딕", 8))
            tray_info.pack(pady=(0, 10))
        else:
            tray_warning = tk.Label(content, text="⚠️ pystray/Pillow가 설치되지 않아 트레이 기능 비활성화", 
                                   bg=COLORS["bg"], fg=COLORS["warning"], font=("맑은 고딕", 8))
            tray_warning.pack(pady=(0, 10))

        # 하단 버튼 그룹
        bottom_frame = tk.Frame(content, bg=COLORS["bg"])
        bottom_frame.pack(fill="x", side="bottom")

        ModernButton(bottom_frame, "📂 로그 보기", self._open_logs, width=100, height=35, bg_color="#E0E0E0", hover_color="#D5D5D5").pack(side="left")
        ModernButton(bottom_frame, "🔄 DNS 초기화", self._flush_dns_manual, width=100, height=35, bg_color="#E0E0E0", hover_color="#D5D5D5").pack(side="right")
        ModernButton(bottom_frame, "📝 도메인 관리", self._manage_domains, width=100, height=35, bg_color="#E0E0E0", hover_color="#D5D5D5").pack(side="right", padx=10)

    def _start_services(self):
        if self.settings.hide_layout:
            self.layout_hider.start()
            
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        while True:
            try:
                ratio = self.hosts_mgr.get_status(DEFAULT_AD_DOMAINS)
                if ratio >= 1.0:
                    self.card_protect.update_status("🛡️ 안전함 (100%)", COLORS["success"])
                elif ratio > 0:
                    self.card_protect.update_status(f"⚠️ 부분 차단 ({ratio*100:.0f}%)", COLORS["warning"])
                else:
                    self.card_protect.update_status("❌ 위험 (차단 안됨)", COLORS["error"])

                is_running = SystemManager.is_process_running("KakaoTalk")
                if is_running:
                    self.card_process.update_status("💬 실행 중", COLORS["success"])
                else:
                    self.card_process.update_status("💬 종료됨", COLORS["sub_text"])
            except Exception:
                pass

            time.sleep(2)

    def _on_close(self):
        """창 닫기 버튼 처리"""
        if self.settings.minimize_to_tray and TRAY_AVAILABLE:
            self.hide_to_tray()
        else:
            self.quit_app()
    
    def hide_to_tray(self):
        """창을 트레이로 숨김"""
        self.root.withdraw()
        self.logger.info("트레이로 최소화됨")
    
    def show_window(self):
        """창 표시"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def quit_app(self):
        """프로그램 완전 종료"""
        if self._is_quitting:
            return
        self._is_quitting = True
        
        self.layout_hider.stop()
        if self.tray_manager:
            self.tray_manager.stop()
        
        self.root.quit()
        self.root.destroy()

    def _smart_optimize(self):
        """원클릭 최적화 로직"""
        if not SystemManager.is_admin():
            messagebox.showwarning("권한 필요", "이 기능을 사용하려면 관리자 권한이 필요합니다.")
            return

        domains = []
        if os.path.exists(DOMAINS_FILE):
            with open(DOMAINS_FILE, 'r', encoding='utf-8') as f:
                domains = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        if not domains:
            domains = DEFAULT_AD_DOMAINS

        success = self.hosts_mgr.block(domains)
        SystemManager.flush_dns()
        restarted = SystemManager.restart_process("kakaotalk.exe")
        
        msg = []
        msg.append("✅ 광고 도메인 차단 완료" if success else "❌ 차단 실패")
        msg.append("✅ DNS 캐시 초기화 완료")
        msg.append("✅ 카카오톡 재시작 완료" if restarted else "⚠️ 카카오톡을 찾지 못하거나 재시작 실패")
        
        messagebox.showinfo("스마트 최적화 결과", "\n".join(msg))

    def _flush_dns_manual(self):
        if SystemManager.flush_dns():
            messagebox.showinfo("성공", "DNS 캐시를 초기화했습니다.")
    
    def _manage_domains(self):
        if os.path.exists(DOMAINS_FILE):
            os.startfile(DOMAINS_FILE)
        else:
            messagebox.showinfo("안내", "도메인 파일이 없습니다.")

    def _open_logs(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)

    def _save_settings(self):
        self.settings.minimize_to_tray = self.var_tray.get()
        self.settings.start_minimized = self.var_start_hidden.get()
        self.settings.realtime_protection = self.var_mon.get()
        self.settings.hide_layout = self.var_hide.get()
        self.settings.save()
    
    def _toggle_autostart(self):
        """시작프로그램 등록 토글"""
        enabled = self.var_autostart.get()
        success = StartupManager.set_startup_enabled(enabled)
        if not success:
            self.var_autostart.set(not enabled)
            messagebox.showerror("오류", "시작프로그램 등록/해제에 실패했습니다.")
        else:
            self.settings.auto_start = enabled
            self.settings.save()
            if enabled:
                self.logger.info("시작프로그램 등록 완료")
            else:
                self.logger.info("시작프로그램 해제 완료")

    def _toggle_layout_hider(self):
        self._save_settings()
        if self.settings.hide_layout:
            self.layout_hider.start()
        else:
            self.layout_hider.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 엔트리 포인트
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    # 고해상도 지원 (DPI)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    
    # 명령행 인자 확인
    start_minimized = "--minimized" in sys.argv
    
    # 도메인 파일 체크
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(DEFAULT_AD_DOMAINS))

    root = tk.Tk()
    app = MainWindow(root, start_minimized=start_minimized)
    root.mainloop()

if __name__ == "__main__":
    main()
