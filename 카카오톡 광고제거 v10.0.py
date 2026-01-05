# -*- coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v10.0 (Advanced Sniffing Edition)
==========================================================
- Advanced Window Hierarchy Analysis
- Multi-Strategy Ad Detection (Class, Size, Position Heuristics)
- Real-time Ad Sniffing with Statistics Dashboard
- Enhanced UI with Debug Mode
"""

import sys
import os
import json
import time
import logging
import logging.handlers
import ctypes
import ctypes.wintypes
import threading
import subprocess
import winreg
import platform
import shutil
from datetime import datetime
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable, Dict

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFrame, 
                             QSystemTrayIcon, QMenu, QStackedWidget, 
                             QScrollArea, QSizePolicy, QGraphicsDropShadowEffect,
                             QTextEdit, QMessageBox, QCheckBox, QRadioButton, QButtonGroup,
                             QGraphicsOpacityEffect, QGridLayout, QComboBox, QSlider,
                             QGroupBox, QSpinBox)
from PyQt6.QtCore import (Qt, QTimer, QSize, QThread, pyqtSignal, QObject, 
                          QPropertyAnimation, QEasingCurve, QPoint, QRect, QEvent)
from PyQt6.QtGui import (QIcon, QFont, QColor, QAction, QPainter, QBrush, 
                         QPen, QLinearGradient, QGradient, QPixmap, QCursor)

# Import the new ad sniffer engine
try:
    from ad_sniffer import AdLayoutSniffer, AdDetectionResult, AdType
    SNIFFER_AVAILABLE = True
except ImportError:
    SNIFFER_AVAILABLE = False
    print("Warning: ad_sniffer module not found. Using legacy mode.")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

try:
    import darkdetect
    DARK_DETECT_AVAILABLE = True
except ImportError:
    DARK_DETECT_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════
class Config:
    VERSION = "10.0.0"
    APP_NAME = "KakaoTalk AdBlocker Pro"
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SETTINGS_FILE = os.path.join(BASE_DIR, "adblock_settings_v10.json")
    LOG_FILE = os.path.join(BASE_DIR, "adblock_v10.log")
    HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
    HOSTS_BACKUP = r"C:\Windows\System32\drivers\etc\hosts.bak"
    
    AD_DOMAINS = [
        "display.ad.daum.net", "analytics.ad.daum.net", "ad.daum.net",
        "alea.adam.ad.daum.net", "adam.ad.daum.net", "wat.ad.daum.net",
        "biz.ad.daum.net", "cs.ad.daum.net", "ad.mad.daum.net",
        "ams.ad.daum.net", "amsv2.daum.net",
        "ad.smart.kakao.com", "ad.kakao.com", "display.ad.kakao.com",
        "business.kakao.com", "ad.kakaocdn.net", "ad.kakaocdn.com",
        "track.tiara.kakao.com", "stat.tiara.kakao.com", "kakaoad.criteo.com"
    ] + [f"adimg{i}.kakaocdn.net" for i in range(1, 11)]

# ═══════════════════════════════════════════════════════════════════════════════
# Logging Setup
# ═══════════════════════════════════════════════════════════════════════════════
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("AdBlocker")
    
    # Prevent duplicate handlers on re-initialization
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    try:
        fh = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE, maxBytes=1024*1024, backupCount=3, encoding='utf-8'
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Log file setup failed: {e}")
    
    return logger

logger = setup_logging()

# ═══════════════════════════════════════════════════════════════════════════════
# Theme System
# ═══════════════════════════════════════════════════════════════════════════════
class Theme:
    PRIMARY = "#FEE500"       
    PRIMARY_DARK = "#FDD835"  
    SECONDARY = "#000000"     
    
    # Dark Mode Palette
    BG_DARK = "#1E1E1E"; SURFACE_DARK = "#252526"; BORDER_DARK = "#333333"
    TEXT_DARK = "#FFFFFF"; TEXT_SUB_DARK = "#AAAAAA"
    
    # Light Mode Palette
    BG_LIGHT = "#F9F9F9"; SURFACE_LIGHT = "#FFFFFF"; BORDER_LIGHT = "#E0E0E0"
    TEXT_LIGHT = "#333333"; TEXT_SUB_LIGHT = "#666666"
    
    SUCCESS = "#00C853"; ERROR = "#F44747"; WARNING = "#FF9800"
    INFO = "#2196F3"

    current_mode = "dark"

    @classmethod
    def set_mode(cls, mode: str):
        cls.current_mode = mode
        
    @classmethod
    def color(cls, name: str) -> str:
        if cls.current_mode == "light":
            mapping = {
                "bg": cls.BG_LIGHT, "surface": cls.SURFACE_LIGHT, "border": cls.BORDER_LIGHT,
                "text": cls.TEXT_LIGHT, "text_sub": cls.TEXT_SUB_LIGHT
            }
        else:
            mapping = {
                "bg": cls.BG_DARK, "surface": cls.SURFACE_DARK, "border": cls.BORDER_DARK,
                "text": cls.TEXT_DARK, "text_sub": cls.TEXT_SUB_DARK
            }
        return mapping.get(name, "#FF0000")

    @classmethod
    def get_style(cls) -> str:
        bg = cls.color("bg"); txt = cls.color("text"); border = cls.color("border")
        return f"""
            QMainWindow, QWidget {{ background-color: {bg}; color: {txt}; font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 14px; }}
            QFrame {{ border: none; }}
            QScrollArea {{ border: none; background: transparent; }}
            QComboBox {{ background-color: {cls.color("surface")}; border: 1px solid {border}; padding: 5px; border-radius: 5px; }}
            QComboBox::drop-down {{ border: none; }}
            QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 10px; padding-top: 10px; font-weight: bold; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
        """

# ═══════════════════════════════════════════════════════════════════════════════
# Logic Layer
# ═══════════════════════════════════════════════════════════════════════════════
class SystemManager:
    @staticmethod
    def is_admin() -> bool:
        try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False
    
    @staticmethod
    def run_as_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit(0)
    
    @staticmethod
    def flush_dns():
        try: 
            subprocess.run("ipconfig /flushdns", capture_output=True, creationflags=0x08000000)
            return True
        except Exception as e: 
            logger.error(f"DNS Flush Failed: {e}")
            return False
        
    # Process name cache for efficiency
    _process_cache: Dict[str, Tuple[bool, float]] = {}
    _cache_ttl = 2.0  # 2 second cache
    
    @staticmethod
    def process_exists(name: str) -> bool:
        """Check if process exists with caching for efficiency"""
        now = time.time()
        cache_key = name.lower()
        
        # Check cache first
        if cache_key in SystemManager._process_cache:
            cached_result, cached_time = SystemManager._process_cache[cache_key]
            if now - cached_time < SystemManager._cache_ttl:
                return cached_result
        
        # Cache miss - do actual check
        result = False
        if PSUTIL_AVAILABLE:
            try:
                # Use generator with early exit for efficiency
                target = name.lower()
                for p in psutil.process_iter(['name']):
                    try:
                        if p.info['name'] and p.info['name'].lower() == target:
                            result = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception:
                pass
        
        # Update cache
        SystemManager._process_cache[cache_key] = (result, now)
        return result

    @staticmethod
    def restart_process(name: str):
        try:
            subprocess.run(['taskkill', '/f', '/im', name], capture_output=True, creationflags=0x08000000)
            time.sleep(1)
            paths = [
                os.path.join(os.environ.get(k,''), 'Kakao', 'KakaoTalk', 'KakaoTalk.exe') 
                for k in ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA']
            ]
            for p in paths:
                if os.path.exists(p): 
                    os.startfile(p)
                    return True
        except Exception as e: 
            logger.error(f"Restart Process Failed: {e}")
        return False

@dataclass
class AppSettings:
    auto_start: bool = False
    minimize_to_tray: bool = True
    start_minimized: bool = False
    # New sniffing options
    enable_sniffing: bool = True
    sniffing_sensitivity: str = "medium"  # low, medium, high
    debug_mode: bool = False
    block_adfit: bool = True
    theme_mode: str = "system"

    @classmethod
    def load(cls):
        try:
            if os.path.exists(Config.SETTINGS_FILE):
                with open(Config.SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
                    return cls(**{k:v for k,v in data.items() if k in cls.__dataclass_fields__})
        except Exception as e:
            logger.error(f"Settings load failed: {e}")
        return cls()
    
    def save(self):
        try:
            with open(Config.SETTINGS_FILE, 'w') as f:
                json.dump(self.__dict__, f, indent=2)
        except Exception as e:
            logger.error(f"Settings Save Failed: {e}")

class HostsManager:
    START, END = "# [KakaoTalk AdBlock Start]", "# [KakaoTalk AdBlock End]"
    
    def backup(self) -> bool:
        try:
            if not os.path.exists(Config.HOSTS_BACKUP):
                shutil.copy2(Config.HOSTS_PATH, Config.HOSTS_BACKUP)
                logger.info("Hosts file backup created.")
            return True
        except Exception as e:
            logger.error(f"Backup Failed: {e}")
            return False

    def block(self, domains: List[str]) -> Tuple[bool, str]:
        self.backup()
        try:
            with open(Config.HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                c = f.read()
            lines = [l for l in c.splitlines() if self.START not in l and self.END not in l] 
            filtered = [l for l in lines if not any(d in l and "0.0.0.0" in l for d in domains)] 
            
            new = "\n".join(filtered).strip() + f"\n\n{self.START}\n# Updated: {datetime.now()}\n"
            new += "\n".join(f"0.0.0.0 {d}" for d in domains) + f"\n{self.END}\n"
            
            os.chmod(Config.HOSTS_PATH, 0o777)
            with open(Config.HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write(new)
            
            logger.info(f"Blocked {len(domains)} domains.")
            return True, f"{len(domains)} 도메인 차단됨"
        except Exception as e:
            logger.error(f"Block Failed: {e}")
            return False, str(e)

    def restore(self) -> Tuple[bool, str]:
        try:
            with open(Config.HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                c = f.read()
            lines = []
            skip = False
            for l in c.splitlines():
                if self.START in l: skip=True; continue
                if self.END in l: skip=False; continue
                if not skip: lines.append(l)
            
            with open(Config.HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines).strip() + "\n")
            logger.info("Hosts file restored.")
            return True, "Hosts 파일 복원 완료"
        except Exception as e:
            logger.error(f"Restore Failed: {e}")
            return False, str(e)

class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerPro"
    
    @staticmethod
    def set(enable: bool):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                exe = sys.executable
                path = f'"{exe}" "{os.path.abspath(sys.argv[0])}" --minimized' if exe.endswith('python.exe') else f'"{exe}" --minimized'
                winreg.SetValueEx(k, StartupManager.NAME, 0, winreg.REG_SZ, path)
            else:
                try: winreg.DeleteValue(k, StartupManager.NAME)
                except: pass
            winreg.CloseKey(k)
        except Exception as e:
            logger.error(f"Startup Set Failed: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# Workers
# ═══════════════════════════════════════════════════════════════════════════════
class WorkerSignals(QObject):
    log = pyqtSignal(str, str)
    stats_updated = pyqtSignal(dict)
    ad_detected = pyqtSignal(object)

class AdSnifferWorker(QThread):
    """New advanced ad sniffer worker using ad_sniffer module"""
    
    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self.active = False
        self.sniffer: Optional[AdLayoutSniffer] = None
    
    def run(self):
        if not SNIFFER_AVAILABLE:
            self.signals.log.emit("ERROR", "ad_sniffer 모듈을 찾을 수 없습니다")
            return
        
        self.active = True
        
        def on_log(level, msg):
            self.signals.log.emit(level, msg)
        
        def on_ad(result: AdDetectionResult):
            self.signals.ad_detected.emit(result)
        
        self.sniffer = AdLayoutSniffer(
            logger=logger,
            on_log=on_log,
            on_ad_detected=on_ad
        )
        
        self.signals.log.emit("INFO", "Advanced AdSniffer v10.0 엔진 시작")
        self.sniffer.start()
        
        # Keep thread alive and periodically emit stats
        while self.active:
            time.sleep(2)
            if self.sniffer:
                stats = self.sniffer.get_stats()
                self.signals.stats_updated.emit(stats)
        
        if self.sniffer:
            self.sniffer.stop()
    
    def stop(self):
        self.active = False
        self.wait()
    
    def inspect(self) -> str:
        if self.sniffer:
            return self.sniffer.inspect()
        return "Sniffer not running"

class AdFitWorker(QThread):
    """Legacy AdFit registry manipulation"""
    
    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self._active = False
        self._stop_event = threading.Event()
    
    def run(self):
        self._active = True
        self._stop_event.clear()
        self.signals.log.emit("INFO", "AdFit 차단기 시작")
        KEY = r"SOFTWARE\Kakao\AdFit"
        
        while self._active:
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, 
                                   winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS)
                idx = 0
                cur = str(int(time.time()))
                while True:
                    try:
                        n = winreg.EnumKey(k, idx)
                        p = f"{KEY}\\{n}"
                        try:
                            sk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, p, 0, winreg.KEY_WRITE)
                            winreg.SetValueEx(sk, "LUD", 0, winreg.REG_SZ, cur)
                            winreg.CloseKey(sk)
                        except OSError:
                            pass
                        idx += 1
                    except OSError:
                        break
                winreg.CloseKey(k)
            except FileNotFoundError:
                # Registry key doesn't exist - this is normal if AdFit not installed
                pass
            except Exception as e:
                logger.debug(f"AdFit registry check error: {e}")
            
            # Wait with interruptible sleep
            if self._stop_event.wait(timeout=5):
                break
    
    def stop(self):
        self._active = False
        self._stop_event.set()
        self.wait(timeout=2000)  # Wait max 2 seconds

# ═══════════════════════════════════════════════════════════════════════════════
# UI Components
# ═══════════════════════════════════════════════════════════════════════════════
class Toast(QWidget):
    def __init__(self, parent, text, icon="✅"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 20, 10)
        
        bg = QFrame()
        bg.setStyleSheet(f"background-color: #333333; border: 1px solid {Theme.SUCCESS}; border-radius: 20px;")
        bg.setGraphicsEffect(QGraphicsDropShadowEffect(blurRadius=10, xOffset=0, yOffset=2))
        
        bl = QHBoxLayout(bg)
        bl.addWidget(QLabel(icon))
        msg = QLabel(text)
        msg.setStyleSheet("color: white; font-weight: bold; margin-left: 5px;")
        bl.addWidget(msg)
        layout.addWidget(bg)
        
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.anim = QPropertyAnimation(self.opacity, b"opacity")
        self.pos_anim = QPropertyAnimation(self, b"pos")

    def show_message(self, duration=2000):
        self.show()
        p = self.parent()
        if not p:
            self.close()
            return
        tx = (p.width()-self.width())//2
        ty = p.height()-80
        self.move(tx, ty+20)
        self.opacity.setOpacity(0)
        
        self.anim.setDuration(300)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()
        self.pos_anim.setDuration(300)
        self.pos_anim.setStartValue(QPoint(tx, ty+20))
        self.pos_anim.setEndValue(QPoint(tx, ty))
        self.pos_anim.start()
        
        # Store timer reference to prevent garbage collection issues
        self._fade_timer = QTimer.singleShot(duration, self.fade_out)
        
    def fade_out(self):
        self.anim.setDuration(300)
        self.anim.setStartValue(1)
        self.anim.setEndValue(0)
        self.anim.finished.connect(self._cleanup)
        self.anim.start()
    
    def _cleanup(self):
        """Clean up animation objects before closing"""
        try:
            self.anim.stop()
            self.pos_anim.stop()
        except RuntimeError:
            pass  # Widget already deleted
        self.close()
        self.deleteLater()

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.is_dragging = False
        self.start_pos = QPoint()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)
        
        icon_lbl = QLabel("🛡️")
        self.lbl = QLabel(Config.APP_NAME)
        self.lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        
        layout.addWidget(icon_lbl)
        layout.addSpacing(8)
        layout.addWidget(self.lbl)
        layout.addStretch()
        
        self.btn_min = self._create_btn("─", self.minimize)
        self.btn_close = self._create_btn("✕", self.close_win, is_close=True)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_close)
        
    def _create_btn(self, text, slot, is_close=False):
        btn = QPushButton(text)
        btn.setFixedSize(40, 32)
        hover = "#E81123" if is_close else "#444"
        btn.setStyleSheet(f"QPushButton {{ border: none; background: transparent; color: #AAA; font-size: 14px; }} QPushButton:hover {{ background: {hover}; color: white; }}")
        btn.clicked.connect(slot)
        return btn
        
    def minimize(self):
        self.window().showMinimized()
    
    def close_win(self):
        self.window().close()
    
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.start_pos = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
    
    def mouseMoveEvent(self, e):
        if self.is_dragging:
            self.window().move(e.globalPosition().toPoint() - self.start_pos)
    
    def mouseReleaseEvent(self, e):
        self.is_dragging = False

class NavButton(QPushButton):
    def __init__(self, text, icon, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedHeight(45)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_emoji = icon
        self.text_label = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = Theme.color("surface") if self.isChecked() else "transparent"
        p.fillRect(self.rect(), QColor(bg))
        if self.isChecked():
            p.fillRect(0, 0, 4, 45, QColor(Theme.PRIMARY))
        
        p.setPen(QColor(Theme.PRIMARY if self.isChecked() else Theme.color("text_sub")))
        p.setFont(QFont("Segoe UI Emoji", 12))
        p.drawText(QRect(20, 0, 30, 45), Qt.AlignmentFlag.AlignVCenter, self.icon_emoji)
        
        p.setPen(QColor(Theme.color("text") if self.isChecked() else Theme.color("text_sub")))
        p.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold if self.isChecked() else QFont.Weight.Normal))
        p.drawText(QRect(55, 0, 150, 45), Qt.AlignmentFlag.AlignVCenter, self.text_label)
        p.end()

class ModernToggle(QWidget):
    toggled = pyqtSignal(bool)
    
    def __init__(self, checked=False):
        super().__init__()
        self.setFixedSize(44, 24)
        self.checked = checked
    
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_col = QColor(Theme.SUCCESS if self.checked else "#444")
        p.setBrush(track_col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 44, 24, 12, 12)
        p.setBrush(Qt.GlobalColor.white)
        x = 22 if self.checked else 2
        p.drawEllipse(x, 2, 20, 20)
        p.end()
    
    def mouseReleaseEvent(self, e):
        self.checked = not self.checked
        self.toggled.emit(self.checked)
        self.update()
    
    def setChecked(self, checked: bool):
        self.checked = checked
        self.update()

class StatCard(QFrame):
    """Statistics card widget"""
    
    def __init__(self, title: str, icon: str, initial_value: str = "0"):
        super().__init__()
        self.setFixedSize(160, 90)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        header = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 16px;")
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {Theme.color('text_sub')}; font-size: 11px; font-weight: bold;")
        header.addWidget(icon_lbl)
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)
        
        self.value_lbl = QLabel(initial_value)
        self.value_lbl.setStyleSheet(f"color: {Theme.SUCCESS}; font-size: 22px; font-weight: bold;")
        layout.addWidget(self.value_lbl)
    
    def set_value(self, value: str, color: str = None):
        self.value_lbl.setText(value)
        if color:
            self.value_lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")

# ═══════════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = AppSettings.load()
        self.apply_theme_mode()
        
        self.signals = WorkerSignals()
        self.signals.log.connect(self.log)
        self.signals.stats_updated.connect(self.update_stats)
        self.signals.ad_detected.connect(self.on_ad_detected)
        
        self.setWindowTitle(Config.APP_NAME)
        self.resize(950, 650)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setup_ui()
        self.setup_workers()
        self.setup_tray()
        
        if self.settings.start_minimized:
            QTimer.singleShot(0, self.hide)
        
        self.log("INFO", f"{Config.APP_NAME} v{Config.VERSION} 시작됨")

    def apply_theme_mode(self):
        mode = self.settings.theme_mode
        if mode == "system":
            Theme.set_mode("dark" if (DARK_DETECT_AVAILABLE and darkdetect.isDark()) else "light")
        else:
            Theme.set_mode(mode)

    def update_ui_theme(self):
        self.setStyleSheet(Theme.get_style())
        self.main_container.setStyleSheet(f"QFrame {{ background-color: {Theme.color('bg')}; border: 1px solid {Theme.color('border')}; border-radius: 10px; }}")
        self.sidebar.setStyleSheet(f"background-color: {Theme.color('surface')}; border-right: 1px solid {Theme.color('border')}; border-bottom-left-radius: 10px;")
        self.title_bar.lbl.setStyleSheet(f"font-weight: bold; color: {Theme.color('text_sub')}; font-size: 12px;")
        self.log_view.setStyleSheet(f"background-color: {Theme.color('surface')}; border-radius: 8px; font-family: Consolas;")
        
        for btn in self.nav_group.buttons():
            btn.update()

    def setup_ui(self):
        self.setStyleSheet(Theme.get_style())
        self.main_container = QFrame(self)
        self.setCentralWidget(self.main_container)
        master = QVBoxLayout(self.main_container)
        master.setContentsMargins(0, 0, 0, 0)
        master.setSpacing(0)
        
        self.title_bar = CustomTitleBar(self)
        self.title_bar.btn_min.clicked.connect(self.showMinimized)
        self.title_bar.btn_close.clicked.connect(self.close)
        master.addWidget(self.title_bar)
        
        body = QHBoxLayout()
        body.setSpacing(0)
        
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(0, 20, 0, 20)
        sb_layout.setSpacing(5)
        
        self.stack = QStackedWidget()
        self.nav_group = QButtonGroup(self)
        
        nav_items = [
            ("대시보드", "📊", self.create_dashboard),
            ("설정", "⚙️", self.create_settings),
            ("로그", "📝", self.create_logs),
            ("디버그", "🔍", self.create_debug),
            ("정보", "ℹ️", self.create_info)
        ]
        
        for idx, (lbl, icon, factory) in enumerate(nav_items):
            btn = NavButton(lbl, icon)
            sb_layout.addWidget(btn)
            self.nav_group.addButton(btn, idx)
            btn.clicked.connect(lambda _, i=idx: self.stack.setCurrentIndex(i))
            self.stack.addWidget(factory())
            if idx == 0:
                btn.setChecked(True)
        
        sb_layout.addStretch()
        ver_lbl = QLabel(f"v{Config.VERSION}")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_lbl.setStyleSheet("color: #555;")
        sb_layout.addWidget(ver_lbl)
        
        body.addWidget(self.sidebar)
        
        content_frame = QFrame()
        content_frame.setStyleSheet("background: transparent; border: none;")
        cf_layout = QVBoxLayout(content_frame)
        cf_layout.setContentsMargins(0, 0, 0, 0)
        cf_layout.addWidget(self.stack)
        body.addWidget(content_frame)
        master.addLayout(body)
        
        self.update_ui_theme()

    def create_dashboard(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Hero section
        hero = QFrame()
        hero.setFixedHeight(110)
        hero.setStyleSheet(f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Theme.PRIMARY}, stop:1 #FFC107); border-radius: 12px; }}")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(25, 0, 25, 0)
        
        h_txt = QLabel("🛡️ 카카오톡 보호가\n   활성화되었습니다")
        h_txt.setStyleSheet("color: black; font-size: 18px; font-weight: bold; background: transparent;")
        
        btns = QVBoxLayout()
        btns.setSpacing(8)
        
        h_btn = QPushButton("⚡ 지금 최적화")
        h_btn.setFixedSize(130, 36)
        h_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        h_btn.setStyleSheet("QPushButton { background-color: black; color: white; border-radius: 18px; font-weight: bold; } QPushButton:hover { background-color: #333; }")
        h_btn.clicked.connect(self.optimize)
        
        r_btn = QPushButton("↩️ 복원")
        r_btn.setFixedSize(130, 28)
        r_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        r_btn.setStyleSheet("QPushButton { background-color: rgba(0,0,0,0.2); color: white; border-radius: 14px; } QPushButton:hover { background-color: rgba(0,0,0,0.4); }")
        r_btn.clicked.connect(self.restore)
        
        btns.addWidget(h_btn)
        btns.addWidget(r_btn)
        hl.addWidget(h_txt)
        hl.addStretch()
        hl.addLayout(btns)
        layout.addWidget(hero)
        
        # Stats section
        stats_label = QLabel("📈 실시간 통계")
        stats_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(stats_label)
        
        stats_row = QHBoxLayout()
        stats_row.setSpacing(15)
        
        self.stat_kakao = StatCard("카카오톡", "💬", "대기중")
        self.stat_ads = StatCard("감지된 광고", "🚫", "0")
        self.stat_popups = StatCard("차단 팝업", "🔒", "0")
        self.stat_banners = StatCard("숨긴 배너", "📵", "0")
        
        stats_row.addWidget(self.stat_kakao)
        stats_row.addWidget(self.stat_ads)
        stats_row.addWidget(self.stat_popups)
        stats_row.addWidget(self.stat_banners)
        stats_row.addStretch()
        
        layout.addLayout(stats_row)
        
        # Engine status
        engine_label = QLabel("🔧 엔진 상태")
        engine_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(engine_label)
        
        engine_row = QHBoxLayout()
        self.lbl_sniffer_status = QLabel("● AdSniffer: 대기중")
        self.lbl_sniffer_status.setStyleSheet("color: #AAA;")
        self.lbl_adfit_status = QLabel("● AdFit 차단: 대기중")
        self.lbl_adfit_status.setStyleSheet("color: #AAA;")
        
        engine_row.addWidget(self.lbl_sniffer_status)
        engine_row.addWidget(self.lbl_adfit_status)
        engine_row.addStretch()
        layout.addLayout(engine_row)
        
        layout.addStretch()
        return page

    def create_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Startup group
        layout.addWidget(QLabel("시작 및 동작"))
        self._add_opt(layout, "Windows 시작 시 자동 실행", "auto_start", StartupManager.set)
        self._add_opt(layout, "실행 시 최소화 (트레이)", "start_minimized")
        
        layout.addSpacing(10)
        
        # Ad blocking group
        layout.addWidget(QLabel("광고 차단"))
        self._add_opt(layout, "광고 레이아웃 스니핑", "enable_sniffing", 
                     lambda s: self.sniffer_worker.start() if s else self.sniffer_worker.stop())
        self._add_opt(layout, "AdFit 팝업 차단", "block_adfit",
                     lambda s: self.adfit_worker.start() if s else self.adfit_worker.stop())
        self._add_opt(layout, "디버그 모드 (상세 로깅)", "debug_mode")
        
        layout.addSpacing(10)
        
        # Sniffing sensitivity
        layout.addWidget(QLabel("스니핑 감도"))
        sens_row = QFrame()
        sens_row.setStyleSheet(f"background-color: {Theme.color('surface')}; border-radius: 8px; padding: 5px;")
        sens_layout = QHBoxLayout(sens_row)
        sens_layout.addWidget(QLabel("감도 수준"))
        sens_layout.addStretch()
        
        sens_combo = QComboBox()
        sens_combo.addItems(["낮음 (Low)", "보통 (Medium)", "높음 (High)"])
        sens_map = {"low": 0, "medium": 1, "high": 2}
        sens_combo.setCurrentIndex(sens_map.get(self.settings.sniffing_sensitivity, 1))
        sens_combo.currentIndexChanged.connect(self.on_sensitivity_changed)
        sens_layout.addWidget(sens_combo)
        layout.addWidget(sens_row)
        
        layout.addSpacing(10)
        
        # Theme
        layout.addWidget(QLabel("테마 설정"))
        theme_row = QFrame()
        theme_row.setStyleSheet(f"background-color: {Theme.color('surface')}; border-radius: 8px; padding: 5px;")
        theme_layout = QHBoxLayout(theme_row)
        theme_layout.addWidget(QLabel("앱 테마"))
        theme_layout.addStretch()
        
        theme_combo = QComboBox()
        theme_combo.addItems(["시스템 기본", "다크 모드", "라이트 모드"])
        theme_map = {"system": 0, "dark": 1, "light": 2}
        theme_combo.setCurrentIndex(theme_map.get(self.settings.theme_mode, 0))
        theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addWidget(theme_combo)
        layout.addWidget(theme_row)
        
        layout.addStretch()
        return page

    def on_sensitivity_changed(self, idx):
        sens_values = ["low", "medium", "high"]
        self.settings.sniffing_sensitivity = sens_values[idx]
        self.settings.save()
        self.show_toast("감도 설정이 저장되었습니다")

    def on_theme_changed(self, idx):
        modes = ["system", "dark", "light"]
        self.settings.theme_mode = modes[idx]
        self.settings.save()
        self.apply_theme_mode()
        self.update_ui_theme()
        self.show_toast("테마가 변경되었습니다")

    def _add_opt(self, layout, text, key, cb=None):
        row = QFrame()
        row.setStyleSheet(f"background-color: {Theme.color('surface')}; border-radius: 8px; padding: 5px;")
        rl = QHBoxLayout(row)
        rl.addWidget(QLabel(text))
        rl.addStretch()
        
        sw = ModernToggle(getattr(self.settings, key))
        
        def _toggled(s):
            setattr(self.settings, key, s)
            self.settings.save()
            if cb:
                cb(s)
            self.show_toast("설정이 저장되었습니다")
        
        sw.toggled.connect(_toggled)
        rl.addWidget(sw)
        layout.addWidget(row)

    def create_logs(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Log controls
        ctrl = QHBoxLayout()
        clear_btn = QPushButton("🗑️ 로그 지우기")
        clear_btn.clicked.connect(lambda: self.log_view.clear())
        ctrl.addWidget(clear_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        
        return page

    def create_debug(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        layout.addWidget(QLabel("🔍 디버그 도구"))
        
        # Inspect button
        inspect_btn = QPushButton("📋 윈도우 계층 구조 분석")
        inspect_btn.setStyleSheet(f"background-color: {Theme.color('surface')}; padding: 10px; border-radius: 8px;")
        inspect_btn.clicked.connect(self.run_inspect)
        layout.addWidget(inspect_btn)
        
        # Debug output
        self.debug_output = QTextEdit()
        self.debug_output.setReadOnly(True)
        self.debug_output.setStyleSheet(f"background-color: {Theme.color('surface')}; font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.debug_output)
        
        return page

    def run_inspect(self):
        self.debug_output.clear()
        self.debug_output.append("윈도우 계층 분석 중...\n")
        
        if hasattr(self, 'sniffer_worker') and self.sniffer_worker.sniffer:
            result = self.sniffer_worker.inspect()
            self.debug_output.append(result)
        else:
            # Fallback: run inspector directly
            try:
                from ad_sniffer import AdLayoutSniffer
                sniffer = AdLayoutSniffer()
                result = sniffer.inspect()
                self.debug_output.append(result)
            except Exception as e:
                self.debug_output.append(f"오류: {e}")
        
        self.show_toast("분석 완료")

    def create_info(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(QLabel(f"🛡️ {Config.APP_NAME}"))
        layout.addWidget(QLabel(f"Version {Config.VERSION}"))
        layout.addSpacing(20)
        layout.addWidget(QLabel("Advanced Window Sniffing Edition"))
        layout.addWidget(QLabel("Multi-Strategy Ad Detection"))
        
        return page

    def setup_workers(self):
        self.sniffer_worker = AdSnifferWorker(self.signals)
        self.adfit_worker = AdFitWorker(self.signals)
        
        if self.settings.enable_sniffing:
            self.sniffer_worker.start()
            self.lbl_sniffer_status.setText("● AdSniffer: 실행중")
            self.lbl_sniffer_status.setStyleSheet(f"color: {Theme.SUCCESS};")
        
        if self.settings.block_adfit:
            self.adfit_worker.start()
            self.lbl_adfit_status.setText("● AdFit 차단: 실행중")
            self.lbl_adfit_status.setStyleSheet(f"color: {Theme.SUCCESS};")
        
        # Process monitor timer
        self.mon_timer = QTimer(self)
        self.mon_timer.timeout.connect(self.monitor)
        self.mon_timer.start(2000)

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        menu.addAction("열기", self.show_normal)
        menu.addAction("종료", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_normal() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def show_toast(self, text, icon="✅"):
        t = Toast(self.main_container, text, icon)
        t.show_message()

    def optimize(self):
        if not SystemManager.is_admin():
            self.show_toast("관리자 권한 필요", "⚠️")
            return
        
        hm = HostsManager()
        suc, msg = hm.block(Config.AD_DOMAINS)
        
        if suc:
            SystemManager.flush_dns()
            SystemManager.restart_process("KakaoTalk.exe")
            self.show_toast("최적화 완료!", "⚡")
            self.log("INFO", "최적화 완료")
        else:
            self.show_toast("실패", "❌")
            self.log("ERROR", msg)

    def restore(self):
        if not SystemManager.is_admin():
            self.show_toast("관리자 권한 필요", "⚠️")
            return
        
        res = QMessageBox.question(
            self, "복원 확인", 
            "Hosts 파일을 초기화하여 차단을 해제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if res == QMessageBox.StandardButton.Yes:
            hm = HostsManager()
            suc, msg = hm.restore()
            if suc:
                self.show_toast("복원 완료", "↩️")
                self.log("INFO", "Hosts 파일 복원됨")
            else:
                self.log("ERROR", msg)

    def monitor(self):
        run = SystemManager.process_exists("KakaoTalk.exe")
        if run:
            self.stat_kakao.set_value("실행 중", Theme.SUCCESS)
        else:
            self.stat_kakao.set_value("중지됨", Theme.ERROR)

    def update_stats(self, stats: dict):
        self.stat_ads.set_value(str(stats.get("ads_detected", 0)))
        self.stat_popups.set_value(str(stats.get("popups_blocked", 0)))
        self.stat_banners.set_value(str(stats.get("banners_hidden", 0)))

    def on_ad_detected(self, result):
        if self.settings.debug_mode:
            self.log("DEBUG", f"광고 감지: {result.ad_type.name} - {result.reason}")

    def log(self, lvl, msg):
        colors = {"INFO": "#569CD6", "WARN": "#DCDCAA", "ERROR": "#F44747", "DEBUG": "#9CDCFE"}
        c = colors.get(lvl, "#AAA")
        
        if lvl == "INFO":
            logger.info(msg)
        elif lvl == "WARN":
            logger.warning(msg)
        elif lvl == "ERROR":
            logger.error(msg)
        else:
            logger.debug(msg)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f'<span style="color:#555">[{timestamp}]</span> <span style="color:{c}">[{lvl}]</span> {msg}')

    def show_normal(self):
        self.show()
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.activateWindow()

    def quit_app(self):
        # Stop timers first
        if hasattr(self, 'mon_timer'):
            self.mon_timer.stop()
        
        # Stop workers
        self.sniffer_worker.stop()
        self.adfit_worker.stop()
        
        # Hide tray icon
        if hasattr(self, 'tray'):
            self.tray.hide()
        
        QApplication.quit()

    def closeEvent(self, e):
        if self.settings.minimize_to_tray:
            e.ignore()
            self.hide()
            self.tray.showMessage(Config.APP_NAME, "트레이로 최소화됨", 
                                 QSystemTrayIcon.MessageIcon.Information, 1000)
        else:
            self.quit_app()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    if "--minimized" not in sys.argv:
        window.show()
    sys.exit(app.exec())
