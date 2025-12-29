# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v8.0
=========================================
- v8.0 Overhaul:
    - Merged optimized PID scanning from v5.1
    - Applied Modern Flat UI design
    - Integrated AdFit registry blocking
    - Enhanced robustness for HiDPI and layout fixing
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

# ═══════════════════════════════════════════════════════════════════════════════
# 서드파티 라이브러리
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
# 상수 및 설정
# ═══════════════════════════════════════════════════════════════════════════════
VERSION = "8.0.0"
APP_NAME = "KakaoTalk AdBlocker Pro"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "adblock_settings.json")
DOMAINS_FILE = os.path.join(BASE_DIR, "blocked_domains.txt")
LOG_FILE = os.path.join(BASE_DIR, "adblock.log")

# 색상 테마 (카카오 스타일 + 모던 플랫)
COLORS = {
    "primary": "#FEE500",       # 카카오 옐로우
    "primary_dark": "#FDD835",  # 호버 색상
    "bg": "#FFFFFF",           
    "text": "#191919",
    "sub_text": "#757575",
    "success": "#2E7D32",
    "warning": "#FF6F00",
    "error": "#D32F2F",
    "surface": "#F8F9FA",      # 카드 배경
    "border": "#E9ECEF"
}

FONTS = {
    "header": ("맑은 고딕", 14, "bold"),
    "title": ("맑은 고딕", 11, "bold"),
    "body": ("맑은 고딕", 10),
    "log": ("Consolas", 9)
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
# 로깅 시스템
# ═══════════════════════════════════════════════════════════════════════════════
class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        try: self.log_queue.put_nowait(self.format(record))
        except: pass

def setup_logging():
    log_queue = queue.Queue(maxsize=100)
    logger = logging.getLogger("AdBlocker")
    logger.setLevel(logging.INFO)
    
    if logger.handlers: logger.handlers.clear()
    
    fmt = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    
    # File Handler
    try:
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except: pass
    
    # Queue Handler
    qh = QueueHandler(log_queue)
    qh.setFormatter(fmt)
    logger.addHandler(qh)
    return logger, log_queue


# ═══════════════════════════════════════════════════════════════════════════════
# 설정 관리
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
        except: pass
        return cls()
    
    def save(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
        except: pass


# ═══════════════════════════════════════════════════════════════════════════════
# Windows API
# ═══════════════════════════════════════════════════════════════════════════════
class User32:
    lib = ctypes.windll.user32 if platform.system() == "Windows" else None
    
    @staticmethod
    def get_pid(hwnd):
        if not User32.lib: return 0
        pid = ctypes.c_ulong()
        User32.lib.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    @staticmethod
    def get_class(hwnd):
        if not User32.lib: return ""
        buf = ctypes.create_unicode_buffer(256)
        User32.lib.GetClassNameW(hwnd, buf, 256)
        return buf.value

    @staticmethod
    def get_text(hwnd):
        if not User32.lib: return ""
        length = User32.lib.GetWindowTextLengthW(hwnd)
        if length == 0: return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        User32.lib.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

# ═══════════════════════════════════════════════════════════════════════════════
# 비즈니스 로직 (Optimized)
# ═══════════════════════════════════════════════════════════════════════════════
class AdLayoutHider:
    """Windows API를 이용한 광고 영역 숨김 및 리사이징 (Performance Optimized)"""
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
        self.logger.info("Layout Optimizer Started (PID Mode)")

    def stop(self):
        self.active = False

    def _loop(self):
        while self.active:
            try:
                self._scan_and_fix()
                # PID가 있으면 1.5초, 없으면 3초 (Adaptive Polling)
                time.sleep(1.5 if self.kakao_pid else 3.0)
            except: 
                time.sleep(3)

    def _get_kakao_pid(self):
        """Find KakaoTalk PID (Check psutil first, then tasklist fallback)"""
        # 1. psutil
        if PSUTIL_AVAILABLE:
            for p in psutil.process_iter(['name', 'pid']):
                if 'kakaotalk.exe' in (p.info['name'] or '').lower():
                    return p.info['pid']
        
        # 2. tasklist fallback (slower)
        try:
            res = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq kakaotalk.exe', '/FO', 'CSV', '/NH'], 
                               capture_output=True, text=True, creationflags=0x08000000)
            line = res.stdout.strip()
            if line and "kakaotalk.exe" in line.lower():
                # CSV format: "KakaoTalk.exe","1234","Console","1","50,000 K"
                parts = line.split(',')
                if len(parts) >= 2:
                    return int(parts[1].replace('"', ''))
        except: pass
        return None

    def _scan_and_fix(self):
        self.kakao_pid = self._get_kakao_pid()
        
        def enum_cb(hwnd, _):
            # PID Filtering: Only inspect windows belonging to KakaoTalk
            if self.kakao_pid:
                if User32.get_pid(hwnd) != self.kakao_pid:
                    return True

            cls = User32.get_class(hwnd)
            if cls == "EVA_Window":
                self._process_eva_window(hwnd)
            return True
        
        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumWindows(PROC(enum_cb), 0)

    def _process_eva_window(self, parent_hwnd):
        # Target Main Window only by checking title
        title = User32.get_text(parent_hwnd)
        if "카카오톡" not in title and "KakaoTalk" not in title:
            return

        def child_cb(hwnd, _):
            text = User32.get_text(hwnd)
            
            # 1. Hide Ad Views
            if text.startswith("BannerAdView") or text.startswith("AdView"):
                if self.user32.IsWindowVisible(hwnd):
                    self.user32.ShowWindow(hwnd, 0) # SW_HIDE
                    self.logger.info(f"Ad hidden: {text}")
            
            # 2. Resize Main View
            elif text.startswith("OnlineMainView"):
                self._resize_main_view(hwnd, parent_hwnd)
            return True

        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumChildWindows(parent_hwnd, PROC(child_cb), 0)

    def _resize_main_view(self, hwnd, parent_hwnd):
        try:
            # Parent Client Area
            pr = ctypes.wintypes.RECT()
            self.user32.GetClientRect(parent_hwnd, ctypes.byref(pr))
            parent_h = pr.bottom - pr.top

            # Child Window Rect
            cr = ctypes.wintypes.RECT()
            self.user32.GetWindowRect(hwnd, ctypes.byref(cr))
            
            # Convert Child Top-Left to Parent Client Coords
            pt = ctypes.wintypes.POINT(cr.left, cr.top)
            self.user32.ScreenToClient(parent_hwnd, ctypes.byref(pt))
            
            # Target Height = Parent Height - Child's Y Position
            target_h = parent_h - pt.y
            
            if target_h < 100: return
            
            curr_h = cr.bottom - cr.top
            curr_w = cr.right - cr.left

            # Resize if diff > 5px
            if abs(target_h - curr_h) > 5:
                self.user32.SetWindowPos(hwnd, 0, 0, 0, curr_w, target_h, 
                                       0x0002 | 0x0004 | 0x0010 | 0x0020) # NOMOVE | NOZORDER | NOACTIVATE | FRAMECHANGED
        except: pass

class AdFitBlocker:
    """AdFit Registry Blocking"""
    KEY = r"SOFTWARE\Kakao\AdFit"
    def __init__(self, logger):
        self.logger = logger
        self.active = False
    def start(self):
        if self.active: return
        self.active = True
        threading.Thread(target=self._loop, daemon=True).start()
    def stop(self): self.active = False
    def _loop(self):
        while self.active:
            self._update()
            time.sleep(10)
    def _update(self):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY, 0, winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS)
            idx = 0
            cur = str(int(time.time()))
            while True:
                try:
                    name = winreg.EnumKey(k, idx)
                    path = f"{self.KEY}\\{name}"
                    try:
                        sk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE)
                        winreg.SetValueEx(sk, "LUD", 0, winreg.REG_SZ, cur)
                        winreg.CloseKey(sk)
                    except: pass
                    idx += 1
                except OSError: break
            winreg.CloseKey(k)
        except: pass

class SystemManager:
    @staticmethod
    def is_admin():
        try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False
    
    @staticmethod
    def run_as_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit(0)
    
    @staticmethod
    def flush_dns():
        try: subprocess.run("ipconfig /flushdns", capture_output=True, creationflags=0x08000000); return True
        except: return False
    
    @staticmethod
    def is_process_running(name):
        # 1. PSUtil
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name']):
                    if name.lower() in (p.info['name'] or '').lower(): return True
            except: pass
        # 2. Tasklist
        try:
            res = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}.exe', '/NH'], 
                               capture_output=True, text=True, creationflags=0x08000000)
            return name.lower() in res.stdout.lower()
        except: return False
    
    @staticmethod
    def restart_process(name):
        exe_path = None
        # Try to find path before killing
        if PSUTIL_AVAILABLE:
            try:
                for p in psutil.process_iter(['name', 'exe']):
                    if name.lower() in (p.info['name'] or '').lower():
                        exe_path = p.info['exe']
                        break
            except: pass
            
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
            if os.path.exists(p): os.startfile(p); return True
        return False

class HostsManager:
    PATH = r"C:\Windows\System32\drivers\etc\hosts"
    START, END = "# [KakaoTalk AdBlock Start]", "# [KakaoTalk AdBlock End]"
    def __init__(self, logger): self.logger = logger
    def block(self, domains):
        try:
            with open(self.PATH, 'r', encoding='utf-8', errors='ignore') as f: c = f.read()
        except: return False
        lines = []
        skip = False
        for l in c.splitlines():
            if self.START in l: skip = True; continue
            if self.END in l: skip = False; continue
            if not skip and not any(d in l and ("0.0.0.0" in l or "127.0.0.1" in l) for d in domains): lines.append(l)
        new = "\n".join(lines).strip() + f"\n\n{self.START}\n# Updated: {datetime.now()}\n" + "\n".join(f"0.0.0.0 {d}" for d in domains) + f"\n{self.END}\n"
        try:
            os.chmod(self.PATH, 0o777)
            with open(self.PATH, 'w', encoding='utf-8') as f: f.write(new)
            return True
        except: return False
    
    def get_status(self, domains):
        try:
            with open(self.PATH, 'r', encoding='utf-8', errors='ignore') as f: c = f.read()
            return sum(1 for d in domains if f"0.0.0.0 {d}" in c) / len(domains) if domains else 0
        except: return 0

class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerPro"
    @staticmethod
    def is_enabled():
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(k, StartupManager.NAME)
            winreg.CloseKey(k); return True
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
        self.icon = pystray.Icon("KakaoTalkAdBlocker", self.create_icon(), APP_NAME, pystray.Menu(
            pystray.MenuItem("열기", lambda: self.app.root.after(0, self.app.show_window)),
            pystray.MenuItem("종료", lambda: self.app.root.after(0, self.app.quit_app))
        ))
    def create_icon(self):
        img = Image.new('RGBA', (64, 64), (0,0,0,0)); d = ImageDraw.Draw(img)
        d.polygon([(32,4),(60,14),(60,32),(32,60),(4,32),(4,14)], fill=(254,229,0,255), outline=(200,180,0,255))
        d.line([(18,32),(26,42),(46,20)], fill=(25,25,25,255), width=5); return img
    def start(self): 
        if not self.running and TRAY_AVAILABLE: 
            self.running = True; threading.Thread(target=self.icon.run, daemon=True).start()
    def stop(self): 
        if self.icon: self.icon.stop(); self.running = False


# ═══════════════════════════════════════════════════════════════════════════════
# UI Components (Modern)
# ═══════════════════════════════════════════════════════════════════════════════
class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=120, height=40, 
                 bg_color=COLORS["primary"], fg_color=COLORS["text"], hover_color=COLORS["primary_dark"]):
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0)
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text = text
        self.fg_color = fg_color
        self.rect = self.create_rounded_rect(2, 2, width-2, height-2, 8, fill=bg_color, outline="")
        self.label = self.create_text(width/2, height/2, text=text, fill=fg_color, font=("맑은 고딕", 10, "bold"))
        self.bind("<Enter>", lambda e: self.itemconfig(self.rect, fill=self.hover_color) or self.config(cursor="hand2"))
        self.bind("<Leave>", lambda e: self.itemconfig(self.rect, fill=self.bg_color) or self.config(cursor=""))
        self.bind("<Button-1>", lambda e: self.move(self.label, 1, 1))
        self.bind("<ButtonRelease-1>", self._on_release)

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y1+r, x2, y2-r, x2, y2-r, x2, y2, x2-r, y2, x2-r, y2, x1+r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y2-r, x1, y1+r, x1, y1+r, x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def _on_release(self, e):
        self.move(self.label, -1, -1)
        if self.command: self.command()

class StatusCard(tk.Frame):
    def __init__(self, parent, title, value, icon="ℹ️", color=COLORS["success"]):
        super().__init__(parent, bg=COLORS["surface"], padx=15, pady=15)
        # Border effect
        self.config(highlightbackground=COLORS["border"], highlightthickness=1)
        
        tk.Label(self, text=title, bg=COLORS["surface"], fg=COLORS["sub_text"], font=("맑은 고딕", 9)).pack(anchor="w")
        self.value_lbl = tk.Label(self, text=f"{icon} {value}", bg=COLORS["surface"], fg=color, font=("맑은 고딕", 11, "bold"))
        self.value_lbl.pack(anchor="w", pady=(5, 0))

    def update_status(self, text, color=None):
        self.value_lbl.config(text=text)
        if color: self.value_lbl.config(fg=color)

# ═══════════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow:
    def __init__(self, root: tk.Tk, minimized=False):
        self.root = root
        self._setup_hidpi()
        self.logger, self.log_queue = setup_logging()
        self.settings = AppSettings.load()
        
        self.layout_hider = AdLayoutHider(self.logger)
        self.adfit_blocker = AdFitBlocker(self.logger)
        self.hosts_mgr = HostsManager(self.logger)
        self.tray = TrayManager(self)
        
        self._setup_ui()
        self.tray.setup(); self.tray.start()
        
        if self.settings.hide_layout: self.layout_hider.start()
        if self.settings.block_adfit: self.adfit_blocker.start()
        
        self._start_monitor()
        self._start_log_consumer()
        
        if minimized or self.settings.minimize_to_tray: # Fixed logic for start minimized
             if '--minimized' in sys.argv or self.settings.minimize_to_tray:
                 pass # Logic handled in main() or check here

    def _setup_hidpi(self):
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except: pass

    def _setup_ui(self):
        self.root.title(APP_NAME)
        self.root.geometry("520x680")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Header
        h = tk.Frame(self.root, bg=COLORS["primary"], height=80)
        h.pack(fill="x"); h.pack_propagate(False)
        
        icon_f = tk.Frame(h, bg=COLORS["primary"])
        icon_f.pack(side="left", padx=20)
        tk.Label(icon_f, text="🛡️", bg=COLORS["primary"], font=("Segoe UI Emoji", 24)).pack()
        
        title_f = tk.Frame(h, bg=COLORS["primary"])
        title_f.pack(side="left", fill="y", pady=18)
        tk.Label(title_f, text=APP_NAME, bg=COLORS["primary"], fg="#3A1D1D", font=FONTS["header"]).pack(anchor="w")
        tk.Label(title_f, text=f"v{VERSION}", bg=COLORS["primary"], fg="#665500", font=("맑은 고딕", 9)).pack(anchor="w")

        # Content
        c = tk.Frame(self.root, bg=COLORS["bg"], padx=25, pady=20)
        c.pack(fill="both", expand=True)

        # Dashboard
        d = tk.Frame(c, bg=COLORS["bg"])
        d.pack(fill="x", pady=(0, 20))
        self.card_status = StatusCard(d, "보호 모듈", "작동 중", "⚡")
        self.card_status.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.card_proc = StatusCard(d, "카카오톡", "감지 안됨", "💤", COLORS["sub_text"])
        self.card_proc.pack(side="left", fill="x", expand=True)

        # Smart Optimize
        self.btn_opt = ModernButton(c, "✨ 스마트 최적화", self._optimize, width=470, height=50)
        self.btn_opt.pack(pady=5)
        tk.Label(c, text="광고 차단 + DNS 초기화 + 프로세스 재시작", bg=COLORS["bg"], fg=COLORS["sub_text"], font=("맑은 고딕", 8)).pack(pady=(2, 20))

        # Controls
        cf = tk.LabelFrame(c, text="설정", bg=COLORS["bg"], font=FONTS["title"], padx=15, pady=15)
        cf.pack(fill="x", pady=10)
        
        self.v_auto = tk.BooleanVar(value=StartupManager.is_enabled())
        self.v_tray = tk.BooleanVar(value=self.settings.minimize_to_tray)
        self.v_hide = tk.BooleanVar(value=self.settings.hide_layout)
        self.v_adfit = tk.BooleanVar(value=self.settings.block_adfit)

        chk_style = {"bg": COLORS["bg"], "activebackground": COLORS["bg"], "font": FONTS["body"], "pady": 2}
        
        tk.Checkbutton(cf, text="윈도우 시작 시 자동 실행", variable=self.v_auto, command=self._save_set, **chk_style).pack(anchor="w")
        tk.Checkbutton(cf, text="닫을 때 트레이로 최소화", variable=self.v_tray, command=self._save_set, **chk_style).pack(anchor="w")
        tk.Checkbutton(cf, text="광고 레이아웃 자동 제거 (빈 공간 삭제)", variable=self.v_hide, command=self._save_set, **chk_style).pack(anchor="w")
        tk.Checkbutton(cf, text="팝업 광고 차단 (AdFit 레지스트리)", variable=self.v_adfit, command=self._save_set, **chk_style).pack(anchor="w")

        # Log
        lf = tk.LabelFrame(c, text="실시간 로그", bg=COLORS["bg"], font=FONTS["title"], padx=5, pady=5)
        lf.pack(fill="both", expand=True, pady=10)
        self.log_widget = scrolledtext.ScrolledText(lf, height=5, font=FONTS["log"], state='disabled', bg="#F1F1F1")
        self.log_widget.pack(fill="both", expand=True)

        # Footer
        ff = tk.Frame(c, bg=COLORS["bg"])
        ff.pack(fill="x", side="bottom")
        ModernButton(ff, "📂 로그 폴더", lambda: os.startfile(BASE_DIR), width=100, height=30, bg_color="#E0E0E0").pack(side="left")
        ModernButton(ff, "📝 차단 목록", lambda: os.startfile(DOMAINS_FILE) if os.path.exists(DOMAINS_FILE) else None, width=100, height=30, bg_color="#E0E0E0").pack(side="right")

    def _log(self, msg):
        self.log_widget.config(state='normal')
        self.log_widget.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_widget.see('end')
        self.log_widget.config(state='disabled')

    def _start_log_consumer(self):
        def loop():
            while True:
                try: 
                    msg = self.log_queue.get_nowait()
                    self.root.after(0, self._log, msg)
                except: pass
                time.sleep(0.1)
        threading.Thread(target=loop, daemon=True).start()

    def _monitor(self):
        def loop():
            while True:
                is_run = SystemManager.is_process_running("KakaoTalk")
                self.root.after(0, self._update_status, is_run)
                time.sleep(2)
        threading.Thread(target=loop, daemon=True).start()

    def _update_status(self, is_run):
        if is_run:
            self.card_proc.update_status("실행 중", COLORS["success"])
        else:
            self.card_proc.update_status("종료됨", COLORS["sub_text"])

    def _optimize(self):
        if not SystemManager.is_admin(): 
            messagebox.showerror("오류", "관리자 권한이 필요합니다.")
            return

        self.logger.info("최적화 작업 시작...")
        
        # 1. Hosts Block
        cnt = self.hosts_mgr.block(DEFAULT_AD_DOMAINS)
        self.logger.info("Hosts 파일 업데이트 완료")
        
        # 2. DNS Flush
        SystemManager.flush_dns()
        self.logger.info("DNS 캐시 초기화 완료")
        
        # 3. Restart
        if SystemManager.restart_process("kakaotalk.exe"):
            self.logger.info("카카오톡 재시작 완료")
            messagebox.showinfo("완료", "스마트 최적화가 완료되었습니다.")
        else:
            self.logger.warning("카카오톡을 찾을 수 없습니다.")
            messagebox.showwarning("주의", "카카오톡 재시작에 실패했습니다.\n수동으로 실행해주세요.")

    def _save_set(self):
        self.settings.auto_start = self.v_auto.get()
        self.settings.minimize_to_tray = self.v_tray.get()
        self.settings.hide_layout = self.v_hide.get()
        self.settings.block_adfit = self.v_adfit.get()
        self.settings.save()
        
        StartupManager.set_enabled(self.settings.auto_start)
        
        if self.settings.hide_layout: self.layout_hider.start()
        else: self.layout_hider.stop()
        
        if self.settings.block_adfit: self.adfit_blocker.start()
        else: self.adfit_blocker.stop()

    def _on_close(self):
        if self.settings.minimize_to_tray:
            self.hide_to_tray()
        else:
            self.quit_app()

    def hide_to_tray(self):
        self.root.withdraw()
        if self.settings.minimize_to_tray:
            self.tray.icon.notify("백그라운드에서 실행 중입니다.", APP_NAME)

    def show_window(self):
        self.root.deiconify()
        self.root.lift()

    def quit_app(self):
        self.layout_hider.stop()
        self.adfit_blocker.stop()
        self.tray.stop()
        self.root.quit()
        self.root.destroy()

if __name__ == "__main__":
    # HiDPI Support
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    # Check Admin
    if not SystemManager.is_admin():
        # Re-run logic usually goes here or show warning.
        # For simplicity in loop, just warn.
        pass

    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w', encoding='utf-8') as f: f.write("\n".join(DEFAULT_AD_DOMAINS))

    root = tk.Tk()
    
    # Check command line args for minimized start
    start_minimized = "--minimized" in sys.argv
    app = MainWindow(root, minimized=start_minimized)
    
    if start_minimized:
        root.withdraw()
    
    root.mainloop()
