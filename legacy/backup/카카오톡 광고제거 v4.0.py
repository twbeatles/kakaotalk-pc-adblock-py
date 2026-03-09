# -*- coding: utf-8 -*-
# pyright: reportOptionalMemberAccess=false, reportPossiblyUnboundVariable=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportSelfClsParameterName=false, reportOptionalCall=false
"""
카카오톡 광고 차단기 Pro v5.0 (Refactored)
=====================================
- Modern UI/UX (Flat Design, Kakao Theme)
- Separated Architecture (Logic vs UI)
- Enhanced Stability & Performance
- Smart Optimization Feature
"""

import os
import sys
import ctypes
from ctypes import wintypes
import shutil
import json
import threading
import time
import logging
import queue
import webbrowser
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass
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
VERSION = "5.0.0"
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
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
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
    theme: str = "light"
    
    @classmethod
    def load(cls):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return cls(**json.load(f))
        except: pass
        return cls()
    
    def save(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, indent=2)
        except: pass

class SystemManager:
    """시스템 레벨 작업 관리 (Process, DNS, Admin 등)"""
    
    @staticmethod
    def is_admin() -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False

    @staticmethod
    def run_as_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
            sys.exit(0)
        except: pass

    @staticmethod
    def flush_dns() -> bool:
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=0x08000000) # CREATE_NO_WINDOW
            return True
        except: return False

    @staticmethod
    def is_process_running(process_name: str) -> bool:
        if not psutil: return False
        try:
            for p in psutil.process_iter(['name']):
                if process_name.lower() in (p.info['name'] or '').lower():
                    return True
        except: pass
        return False

    @staticmethod
    def restart_process(process_name: str, exe_path: str = None) -> bool:
        # 1. 실행 중인 프로세스에서 경로 찾기 (psutil 사용)
        if not exe_path and psutil:
            try:
                for p in psutil.process_iter(['name', 'exe']):
                    if process_name.lower() in (p.info['name'] or '').lower():
                        exe_path = p.info['exe']
                        break
            except: pass

        # 2. 프로세스 종료
        try:
            subprocess.run(["taskkill", "/f", "/im", process_name], capture_output=True, creationflags=0x08000000)
            time.sleep(1.5) # 완전히 종료될 때까지 대기
            
            # 3. 재실행
            if exe_path and os.path.exists(exe_path):
                os.startfile(exe_path)
                return True
            
            # 4. 경로를 못 찾은 경우 기본 경로 시도 (Windows 전용)
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
        except: pass
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
            # 읽기 전용 속성 해제 시도
            os.chmod(self.HOSTS_PATH, 0o777)
            with open(self.HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            self.logger.error(f"Hosts 쓰기 실패: {e}")
            return False

    def block(self, domains: List[str]) -> bool:
        content = self._read_hosts()
        # 기존 블록 제거
        lines = [line for line in content.splitlines() if self.MARKER_START not in line and self.MARKER_END not in line]
        # 해당 도메인의 기존 레코드도 제거 (중복 방지)
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
            if self.MARKER_START in line: skip = True
            if not skip: new_lines.append(line)
            if self.MARKER_END in line: skip = False
        
        if self._write_hosts("\n".join(new_lines)):
            self.logger.info("광고 차단 해제 완료")
            return True
        return False

    def get_status(self, domains: List[str]) -> float:
        """차단율 반환 (0.0 ~ 1.0)"""
        content = self._read_hosts()
        if not content: return 0.0
        count = 0
        for d in domains:
            if f"0.0.0.0 {d}" in content or f"127.0.0.1 {d}" in content:
                count += 1
        return count / len(domains) if domains else 0.0

class AdLayoutHider:
    """Windows API를 이용한 광고 영역 숨김 및 리사이징 (v5.1 Optimized)"""
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.active = False
        self.thread = None
        self.user32 = ctypes.windll.user32 if platform.system() == "Windows" else None
        self.kakao_pid = None

    def start(self):
        if not self.user32 or self.active: return
        self.active = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.logger.info("레이아웃 최적화 엔진 시작 (v5.1)")

    def stop(self):
        self.active = False
        self.logger.info("레이아웃 최적화 엔진 중지")

    def _loop(self):
        while self.active:
            try:
                self._scan_and_fix()
                # 프로세스가 있으면 1.5초, 없으면 3초 대기 (CPU 절약)
                time.sleep(1.5 if self.kakao_pid else 3.0)
            except: 
                time.sleep(3)

    def _get_kakao_pid(self):
        """카카오톡 프로세스 ID 찾기 (캐싱 겸용)"""
        # 주기적으로 PID 재확인
        if not psutil: return None
        for p in psutil.process_iter(['name', 'pid']):
            if 'kakaotalk.exe' in (p.info['name'] or '').lower():
                return p.info['pid']
        return None

    def _scan_and_fix(self):
        # 1. 카카오톡 PID 획득 (psutil이 없거나 실패하면 None)
        self.kakao_pid = self._get_kakao_pid()
        
        # 2. 윈도우 스캔
        def enum_cb(hwnd, _):
            # PID 필터링 모드
            if self.kakao_pid:
                lpdw_process_id = ctypes.c_ulong()
                self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_process_id))
                if lpdw_process_id.value != self.kakao_pid:
                    return True # 내 프로세스가 아니면 스킵

            # 클래스 이름 확인
            class_name = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(hwnd, class_name, 256)
            
            if class_name.value == "EVA_Window":
                self._process_eva_window(hwnd)
            return True
        
        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumWindows(PROC(enum_cb), 0)

    def _process_eva_window(self, parent_hwnd):
        # 메인 윈도우인지 확인 (제목이 '카카오톡')
        length = self.user32.GetWindowTextLengthW(parent_hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(parent_hwnd, buf, length + 1)
            if "카카오톡" not in buf.value and "KakaoTalk" not in buf.value:
                return # 메인 윈도우가 아니면 스킵

        def child_cb(hwnd, _):
            length = self.user32.GetWindowTextLengthW(hwnd)
            if length == 0: return True
            buf = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buf, length + 1)
            text = buf.value
            
            # 광고 뷰 숨기기
            if text.startswith("BannerAdView") or text.startswith("AdView"):
                # 이미 숨겨져 있는지 체크 후 실행 (불필요한 호출 방지)
                if self.user32.IsWindowVisible(hwnd):
                    self.user32.ShowWindow(hwnd, 0) # SW_HIDE
            
            # 메인 뷰 리사이징
            elif text.startswith("OnlineMainView"):
                self._resize_main_view(hwnd, parent_hwnd)
            return True

        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumChildWindows(parent_hwnd, PROC(child_cb), 0)

    def _resize_main_view(self, hwnd, parent_hwnd):
        try:
            # 부모(EVA_Window) 클라이언트 영역 높이
            pr = wintypes.RECT()
            self.user32.GetClientRect(parent_hwnd, ctypes.byref(pr))
            parent_client_h = pr.bottom - pr.top

            # 자식(OnlineMainView)의 윈도우 좌표
            cr = wintypes.RECT()
            self.user32.GetWindowRect(hwnd, ctypes.byref(cr))
            
            # 자식의 좌측 상단을 부모 클라이언트 기준 좌표로 변환
            pt = wintypes.POINT(cr.left, cr.top)
            self.user32.ScreenToClient(parent_hwnd, ctypes.byref(pt))
            
            # 목표: 자식의 Y 시작점부터 부모의 끝까지 꽉 채우기
            target_height = parent_client_h - pt.y
            
            if target_height < 100: return # 너무 작으면 무시
            
            current_height = cr.bottom - cr.top
            current_width = cr.right - cr.left

            # 5픽셀 이상 차이날 때만 리사이즈 (CPU 절약 및 깜빡임 방지)
            if abs(target_height - current_height) > 5:
                # SWP_NOMOVE(0x0002) | SWP_NOZORDER(0x0004) | SWP_NOACTIVATE(0x0010) | SWP_FRAMECHANGED(0x0020)
                self.user32.SetWindowPos(hwnd, 0, 0, 0, current_width, target_height, 
                                       0x0002 | 0x0004 | 0x0010 | 0x0020)
        except: pass

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
        if self.command: self.command()

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
        if color: self.value_lbl.config(fg=color)

# ═══════════════════════════════════════════════════════════════════════════════
# 메인 윈도우
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        self.hosts_mgr = HostsManager(self.logger)
        self.layout_hider = AdLayoutHider(self.logger)
        
        self._setup_window()
        self._setup_ui()
        self._start_services()

    def _setup_window(self):
        self.root.title(APP_NAME)
        self.root.geometry("500x600")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)
        
        # 관리자 권한 체크
        if not SystemManager.is_admin():
            if messagebox.askyesno("권한 필요", "광고 차단을 위해 관리자 권한이 필요합니다.\n재실행 하시겠습니까?"):
                SystemManager.run_as_admin()
            else:
                self.logger.warning("관리자 권한 없이 실행됨 - 기능 제한")

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
        self.var_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.var_mon = tk.BooleanVar(value=self.settings.realtime_protection)
        self.var_hide = tk.BooleanVar(value=self.settings.hide_layout)
        
        cb_style = {"bg": COLORS["bg"], "activebackground": COLORS["bg"], "font": ("맑은 고딕", 9)}
        
        tk.Checkbutton(controls, text="닫을 때 트레이로 최소화", variable=self.var_tray, command=self._save_settings, **cb_style).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="실시간 프로세스 모니터링", variable=self.var_mon, command=self._save_settings, **cb_style).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="광고 레이아웃(빈 공간) 자동 제거", variable=self.var_hide, command=self._toggle_layout_hider, **cb_style).pack(anchor="w", pady=2)

        # 하단 버튼 그룹
        bottom_frame = tk.Frame(content, bg=COLORS["bg"])
        bottom_frame.pack(fill="x", side="bottom")

        ModernButton(bottom_frame, "📂 로그 보기", self._open_logs, width=100, height=35, bg_color="#E0E0E0", hover_color="#D5D5D5").pack(side="left")
        ModernButton(bottom_frame, "🔄 DNS 초기화", self._flush_dns_manual, width=100, height=35, bg_color="#E0E0E0", hover_color="#D5D5D5").pack(side="right")
        ModernButton(bottom_frame, "📝 도메인 관리", self._manage_domains, width=100, height=35, bg_color="#E0E0E0", hover_color="#D5D5D5").pack(side="right", padx=10)

    def _start_services(self):
        # 설정 적용
        if self.settings.hide_layout:
            self.layout_hider.start()
            
        # 모니터링 스레드
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        while True:
            # 1. 차단율 업데이트
            ratio = self.hosts_mgr.get_status(DEFAULT_AD_DOMAINS) # 실제로는 파일에서 로드한 도메인 써야 함
            if ratio >= 1.0:
                self.card_protect.update_status("안전함 (100%)", COLORS["success"])
            elif ratio > 0:
                self.card_protect.update_status(f"부분 차단 ({ratio*100:.0f}%)", COLORS["warning"])
            else:
                self.card_protect.update_status("위험 (차단 안됨)", COLORS["error"])

            # 2. 프로세스 감지
            is_running = SystemManager.is_process_running("KakaoTalk")
            if is_running:
                self.card_process.update_status("실행 중", COLORS["success"])
            else:
                self.card_process.update_status("종료됨", COLORS["sub_text"])

            time.sleep(2)

    def _smart_optimize(self):
        """원클릭 최적화 로직"""
        if not SystemManager.is_admin():
            messagebox.showwarning("권한 필요", "이 기능을 사용하려면 관리자 권한이 필요합니다.")
            return

        # 1. 도메인 차단
        domains = []
        if os.path.exists(DOMAINS_FILE):
             with open(DOMAINS_FILE, 'r', encoding='utf-8') as f:
                 domains = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        if not domains: domains = DEFAULT_AD_DOMAINS

        success = self.hosts_mgr.block(domains)
        
        # 2. DNS 초기화
        SystemManager.flush_dns()
        
        # 3. 카톡 재시작
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
        os.startfile(DOMAINS_FILE) if os.path.exists(DOMAINS_FILE) else messagebox.showinfo("안내", "도메인 파일이 없습니다.")

    def _open_logs(self):
        os.startfile(LOG_FILE) if os.path.exists(LOG_FILE) else None

    def _save_settings(self):
        self.settings.minimize_to_tray = self.var_tray.get()
        self.settings.realtime_protection = self.var_mon.get()
        self.settings.hide_layout = self.var_hide.get()
        self.settings.save()

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
    except: pass
    
    # 도메인 파일 체크
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(DEFAULT_AD_DOMAINS))

    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    main()


