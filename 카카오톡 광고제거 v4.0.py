# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v4.0
===========================
주요 개선사항:
- 모던 UI/UX (ttk 테마, 애니메이션, 다크/라이트 모드)
- 광고 레이아웃 숨기기 (Windows API)
- Toast 알림 시스템
- 키보드 단축키
- 최신 카카오톡 광고 도메인 목록 (2024-2025)
- 강화된 로깅 시스템
- 실시간 상태 업데이트
- 자동 백업/복원 시스템
"""

import os
import sys
import platform
import ctypes
import shutil
import json
import threading
import time
import logging
import queue
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from contextlib import contextmanager
import subprocess

# 서드파티 라이브러리
try:
    import psutil
except ImportError:
    psutil = None

try:
    import requests
except ImportError:
    requests = None

# GUI 관련
import tkinter as tk
from tkinter import ttk, messagebox, font, filedialog
from tkinter.scrolledtext import ScrolledText

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# 상수 및 설정
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "4.0.0"
APP_NAME = "카카오톡 광고 차단기 Pro"
GITHUB_REPO = "blurfx/KakaoTalkAdBlock"  # 참고용 레포지토리
SETTINGS_FILE = "adblock_settings.json"
DOMAINS_FILE = "blocked_domains.txt"
LOG_FILE = "adblock.log"

# 최신 광고 도메인 목록 (2024-2025 업데이트)
DEFAULT_AD_DOMAINS = [
    # Daum/Kakao 광고 서버 (핵심)
    "display.ad.daum.net",
    "analytics.ad.daum.net",
    "ad.daum.net",
    "alea.adam.ad.daum.net",
    "adam.ad.daum.net",
    "wat.ad.daum.net",
    "biz.ad.daum.net",
    "cs.ad.daum.net",
    "ad.mad.daum.net",
    "ams.ad.daum.net",
    "amsv2.daum.net",
    
    # Kakao 광고 서버
    "ad.smart.kakao.com",
    "ad.kakao.com",
    "display.ad.kakao.com",
    "business.kakao.com",
    
    # Kakao CDN 광고
    "ad.kakaocdn.net",
    "ad.kakaocdn.com",
    "t1.kakaocdn.net",
    "st.kakaocdn.net",
    "adimg.imkakao.com",
    "adimg.daumcdn.net",
    
    # adimg 시리즈 (1~10)
    "adimg1.kakaocdn.net",
    "adimg2.kakaocdn.net",
    "adimg3.kakaocdn.net",
    "adimg4.kakaocdn.net",
    "adimg5.kakaocdn.net",
    "adimg6.kakaocdn.net",
    "adimg7.kakaocdn.net",
    "adimg8.kakaocdn.net",
    "adimg9.kakaocdn.net",
    "adimg10.kakaocdn.net",
    
    # 트래킹/분석
    "track.tiara.kakao.com",
    "stat.tiara.kakao.com",
    
    # Criteo 연동 광고
    "kakaoad.criteo.com",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Toast 알림 시스템
# ═══════════════════════════════════════════════════════════════════════════════
class ToastWidget(tk.Toplevel):
    """비침투적 토스트 알림 위젯"""
    
    TOAST_COLORS = {
        "success": {"bg": "#28A745", "fg": "#FFFFFF"},
        "error": {"bg": "#DC3545", "fg": "#FFFFFF"},
        "warning": {"bg": "#FFC107", "fg": "#1A1A1A"},
        "info": {"bg": "#17A2B8", "fg": "#FFFFFF"},
    }
    
    _active_toasts: List['ToastWidget'] = []
    
    def __init__(self, parent: tk.Tk, message: str, toast_type: str = "info", duration: int = 3000):
        super().__init__(parent)
        
        self.parent = parent
        self.duration = duration
        
        # 윈도우 설정
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        
        # 색상 설정
        colors = self.TOAST_COLORS.get(toast_type, self.TOAST_COLORS["info"])
        
        # 프레임 및 라벨
        frame = tk.Frame(self, bg=colors["bg"], padx=15, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 아이콘
        icons = {"success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️"}
        icon = icons.get(toast_type, "ℹ️")
        
        label = tk.Label(
            frame,
            text=f"{icon} {message}",
            bg=colors["bg"],
            fg=colors["fg"],
            font=("맑은 고딕", 10, "bold"),
            wraplength=300
        )
        label.pack()
        
        # 위치 계산 및 표시
        self._position_toast()
        ToastWidget._active_toasts.append(self)
        self._fade_in()
    
    def _position_toast(self):
        """토스트 위치 설정 (우측 하단)"""
        self.update_idletasks()
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        toast_width = self.winfo_width()
        toast_height = self.winfo_height()
        
        # 기존 토스트들 위에 쌓기
        offset = len(ToastWidget._active_toasts) * (toast_height + 10)
        
        x = screen_width - toast_width - 20
        y = screen_height - toast_height - 60 - offset
        
        self.geometry(f"+{x}+{y}")
    
    def _fade_in(self, alpha: float = 0.0):
        """페이드 인 애니메이션"""
        if alpha < 0.95:
            try:
                self.attributes("-alpha", alpha)
            except tk.TclError:
                pass
            self.after(20, lambda: self._fade_in(alpha + 0.1))
        else:
            try:
                self.attributes("-alpha", 0.95)
            except tk.TclError:
                pass
            self.after(self.duration, self._fade_out)
    
    def _fade_out(self, alpha: float = 0.95):
        """페이드 아웃 애니메이션"""
        if alpha > 0.05:
            try:
                self.attributes("-alpha", alpha)
            except tk.TclError:
                pass
            self.after(20, lambda: self._fade_out(alpha - 0.1))
        else:
            self._close()
    
    def _close(self):
        """토스트 닫기"""
        try:
            if self in ToastWidget._active_toasts:
                ToastWidget._active_toasts.remove(self)
            self.destroy()
        except tk.TclError:
            pass  # 이미 파괴된 위젯


# ═══════════════════════════════════════════════════════════════════════════════
# 열거형 및 데이터 클래스
# ═══════════════════════════════════════════════════════════════════════════════
class BlockStatus(Enum):
    """차단 상태"""
    NOT_BLOCKED = auto()
    PARTIALLY_BLOCKED = auto()
    FULLY_BLOCKED = auto()
    ERROR = auto()


class Theme(Enum):
    """테마"""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass
class AppSettings:
    """애플리케이션 설정"""
    auto_start: bool = False
    minimize_to_tray: bool = True
    check_updates: bool = True
    monitoring_enabled: bool = True
    monitoring_interval: int = 3  # 초
    theme: str = Theme.LIGHT.value
    first_run: bool = True
    backup_on_modify: bool = True
    log_level: str = "INFO"
    hide_ad_layout: bool = True  # 광고 레이아웃 숨기기
    
    @classmethod
    def load(cls, filepath: str) -> 'AppSettings':
        """설정 파일에서 로드"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception as e:
            logging.warning(f"설정 로드 실패: {e}")
        return cls()
    
    def save(self, filepath: str) -> bool:
        """설정 파일에 저장"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logging.error(f"설정 저장 실패: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# 로깅 설정
# ═══════════════════════════════════════════════════════════════════════════════
class QueueHandler(logging.Handler):
    """GUI로 로그를 전달하기 위한 큐 핸들러"""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        self.log_queue.put(self.format(record))


def setup_logging(log_file: str, log_queue: Optional[queue.Queue] = None) -> logging.Logger:
    """로깅 설정"""
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.DEBUG)
    
    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # GUI 큐 핸들러
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setLevel(logging.INFO)
        queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(queue_handler)
    
    return logger


# ═══════════════════════════════════════════════════════════════════════════════
# 시스템 유틸리티
# ═══════════════════════════════════════════════════════════════════════════════
class SystemUtils:
    """시스템 관련 유틸리티 함수들"""
    
    @staticmethod
    def get_hosts_path() -> str:
        """hosts 파일 경로 반환"""
        if platform.system() == "Windows":
            return os.path.join(
                os.environ.get("SystemRoot", "C:\\Windows"),
                "System32", "drivers", "etc", "hosts"
            )
        return "/etc/hosts"
    
    @staticmethod
    def is_admin() -> bool:
        """관리자 권한 확인"""
        try:
            if platform.system() == "Windows":
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            return os.geteuid() == 0
        except Exception:
            return False
    
    @staticmethod
    def run_as_admin():
        """관리자 권한으로 재실행"""
        if platform.system() == "Windows":
            try:
                # 공백이 포함된 경로를 위해 따옴표 처리
                args = " ".join(f'"{arg}"' for arg in sys.argv)
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, args, None, 1
                )
                sys.exit(0)
            except Exception:
                pass
    
    @staticmethod
    def flush_dns() -> bool:
        """DNS 캐시 초기화"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["ipconfig", "/flushdns"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return result.returncode == 0
            elif platform.system() == "Linux":
                subprocess.run(["systemd-resolve", "--flush-caches"], capture_output=True)
                return True
            elif platform.system() == "Darwin":
                subprocess.run(["dscacheutil", "-flushcache"], capture_output=True)
                return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def is_kakaotalk_running() -> bool:
        """카카오톡 프로세스 실행 여부 확인"""
        if psutil is None:
            return False
        try:
            for proc in psutil.process_iter(['name']):
                name = proc.info.get('name', '')
                if name and 'kakaotalk' in name.lower():
                    return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def get_kakaotalk_path() -> Optional[str]:
        """카카오톡 설치 경로 찾기"""
        if platform.system() != "Windows":
            return None
            
        search_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'Kakao', 'KakaoTalk'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'Kakao', 'KakaoTalk'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Kakao', 'KakaoTalk'),
            os.path.join(os.environ.get('APPDATA', ''), 'Kakao', 'KakaoTalk'),
        ]
        
        for path in search_paths:
            if path and os.path.exists(path):
                return path
        return None
    
    @staticmethod
    def restart_kakaotalk() -> bool:
        """카카오톡 재시작"""
        if platform.system() != "Windows":
            return False
            
        try:
            # 종료
            subprocess.run(
                ["taskkill", "/f", "/im", "kakaotalk.exe"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            time.sleep(1.5)
            
            # 실행
            kakao_path = SystemUtils.get_kakaotalk_path()
            if kakao_path:
                exe_path = os.path.join(kakao_path, "KakaoTalk.exe")
                if os.path.exists(exe_path):
                    os.startfile(exe_path)
                    return True
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 광고 레이아웃 제거 (Windows API)
# ═══════════════════════════════════════════════════════════════════════════════
class AdLayoutHider:
    """Windows API를 사용하여 카카오톡 광고 레이아웃을 숨깁니다."""
    
    MAIN_VIEW_AD_HEIGHT = 31  # 메인 뷰 하단 광고 영역 높이
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.active = False
        self.thread: Optional[threading.Thread] = None
        self.user32 = None
        if platform.system() == "Windows":
            self.user32 = ctypes.windll.user32
            self.WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    
    def start(self):
        if self.user32 is None:
            return
        self.active = True
        self.thread = threading.Thread(target=self._hide_loop, daemon=True)
        self.thread.start()
        self.logger.info("광고 레이아웃 숨기기 시작됨")
    
    def stop(self):
        self.active = False
        self.logger.info("광고 레이아웃 숨기기 중지됨")
    
    def _hide_loop(self):
        while self.active:
            try:
                self._hide_ad_windows()
                time.sleep(0.5)
            except Exception:
                time.sleep(1)
    
    def _hide_ad_windows(self):
        def enum_callback(hwnd, lParam):
            try:
                class_name = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(hwnd, class_name, 256)
                if class_name.value == "EVA_Window":
                    self._process_window(hwnd)
            except Exception:
                pass
            return True
        callback = self.WNDENUMPROC(enum_callback)
        self.user32.EnumWindows(callback, 0)
    
    def _process_window(self, parent):
        def child_callback(hwnd, lParam):
            try:
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, buf, length + 1)
                    text = buf.value
                    if text.startswith("OnlineMainView"):
                        self._resize_main_view(hwnd)
                    elif text.startswith("BannerAdView") or text.startswith("AdView"):
                        self.user32.ShowWindow(hwnd, 0)
            except Exception:
                pass
            return True
        callback = self.WNDENUMPROC(child_callback)
        self.user32.EnumChildWindows(parent, callback, 0)
    
    def _resize_main_view(self, hwnd):
        try:
            rect = ctypes.wintypes.RECT()
            self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left - 2
            height = rect.bottom - rect.top - self.MAIN_VIEW_AD_HEIGHT
            if height > 1:
                self.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, self.SWP_NOMOVE | self.SWP_NOZORDER)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Hosts 파일 매니저
# ═══════════════════════════════════════════════════════════════════════════════
class HostsManager:
    """Hosts 파일 관리 클래스"""
    
    BLOCK_MARKER_START = "# === KakaoTalk AdBlock START ==="
    BLOCK_MARKER_END = "# === KakaoTalk AdBlock END ==="
    
    def __init__(self, hosts_path: str, logger: logging.Logger):
        self.hosts_path = hosts_path
        self.logger = logger
    
    @contextmanager
    def _safe_file_operation(self, mode: str = 'r'):
        """안전한 파일 작업을 위한 컨텍스트 매니저"""
        try:
            with open(self.hosts_path, mode, encoding='utf-8', errors='ignore') as f:
                yield f
        except PermissionError:
            self.logger.error("hosts 파일 접근 권한이 없습니다. 관리자 권한으로 실행하세요.")
            raise
        except Exception as e:
            self.logger.error(f"hosts 파일 작업 중 오류: {e}")
            raise
    
    def read_content(self) -> str:
        """hosts 파일 내용 읽기"""
        with self._safe_file_operation('r') as f:
            return f.read()
    
    def write_content(self, content: str):
        """hosts 파일 내용 쓰기"""
        with self._safe_file_operation('w') as f:
            f.write(content)
    
    def create_backup(self) -> Optional[str]:
        """백업 파일 생성"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.hosts_path}.backup_{timestamp}"
            shutil.copy2(self.hosts_path, backup_path)
            self.logger.info(f"백업 생성: {backup_path}")
            return backup_path
        except Exception as e:
            self.logger.error(f"백업 생성 실패: {e}")
            return None
    
    def restore_backup(self, backup_path: str) -> bool:
        """백업에서 복원"""
        try:
            shutil.copy2(backup_path, self.hosts_path)
            self.logger.info(f"백업 복원 완료: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"백업 복원 실패: {e}")
            return False
    
    def get_block_status(self, domains: List[str]) -> tuple[BlockStatus, int, int]:
        """차단 상태 확인"""
        try:
            content = self.read_content()
            blocked_count = sum(
                1 for d in domains
                if f"127.0.0.1 {d}" in content or f"0.0.0.0 {d}" in content
            )
            
            total = len(domains)
            if blocked_count == 0:
                return BlockStatus.NOT_BLOCKED, 0, total
            elif blocked_count == total:
                return BlockStatus.FULLY_BLOCKED, blocked_count, total
            else:
                return BlockStatus.PARTIALLY_BLOCKED, blocked_count, total
        except Exception as e:
            self.logger.error(f"상태 확인 실패: {e}")
            return BlockStatus.ERROR, 0, 0
    
    def block_domains(self, domains: List[str], use_marker: bool = True) -> tuple[bool, int]:
        """도메인 차단 추가"""
        try:
            content = self.read_content()
            new_entries = []
            
            for domain in domains:
                if f"127.0.0.1 {domain}" not in content and f"0.0.0.0 {domain}" not in content:
                    new_entries.append(domain)
            
            if not new_entries:
                self.logger.info("이미 모든 도메인이 차단되어 있습니다.")
                return True, 0
            
            # 기존 마커 블록 제거
            content = self._remove_marker_block(content)
            
            # 새 블록 추가
            if not content.endswith('\n'):
                content += '\n'
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if use_marker:
                content += f"\n{self.BLOCK_MARKER_START}\n"
                content += f"# Generated by {APP_NAME} v{VERSION}\n"
                content += f"# Time: {timestamp}\n"
            
            for domain in new_entries:
                content += f"127.0.0.1 {domain}\n"
            
            if use_marker:
                content += f"{self.BLOCK_MARKER_END}\n"
            
            self.write_content(content)
            self.logger.info(f"{len(new_entries)}개 도메인 차단 추가됨")
            return True, len(new_entries)
            
        except Exception as e:
            self.logger.error(f"도메인 차단 실패: {e}")
            return False, 0
    
    def unblock_domains(self, domains: List[str]) -> tuple[bool, int]:
        """도메인 차단 해제"""
        try:
            content = self.read_content()
            lines = content.splitlines(keepends=True)
            new_lines = []
            removed_count = 0
            in_marker_block = False
            
            for line in lines:
                # 마커 블록 처리
                if self.BLOCK_MARKER_START in line:
                    in_marker_block = True
                    continue
                if self.BLOCK_MARKER_END in line:
                    in_marker_block = False
                    continue
                
                # 마커 블록 내부면 스킵
                if in_marker_block:
                    removed_count += 1
                    continue
                
                # 개별 도메인 확인
                is_blocked_domain = False
                for domain in domains:
                    if (f"127.0.0.1 {domain}" in line or 
                        f"0.0.0.0 {domain}" in line):
                        is_blocked_domain = True
                        removed_count += 1
                        break
                
                if not is_blocked_domain:
                    new_lines.append(line)
            
            self.write_content(''.join(new_lines))
            self.logger.info(f"{removed_count}개 항목 차단 해제됨")
            return True, removed_count
            
        except Exception as e:
            self.logger.error(f"차단 해제 실패: {e}")
            return False, 0
    
    def _remove_marker_block(self, content: str) -> str:
        """마커 블록 제거"""
        lines = content.splitlines(keepends=True)
        new_lines = []
        in_marker_block = False
        
        for line in lines:
            if self.BLOCK_MARKER_START in line:
                in_marker_block = True
                continue
            if self.BLOCK_MARKER_END in line:
                in_marker_block = False
                continue
            if not in_marker_block:
                new_lines.append(line)
        
        return ''.join(new_lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 도메인 관리
# ═══════════════════════════════════════════════════════════════════════════════
class DomainManager:
    """광고 도메인 관리 클래스"""
    
    def __init__(self, filepath: str, logger: logging.Logger):
        self.filepath = filepath
        self.logger = logger
        self.domains: List[str] = []
        self.load_or_create()
    
    def load_or_create(self):
        """도메인 파일 로드 또는 생성"""
        try:
            if not os.path.exists(self.filepath):
                self._create_default_file()
            
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.domains = [
                    line.strip() for line in f
                    if line.strip() and not line.strip().startswith('#')
                ]
            self.logger.info(f"{len(self.domains)}개 도메인 로드됨")
        except Exception as e:
            self.logger.error(f"도메인 파일 처리 오류: {e}")
            self.domains = DEFAULT_AD_DOMAINS.copy()
    
    def _create_default_file(self):
        """기본 도메인 파일 생성"""
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write("# 카카오톡 광고 차단 도메인 목록\n")
            f.write(f"# Generated by {APP_NAME} v{VERSION}\n")
            f.write("# 한 줄에 하나의 도메인을 입력하세요.\n")
            f.write("# '#'으로 시작하는 줄은 주석입니다.\n\n")
            f.write('\n'.join(DEFAULT_AD_DOMAINS))
        self.logger.info("기본 도메인 파일 생성됨")
    
    def save(self) -> bool:
        """도메인 목록 저장"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write("# 카카오톡 광고 차단 도메인 목록\n")
                f.write(f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write('\n'.join(self.domains))
            self.logger.info("도메인 목록 저장됨")
            return True
        except Exception as e:
            self.logger.error(f"도메인 저장 실패: {e}")
            return False
    
    def add(self, domain: str) -> bool:
        """도메인 추가"""
        domain = domain.strip().lower()
        if domain and domain not in self.domains:
            self.domains.append(domain)
            return True
        return False
    
    def remove(self, domain: str) -> bool:
        """도메인 제거"""
        domain = domain.strip().lower()
        if domain in self.domains:
            self.domains.remove(domain)
            return True
        return False
    
    def reset_to_default(self):
        """기본값으로 초기화"""
        self.domains = DEFAULT_AD_DOMAINS.copy()
        self.save()


# ═══════════════════════════════════════════════════════════════════════════════
# 시스템 트레이
# ═══════════════════════════════════════════════════════════════════════════════
class TrayIcon:
    """시스템 트레이 아이콘 관리"""
    
    def __init__(self, app: 'AdBlockerApp'):
        self.app = app
        self.icon: Optional[pystray.Icon] = None
    
    def create_icon_image(self, size: int = 64) -> Image.Image:
        """트레이 아이콘 이미지 생성"""
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 배경 (카카오톡 노란색)
        margin = 4
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=8,
            fill='#FEE500'
        )
        
        # 방패 아이콘
        shield_color = '#3A1D1D'
        cx, cy = size // 2, size // 2 + 2
        points = [
            (cx, cy - 18),  # 상단
            (cx + 14, cy - 10),  # 우상단
            (cx + 14, cy + 4),  # 우측
            (cx, cy + 18),  # 하단
            (cx - 14, cy + 4),  # 좌측
            (cx - 14, cy - 10),  # 좌상단
        ]
        draw.polygon(points, fill=shield_color)
        
        # 체크마크
        check_points = [
            (cx - 6, cy),
            (cx - 2, cy + 6),
            (cx + 8, cy - 6)
        ]
        draw.line(check_points, fill='#FEE500', width=3)
        
        return image
    
    def create(self):
        """트레이 아이콘 생성"""
        if not TRAY_AVAILABLE:
            return
        
        try:
            menu = pystray.Menu(
                pystray.MenuItem("열기", self._show_window, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("광고 차단", self._block_ads),
                pystray.MenuItem("차단 해제", self._unblock_ads),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("카카오톡 재시작", self._restart_kakao),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("종료", self._quit_app)
            )
            
            self.icon = pystray.Icon(
                "KakaoAdBlock",
                self.create_icon_image(),
                f"{APP_NAME} v{VERSION}",
                menu
            )
            
            threading.Thread(target=self.icon.run, daemon=True).start()
        except Exception as e:
            logging.error(f"트레이 아이콘 생성 실패: {e}")
    
    def _show_window(self):
        self.app.root.after(0, self.app.show_window)
    
    def _block_ads(self):
        self.app.root.after(0, self.app.block_ads)
    
    def _unblock_ads(self):
        self.app.root.after(0, self.app.unblock_ads)
    
    def _restart_kakao(self):
        self.app.root.after(0, self.app.restart_kakaotalk)
    
    def _quit_app(self):
        self.app.root.after(0, self.app.quit_app)
    
    def stop(self):
        """트레이 아이콘 중지"""
        if self.icon:
            self.icon.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 메인 애플리케이션
# ═══════════════════════════════════════════════════════════════════════════════
class AdBlockerApp:
    """카카오톡 광고 차단기 메인 애플리케이션"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.log_queue = queue.Queue()
        
        # 로거 설정
        self.logger = setup_logging(LOG_FILE, self.log_queue)
        self.logger.info(f"{APP_NAME} v{VERSION} 시작")
        
        # 컴포넌트 초기화
        self.settings = AppSettings.load(SETTINGS_FILE)
        self.hosts_manager = HostsManager(SystemUtils.get_hosts_path(), self.logger)
        self.domain_manager = DomainManager(DOMAINS_FILE, self.logger)
        self.tray_icon: Optional[TrayIcon] = None
        self.ad_layout_hider = AdLayoutHider(self.logger)
        
        # 상태 변수
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        
        # UI 구성
        self._setup_window()
        self._setup_styles()
        self._create_ui()
        
        # 초기화
        self._check_admin()
        self._start_monitoring()
        self._start_layout_hider()
        self._update_ui_periodically()
    
    def _setup_window(self):
        """윈도우 기본 설정"""
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("600x520")
        self.root.minsize(500, 400)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # 키보드 단축키 설정
        self.root.bind("<Control-b>", lambda e: self.block_ads())
        self.root.bind("<Control-B>", lambda e: self.block_ads())
        self.root.bind("<Control-u>", lambda e: self.unblock_ads())
        self.root.bind("<Control-U>", lambda e: self.unblock_ads())
        self.root.bind("<Control-r>", lambda e: self.restart_kakaotalk())
        self.root.bind("<Control-R>", lambda e: self.restart_kakaotalk())
        self.root.bind("<F5>", lambda e: self._update_status())
        
        # 아이콘 설정 (가능한 경우)
        try:
            # 간단한 아이콘 생성
            icon_data = self._create_window_icon()
            self.root.iconphoto(True, icon_data)
        except Exception:
            pass
    
    def _create_window_icon(self) -> tk.PhotoImage:
        """윈도우 아이콘 생성"""
        # 간단한 16x16 아이콘
        icon = tk.PhotoImage(width=32, height=32)
        for x in range(32):
            for y in range(32):
                icon.put("#FEE500", (x, y))
        return icon
    
    def _setup_styles(self):
        """ttk 스타일 설정"""
        self.style = ttk.Style()
        
        # 기본 스타일
        self.style.configure('Title.TLabel', font=('맑은 고딕', 14, 'bold'))
        self.style.configure('Status.TLabel', font=('맑은 고딕', 11))
        self.style.configure('Info.TLabel', font=('맑은 고딕', 9), foreground='gray')
        
        # 버튼 스타일
        self.style.configure('Primary.TButton', font=('맑은 고딕', 10, 'bold'))
        self.style.configure('Secondary.TButton', font=('맑은 고딕', 9))
        
        # 프레임 스타일
        self.style.configure('Card.TFrame', relief='solid', borderwidth=1)
    
    def _create_ui(self):
        """UI 생성"""
        # 메인 컨테이너
        self.main_frame = ttk.Frame(self.root, padding=15)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 헤더
        self._create_header()
        
        # 상태 카드
        self._create_status_card()
        
        # 버튼 영역
        self._create_buttons()
        
        # 옵션 영역
        self._create_options()
        
        # 하단 정보
        self._create_footer()
        
        # 메뉴바
        self._create_menu()
    
    def _create_header(self):
        """헤더 생성"""
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text=f"🛡️ {APP_NAME}",
            style='Title.TLabel'
        ).pack(side=tk.LEFT)
        
        ttk.Label(
            header_frame,
            text=f"v{VERSION}",
            style='Info.TLabel'
        ).pack(side=tk.LEFT, padx=10)
    
    def _create_status_card(self):
        """상태 카드 생성"""
        status_frame = ttk.LabelFrame(self.main_frame, text="상태", padding=15)
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 차단 상태
        self.status_label = ttk.Label(
            status_frame,
            text="상태 확인 중...",
            style='Status.TLabel'
        )
        self.status_label.pack(anchor=tk.W)
        
        # 카카오톡 상태
        self.kakao_status_label = ttk.Label(
            status_frame,
            text="카카오톡: 확인 중...",
            style='Info.TLabel'
        )
        self.kakao_status_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 도메인 수
        self.domain_count_label = ttk.Label(
            status_frame,
            text=f"등록된 차단 도메인: {len(self.domain_manager.domains)}개",
            style='Info.TLabel'
        )
        self.domain_count_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 프로그레스바 (상태 표시용)
        self.progress = ttk.Progressbar(
            status_frame,
            mode='determinate',
            length=200
        )
        self.progress.pack(fill=tk.X, pady=(10, 0))
    
    def _create_buttons(self):
        """버튼 영역 생성"""
        # 메인 버튼
        main_btn_frame = ttk.Frame(self.main_frame)
        main_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.block_btn = ttk.Button(
            main_btn_frame,
            text="🛡️ 광고 차단 시작",
            style='Primary.TButton',
            command=self.block_ads
        )
        self.block_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.unblock_btn = ttk.Button(
            main_btn_frame,
            text="🔓 차단 해제",
            style='Secondary.TButton',
            command=self.unblock_ads
        )
        self.unblock_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # 서브 버튼
        sub_btn_frame = ttk.Frame(self.main_frame)
        sub_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(
            sub_btn_frame,
            text="📝 도메인 편집",
            command=self._open_domain_editor
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        
        ttk.Button(
            sub_btn_frame,
            text="📄 hosts 보기",
            command=self._open_hosts_viewer
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 3))
        
        ttk.Button(
            sub_btn_frame,
            text="🔄 DNS 초기화",
            command=self._flush_dns
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        
        # 추가 버튼
        extra_btn_frame = ttk.Frame(self.main_frame)
        extra_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(
            extra_btn_frame,
            text="🔁 카톡 재시작",
            command=self.restart_kakaotalk
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        
        ttk.Button(
            extra_btn_frame,
            text="📊 통계",
            command=self._show_statistics
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 3))
        
        ttk.Button(
            extra_btn_frame,
            text="📋 로그",
            command=self._open_log_viewer
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
    
    def _create_options(self):
        """옵션 영역 생성"""
        options_frame = ttk.LabelFrame(self.main_frame, text="옵션", padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 트레이 최소화
        self.tray_var = tk.BooleanVar(value=self.settings.minimize_to_tray)
        ttk.Checkbutton(
            options_frame,
            text="창 닫을 때 시스템 트레이로 최소화",
            variable=self.tray_var,
            command=self._toggle_tray_option
        ).pack(anchor=tk.W)
        
        # 모니터링
        self.monitor_var = tk.BooleanVar(value=self.settings.monitoring_enabled)
        ttk.Checkbutton(
            options_frame,
            text="카카오톡 프로세스 모니터링",
            variable=self.monitor_var,
            command=self._toggle_monitoring
        ).pack(anchor=tk.W)
        
        # 광고 레이아웃 숨기기
        self.hide_layout_var = tk.BooleanVar(value=self.settings.hide_ad_layout)
        ttk.Checkbutton(
            options_frame,
            text="광고 레이아웃 숨기기 (빈 공간 제거)",
            variable=self.hide_layout_var,
            command=self._toggle_layout_hider
        ).pack(anchor=tk.W)
    
    def _create_footer(self):
        """하단 정보 생성"""
        footer_frame = ttk.Frame(self.main_frame)
        footer_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(
            footer_frame,
            text="※ 차단 적용 후 카카오톡을 재시작해주세요",
            style='Info.TLabel'
        ).pack()
        
        # GitHub 링크
        link_label = ttk.Label(
            footer_frame,
            text="참고: KakaoTalkAdBlock (GitHub)",
            style='Info.TLabel',
            cursor="hand2"
        )
        link_label.pack(pady=(5, 0))
        link_label.bind("<Button-1>", lambda e: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
    
    def _create_menu(self):
        """메뉴바 생성"""
        menubar = tk.Menu(self.root)
        
        # 파일 메뉴
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="백업 생성", command=self._create_backup)
        file_menu.add_command(label="백업에서 복원...", command=self._restore_backup)
        file_menu.add_separator()
        file_menu.add_command(label="설정 내보내기...", command=self._export_settings)
        file_menu.add_command(label="설정 가져오기...", command=self._import_settings)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.quit_app)
        menubar.add_cascade(label="파일", menu=file_menu)
        
        # 도구 메뉴
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="도메인 목록 초기화", command=self._reset_domains)
        tools_menu.add_command(label="hosts 파일 열기", command=self._open_hosts_in_editor)
        tools_menu.add_separator()
        tools_menu.add_command(label="관리자 권한으로 재실행", command=self._restart_as_admin)
        menubar.add_cascade(label="도구", menu=tools_menu)
        
        # 도움말 메뉴
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="사용 방법", command=self._show_help)
        help_menu.add_command(label="정보", command=self._show_about)
        menubar.add_cascade(label="도움말", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 핵심 기능
    # ═══════════════════════════════════════════════════════════════════════════
    def block_ads(self):
        """광고 차단 시작"""
        if not SystemUtils.is_admin():
            messagebox.showerror("권한 오류", "관리자 권한이 필요합니다.\n\n관리자 권한으로 재실행하세요.")
            return
        
        if not self.domain_manager.domains:
            self._show_toast("차단할 도메인 목록이 비어있습니다.", "warning")
            return
        
        try:
            # 백업 생성
            if self.settings.backup_on_modify:
                self.hosts_manager.create_backup()
            
            # 차단 적용
            success, count = self.hosts_manager.block_domains(self.domain_manager.domains)
            
            if success:
                SystemUtils.flush_dns()
                self._update_status()
                
                if count > 0:
                    self._show_toast(f"{count}개 도메인 차단 완료! 카카오톡을 재시작해주세요.", "success")
                else:
                    self._show_toast("이미 모든 도메인이 차단되어 있습니다.", "info")
            else:
                self._show_toast("차단 적용 중 오류가 발생했습니다.", "error")
                
        except PermissionError:
            messagebox.showerror("권한 오류", "hosts 파일에 접근할 수 없습니다.\n관리자 권한으로 재실행하세요.")
        except Exception as e:
            self.logger.error(f"차단 실패: {e}")
            self._show_toast(f"오류가 발생했습니다: {e}", "error")
    
    def unblock_ads(self):
        """광고 차단 해제"""
        if not SystemUtils.is_admin():
            messagebox.showerror("권한 오류", "관리자 권한이 필요합니다.")
            return
        
        if not messagebox.askyesno("확인", "광고 차단을 해제하시겠습니까?"):
            return
        
        try:
            if self.settings.backup_on_modify:
                self.hosts_manager.create_backup()
            
            success, count = self.hosts_manager.unblock_domains(self.domain_manager.domains)
            
            if success:
                SystemUtils.flush_dns()
                self._update_status()
                
                if count > 0:
                    self._show_toast(f"{count}개 항목의 차단이 해제되었습니다.", "success")
                else:
                    self._show_toast("차단된 항목이 없습니다.", "info")
            else:
                self._show_toast("차단 해제 중 오류가 발생했습니다.", "error")
                
        except Exception as e:
            self.logger.error(f"차단 해제 실패: {e}")
            self._show_toast(f"오류가 발생했습니다: {e}", "error")
    
    def restart_kakaotalk(self):
        """카카오톡 재시작"""
        if not messagebox.askyesno("확인", "카카오톡을 재시작하시겠습니까?"):
            return
        
        if SystemUtils.restart_kakaotalk():
            self._show_toast("카카오톡이 재시작되었습니다.", "success")
        else:
            self._show_toast("카카오톡 재시작에 실패했습니다. 수동으로 재시작해주세요.", "error")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UI 업데이트
    # ═══════════════════════════════════════════════════════════════════════════
    def _update_status(self):
        """상태 업데이트"""
        try:
            status, blocked, total = self.hosts_manager.get_block_status(self.domain_manager.domains)
            
            if status == BlockStatus.FULLY_BLOCKED:
                self.status_label.config(text=f"✅ 모든 광고 차단 중 ({blocked}개)")
                self.progress['value'] = 100
            elif status == BlockStatus.PARTIALLY_BLOCKED:
                self.status_label.config(text=f"⚠️ 부분 차단: {blocked}/{total}개")
                self.progress['value'] = (blocked / total) * 100 if total > 0 else 0
            elif status == BlockStatus.NOT_BLOCKED:
                self.status_label.config(text="❌ 광고 차단되지 않음")
                self.progress['value'] = 0
            else:
                self.status_label.config(text="⚠️ 상태 확인 실패")
                self.progress['value'] = 0
                
        except Exception as e:
            self.logger.error(f"상태 업데이트 실패: {e}")
    
    def _update_kakao_status(self):
        """카카오톡 상태 업데이트"""
        if SystemUtils.is_kakaotalk_running():
            self.kakao_status_label.config(text="카카오톡: ✅ 실행 중")
        else:
            self.kakao_status_label.config(text="카카오톡: ❌ 실행 안 됨")
    
    def _update_domain_count(self):
        """도메인 수 업데이트"""
        self.domain_count_label.config(
            text=f"등록된 차단 도메인: {len(self.domain_manager.domains)}개"
        )
    
    def _update_ui_periodically(self):
        """주기적 UI 업데이트"""
        self._update_status()
        self._update_kakao_status()
        self._update_domain_count()
        self._process_log_queue()
        
        # 3초마다 업데이트
        self.root.after(3000, self._update_ui_periodically)
    
    def _process_log_queue(self):
        """로그 큐 처리"""
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                # 로그 메시지 처리 (콘솔에만 출력, GUI 표시는 별도)
                if hasattr(self, 'logger'):
                    pass  # 이미 파일/콘솔에 기록됨
            except queue.Empty:
                break
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 모니터링
    # ═══════════════════════════════════════════════════════════════════════════
    def _start_monitoring(self):
        """모니터링 시작"""
        if not self.settings.monitoring_enabled:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitoring_thread.start()
    
    def _monitor_loop(self):
        """모니터링 루프 - 차단 상태 주기적 확인"""
        last_status = None
        while self.monitoring_active and self.settings.monitoring_enabled:
            try:
                time.sleep(self.settings.monitoring_interval)
                
                # 차단 상태 확인
                if self.domain_manager.domains:
                    status, _, _ = self.hosts_manager.get_block_status(self.domain_manager.domains)
                    
                    # 상태 변경 감지
                    if last_status is not None and last_status != status:
                        if status == BlockStatus.NOT_BLOCKED:
                            self.root.after(0, lambda: self._show_toast("⚠️ 광고 차단이 해제되었습니다!", "warning"))
                        elif status == BlockStatus.FULLY_BLOCKED and last_status != BlockStatus.FULLY_BLOCKED:
                            self.root.after(0, lambda: self._show_toast("✅ 광고 차단이 적용되었습니다", "success"))
                    
                    last_status = status
                    
            except Exception:
                break
    
    def _show_toast(self, message: str, toast_type: str = "info"):
        """Toast 알림 표시"""
        ToastWidget(self.root, message, toast_type)
    
    def _toggle_monitoring(self):
        """모니터링 토글"""
        self.settings.monitoring_enabled = self.monitor_var.get()
        self.settings.save(SETTINGS_FILE)
    
    def _start_layout_hider(self):
        """광고 레이아웃 숨기기 시작"""
        if self.settings.hide_ad_layout:
            self.ad_layout_hider.start()
    
    def _toggle_layout_hider(self):
        """광고 레이아웃 숨기기 토글"""
        self.settings.hide_ad_layout = self.hide_layout_var.get()
        self.settings.save(SETTINGS_FILE)
        if self.settings.hide_ad_layout:
            self.ad_layout_hider.start()
        else:
            self.ad_layout_hider.stop()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 다이얼로그
    # ═══════════════════════════════════════════════════════════════════════════
    def _open_domain_editor(self):
        """도메인 편집기 열기"""
        DomainEditorDialog(self.root, self)
    
    def _open_hosts_viewer(self):
        """hosts 파일 뷰어 열기"""
        HostsViewerDialog(self.root, self.hosts_manager)
    
    def _open_log_viewer(self):
        """로그 뷰어 열기"""
        LogViewerDialog(self.root, LOG_FILE)
    
    def _show_statistics(self):
        """통계 표시"""
        status, blocked, total = self.hosts_manager.get_block_status(self.domain_manager.domains)
        kakao_running = "실행 중" if SystemUtils.is_kakaotalk_running() else "실행 안 됨"
        
        stats = f"""📊 통계 정보

• 등록된 도메인: {total}개
• 현재 차단 중: {blocked}개
• 차단율: {(blocked/total*100):.1f}%

• 카카오톡: {kakao_running}
• 모니터링: {'활성' if self.settings.monitoring_enabled else '비활성'}
• 백그라운드 모드: {'활성' if self.settings.minimize_to_tray else '비활성'}

• 설정 파일: {SETTINGS_FILE}
• 도메인 파일: {DOMAINS_FILE}
• 로그 파일: {LOG_FILE}"""
        
        messagebox.showinfo("통계", stats)
    
    def _show_help(self):
        """도움말 표시"""
        help_text = """■ 사용 방법

1. 관리자 권한으로 실행
   - 우클릭 → '관리자 권한으로 실행'

2. '광고 차단 시작' 버튼 클릭

3. 카카오톡 재시작
   - 프로그램 내 '카톡 재시작' 버튼 사용
   - 또는 수동으로 카카오톡 종료 후 재실행

■ 주요 기능

• hosts 파일 기반 광고 차단
• 시스템 트레이 백그라운드 실행
• 카카오톡 프로세스 모니터링
• 자동 백업/복원

■ 문제 해결

• 광고가 여전히 보이는 경우:
  - DNS 캐시 초기화 후 재시도
  - 카카오톡 완전 종료 후 재시작

• 권한 오류 발생 시:
  - 반드시 관리자 권한으로 실행"""
        
        messagebox.showinfo("사용 방법", help_text)
    
    def _show_about(self):
        """정보 표시"""
        about_text = f"""{APP_NAME}
버전 {VERSION}

hosts 파일 기반 광고 차단 도구

• 카카오톡 PC 버전 광고 제거
• 시스템 트레이 지원
• 자동 백업 기능

참고: github.com/{GITHUB_REPO}"""
        
        messagebox.showinfo("정보", about_text)
    
    def _flush_dns(self):
        """DNS 캐시 초기화"""
        if SystemUtils.flush_dns():
            messagebox.showinfo("성공", "DNS 캐시가 초기화되었습니다.")
        else:
            messagebox.showwarning("알림", "DNS 캐시 초기화에 실패했습니다.")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 설정/백업 관련
    # ═══════════════════════════════════════════════════════════════════════════
    def _create_backup(self):
        """백업 생성"""
        backup_path = self.hosts_manager.create_backup()
        if backup_path:
            messagebox.showinfo("성공", f"백업 생성 완료:\n{backup_path}")
        else:
            messagebox.showerror("오류", "백업 생성에 실패했습니다.")
    
    def _restore_backup(self):
        """백업 복원"""
        backup_dir = os.path.dirname(SystemUtils.get_hosts_path())
        filepath = filedialog.askopenfilename(
            title="백업 파일 선택",
            initialdir=backup_dir,
            filetypes=[("백업 파일", "*.backup_*"), ("모든 파일", "*.*")]
        )
        
        if filepath:
            if messagebox.askyesno("확인", f"이 백업으로 복원하시겠습니까?\n{filepath}"):
                if self.hosts_manager.restore_backup(filepath):
                    SystemUtils.flush_dns()
                    self._update_status()
                    messagebox.showinfo("성공", "복원이 완료되었습니다.")
                else:
                    messagebox.showerror("오류", "복원에 실패했습니다.")
    
    def _reset_domains(self):
        """도메인 초기화"""
        if messagebox.askyesno("확인", "도메인 목록을 기본값으로 초기화하시겠습니까?"):
            self.domain_manager.reset_to_default()
            self._update_domain_count()
            messagebox.showinfo("성공", "도메인 목록이 초기화되었습니다.")
    
    def _export_settings(self):
        """설정 내보내기"""
        filepath = filedialog.asksaveasfilename(
            title="설정 내보내기",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json")]
        )
        
        if filepath:
            try:
                export_data = {
                    'settings': self.settings.__dict__,
                    'domains': self.domain_manager.domains,
                    'version': VERSION
                }
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("성공", "설정이 내보내졌습니다.")
            except Exception as e:
                messagebox.showerror("오류", f"내보내기 실패:\n{e}")
    
    def _import_settings(self):
        """설정 가져오기"""
        filepath = filedialog.askopenfilename(
            title="설정 가져오기",
            filetypes=[("JSON 파일", "*.json")]
        )
        
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    import_data = json.load(f)
                
                if 'domains' in import_data:
                    self.domain_manager.domains = import_data['domains']
                    self.domain_manager.save()
                
                self._update_status()
                self._update_domain_count()
                messagebox.showinfo("성공", "설정을 가져왔습니다.")
            except Exception as e:
                messagebox.showerror("오류", f"가져오기 실패:\n{e}")
    
    def _open_hosts_in_editor(self):
        """hosts 파일을 시스템 편집기로 열기"""
        try:
            hosts_path = SystemUtils.get_hosts_path()
            if platform.system() == "Windows":
                os.startfile(hosts_path)
            else:
                subprocess.run(["xdg-open", hosts_path])
        except Exception as e:
            messagebox.showerror("오류", f"파일을 열 수 없습니다:\n{e}")
    
    def _restart_as_admin(self):
        """관리자 권한으로 재실행"""
        if messagebox.askyesno("확인", "관리자 권한으로 재실행하시겠습니까?"):
            SystemUtils.run_as_admin()
    
    def _toggle_tray_option(self):
        """트레이 옵션 토글"""
        self.settings.minimize_to_tray = self.tray_var.get()
        self.settings.save(SETTINGS_FILE)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 윈도우 관리
    # ═══════════════════════════════════════════════════════════════════════════
    def _check_admin(self):
        """관리자 권한 확인"""
        if not SystemUtils.is_admin():
            self.logger.warning("관리자 권한 없이 실행됨")
            messagebox.showwarning(
                "권한 알림",
                "이 프로그램은 hosts 파일을 수정하기 위해\n"
                "관리자 권한이 필요합니다.\n\n"
                "일부 기능이 제한될 수 있습니다.\n"
                "우클릭 → '관리자 권한으로 실행'을 권장합니다."
            )
    
    def show_window(self):
        """윈도우 표시"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def _on_closing(self):
        """창 닫기 이벤트"""
        if self.settings.minimize_to_tray and TRAY_AVAILABLE:
            self.root.withdraw()
            if not self.tray_icon:
                self.tray_icon = TrayIcon(self)
                self.tray_icon.create()
        else:
            self.quit_app()
    
    def quit_app(self):
        """앱 종료"""
        self.monitoring_active = False
        self.ad_layout_hider.stop()
        self.settings.save(SETTINGS_FILE)
        
        if self.tray_icon:
            self.tray_icon.stop()
        
        self.logger.info("애플리케이션 종료")
        self.root.quit()
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# 다이얼로그 클래스들
# ═══════════════════════════════════════════════════════════════════════════════
class DomainEditorDialog(tk.Toplevel):
    """도메인 편집 다이얼로그"""
    
    def __init__(self, parent, app: AdBlockerApp):
        super().__init__(parent)
        self.app = app
        
        self.title("차단 도메인 편집")
        self.geometry("500x450")
        self.transient(parent)
        self.grab_set()
        
        self._create_ui()
        self._load_domains()
    
    def _create_ui(self):
        """UI 생성"""
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 리스트
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            font=('Consolas', 10),
            yscrollcommand=scrollbar.set
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        # 입력 영역
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.entry = ttk.Entry(input_frame, font=('Consolas', 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self._add_domain())
        
        ttk.Button(input_frame, text="추가", command=self._add_domain).pack(side=tk.RIGHT)
        
        # 버튼 영역
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="선택 삭제", command=self._remove_selected).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="기본값 복원", command=self._restore_defaults).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="저장", command=self._save_and_close).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side=tk.RIGHT, padx=5)
    
    def _load_domains(self):
        """도메인 목록 로드"""
        self.listbox.delete(0, tk.END)
        for domain in self.app.domain_manager.domains:
            self.listbox.insert(tk.END, domain)
    
    def _add_domain(self):
        """도메인 추가"""
        domain = self.entry.get().strip().lower()
        if domain and domain not in self.listbox.get(0, tk.END):
            self.listbox.insert(tk.END, domain)
            self.entry.delete(0, tk.END)
    
    def _remove_selected(self):
        """선택 항목 삭제"""
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
    
    def _restore_defaults(self):
        """기본값 복원"""
        if messagebox.askyesno("확인", "기본 도메인 목록으로 복원하시겠습니까?", parent=self):
            self.listbox.delete(0, tk.END)
            for domain in DEFAULT_AD_DOMAINS:
                self.listbox.insert(tk.END, domain)
    
    def _save_and_close(self):
        """저장 후 닫기"""
        self.app.domain_manager.domains = list(self.listbox.get(0, tk.END))
        self.app.domain_manager.save()
        self.app._update_domain_count()
        self.destroy()


class HostsViewerDialog(tk.Toplevel):
    """hosts 파일 뷰어 다이얼로그"""
    
    def __init__(self, parent, hosts_manager: HostsManager):
        super().__init__(parent)
        self.hosts_manager = hosts_manager
        
        self.title("hosts 파일 내용")
        self.geometry("700x500")
        self.transient(parent)
        
        self._create_ui()
        self._load_content()
    
    def _create_ui(self):
        """UI 생성"""
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 텍스트 영역
        self.text = ScrolledText(
            main_frame,
            font=('Consolas', 10),
            wrap=tk.NONE
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        
        # 버튼
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="새로고침", command=self._load_content).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="닫기", command=self.destroy).pack(side=tk.RIGHT)
    
    def _load_content(self):
        """내용 로드"""
        try:
            content = self.hosts_manager.read_content()
            self.text.config(state=tk.NORMAL)
            self.text.delete(1.0, tk.END)
            self.text.insert(1.0, content)
            self.text.config(state=tk.DISABLED)
        except Exception as e:
            self.text.config(state=tk.NORMAL)
            self.text.delete(1.0, tk.END)
            self.text.insert(1.0, f"오류: {e}")
            self.text.config(state=tk.DISABLED)


class LogViewerDialog(tk.Toplevel):
    """로그 뷰어 다이얼로그"""
    
    def __init__(self, parent, log_file: str):
        super().__init__(parent)
        self.log_file = log_file
        
        self.title("로그 뷰어")
        self.geometry("700x400")
        self.transient(parent)
        
        self._create_ui()
        self._load_logs()
    
    def _create_ui(self):
        """UI 생성"""
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 텍스트 영역
        self.text = ScrolledText(
            main_frame,
            font=('Consolas', 9),
            wrap=tk.WORD
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        
        # 버튼
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="새로고침", command=self._load_logs).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="로그 지우기", command=self._clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="닫기", command=self.destroy).pack(side=tk.RIGHT)
    
    def _load_logs(self):
        """로그 로드"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = "로그 파일이 없습니다."
            
            self.text.config(state=tk.NORMAL)
            self.text.delete(1.0, tk.END)
            self.text.insert(1.0, content)
            self.text.see(tk.END)
            self.text.config(state=tk.DISABLED)
        except Exception as e:
            self.text.config(state=tk.NORMAL)
            self.text.insert(tk.END, f"오류: {e}")
            self.text.config(state=tk.DISABLED)
    
    def _clear_logs(self):
        """로그 지우기"""
        if messagebox.askyesno("확인", "로그를 모두 지우시겠습니까?", parent=self):
            try:
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.write("")
                self._load_logs()
            except Exception as e:
                messagebox.showerror("오류", f"로그 삭제 실패:\n{e}", parent=self)


# ═══════════════════════════════════════════════════════════════════════════════
# 엔트리 포인트
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    """메인 함수"""
    # 중복 실행 방지 (Windows)
    if platform.system() == "Windows":
        try:
            import win32event
            import win32api
            from winerror import ERROR_ALREADY_EXISTS
            
            mutex = win32event.CreateMutex(None, False, "KakaoTalkAdBlocker_Mutex")
            if win32api.GetLastError() == ERROR_ALREADY_EXISTS:
                messagebox.showwarning("알림", "프로그램이 이미 실행 중입니다.")
                return
        except ImportError:
            pass
    
    # 메인 윈도우 생성
    root = tk.Tk()
    
    # DPI 인식 설정 (Windows)
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    
    # 애플리케이션 실행
    app = AdBlockerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
