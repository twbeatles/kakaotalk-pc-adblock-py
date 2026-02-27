from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Optional

from .config import APP_NAME, APPDATA_DIR, LayoutSettingsV11, SETTINGS_FILE
from .event_engine import LayoutOnlyEngine
from .services import ReleaseService, ShellService, StartupManager

pystray = None
Image = None
ImageDraw = None
PYSTRAY_AVAILABLE = False
_TRAY_IMPORT_ATTEMPTED = False


def _load_tray_modules() -> bool:
    global pystray, Image, ImageDraw, PYSTRAY_AVAILABLE, _TRAY_IMPORT_ATTEMPTED
    if PYSTRAY_AVAILABLE:
        return True
    if _TRAY_IMPORT_ATTEMPTED:
        return False
    _TRAY_IMPORT_ATTEMPTED = True
    try:
        import pystray as _pystray
        from PIL import Image as _Image, ImageDraw as _ImageDraw

        pystray = _pystray
        Image = _Image
        ImageDraw = _ImageDraw
        PYSTRAY_AVAILABLE = True
        return True
    except Exception:
        return False


class TrayController:
    def __init__(
        self,
        root: tk.Tk,
        engine: LayoutOnlyEngine,
        settings: LayoutSettingsV11,
        logger: logging.Logger,
    ) -> None:
        self.root = root
        self.engine = engine
        self.settings = settings
        self.logger = logger.getChild("TrayController")
        self.icon = None
        self._tray_running = False
        self._startup_notice_shown = False
        self._last_status_text: Optional[str] = None
        try:
            self._status_var = tk.StringVar(master=self.root, value="상태: 초기화")
        except Exception:
            self._status_var = _ValueHolder("상태: 초기화")
        self._build_window()

    def _build_window(self) -> None:
        if not hasattr(self.root, "title"):
            return
        self.root.title(APP_NAME)
        self.root.geometry("460x260")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        wrapper = ttk.Frame(self.root, padding=16)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper, text="KakaoTalk Layout AdBlocker v11", font=("Malgun Gothic", 12, "bold")).pack(anchor="w")
        ttk.Label(wrapper, textvariable=self._status_var).pack(anchor="w", pady=(10, 8))

        btn_row = ttk.Frame(wrapper)
        btn_row.pack(fill="x", pady=6)
        ttk.Button(btn_row, text="차단 On/Off", command=self.toggle_blocking).pack(side="left")
        ttk.Button(btn_row, text="시작프로그램 토글", command=self.toggle_startup).pack(side="left", padx=(8, 0))
        ttk.Button(btn_row, text="공격 모드 토글", command=self.toggle_aggressive_mode).pack(side="left", padx=(8, 0))

        btn_row2 = ttk.Frame(wrapper)
        btn_row2.pack(fill="x", pady=6)
        ttk.Button(btn_row2, text="로그 폴더 열기", command=self.open_log_folder).pack(side="left")
        ttk.Button(btn_row2, text="GitHub 리포", command=self.open_releases_page).pack(side="left", padx=(8, 0))

        ttk.Button(wrapper, text="종료", command=self.shutdown).pack(anchor="e", pady=(14, 0))

    def start(self) -> None:
        self._sync_startup_setting()
        if _load_tray_modules():
            self._setup_tray()
        else:
            self.logger.warning("pystray is unavailable; tray mode disabled")
        self._tick_status()

    def _tick_status(self) -> None:
        self._update_status()
        if hasattr(self.root, "after"):
            self.root.after(1000, self._tick_status)

    def _update_status(self, force: bool = False) -> None:
        text = self.status_text()
        if not force and text == self._last_status_text:
            return
        self._status_var.set(text)
        self._last_status_text = text

    def status_text(self) -> str:
        state = self.engine.state
        mode = "ON" if state.enabled else "OFF"
        tick_text = "-"
        if state.last_tick > 0:
            tick_text = datetime.fromtimestamp(state.last_tick).strftime("%H:%M:%S")
        base = (
            f"상태: {mode} | PID {state.kakao_pid_count} | 메인윈도우 {state.main_window_count} | "
            f"숨김 {state.hidden_windows} | 리사이즈 {state.resized_windows}"
        )
        if state.last_error:
            compact_error = state.last_error if len(state.last_error) <= 80 else f"{state.last_error[:77]}..."
            return f"{base} | 오류 {tick_text} {compact_error}"
        return f"{base} | 마지막 갱신 {tick_text}"

    def toggle_blocking(self) -> None:
        new_value = not self.settings.enabled
        self.settings.enabled = new_value
        self.settings.save(SETTINGS_FILE)
        self.engine.set_enabled(new_value)
        self.logger.info("Blocking toggled: %s", "ON" if new_value else "OFF")
        self._update_status(force=True)

    def toggle_startup(self) -> None:
        current = StartupManager.is_enabled()
        target = not current
        if not StartupManager.set_enabled(target):
            self.logger.warning("Failed to update startup registration")
            return
        self.settings.run_on_startup = target
        self.settings.save(SETTINGS_FILE)
        self.logger.info("Startup registration toggled: %s", "ON" if target else "OFF")

    def toggle_aggressive_mode(self) -> None:
        self.settings.aggressive_mode = not self.settings.aggressive_mode
        self.settings.save(SETTINGS_FILE)
        self.logger.info("Aggressive mode toggled: %s", "ON" if self.settings.aggressive_mode else "OFF")
        self._update_status(force=True)

    def open_log_folder(self) -> None:
        ShellService.open_folder(APPDATA_DIR)

    def open_releases_page(self) -> None:
        ReleaseService.open_releases_page()

    def show_window(self) -> None:
        if hasattr(self.root, "deiconify"):
            self.root.deiconify()
        if hasattr(self.root, "lift"):
            self.root.lift()

    def hide_window(self) -> None:
        if hasattr(self.root, "withdraw"):
            self.root.withdraw()

    def shutdown(self) -> None:
        self.stop_tray()
        self.engine.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _setup_tray(self) -> None:
        if not _load_tray_modules():
            return
        self.icon = pystray.Icon(
            "KakaoTalkLayoutAdBlocker",
            self._create_icon(),
            APP_NAME,
            pystray.Menu(
                pystray.MenuItem(lambda _item: self.status_text(), None, enabled=False),
                pystray.MenuItem(lambda _item: "차단 끄기" if self.settings.enabled else "차단 켜기", self._menu_toggle_blocking),
                pystray.MenuItem("공격 모드", self._menu_toggle_aggressive_mode, checked=lambda _item: self.settings.aggressive_mode),
                pystray.MenuItem("시작프로그램 등록", self._menu_toggle_startup, checked=lambda _item: StartupManager.is_enabled()),
                pystray.MenuItem("창 열기", self._menu_show_window),
                pystray.MenuItem("로그 폴더 열기", self._menu_open_logs),
                pystray.MenuItem("GitHub 리포 열기", self._menu_open_release),
                pystray.MenuItem("종료", self._menu_exit),
            ),
        )
        self._tray_running = True
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop_tray(self) -> None:
        if self._tray_running and self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        self._tray_running = False

    def _create_icon(self):
        if not _load_tray_modules():
            return None
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.polygon(
            [(32, 4), (60, 14), (60, 32), (32, 60), (4, 32), (4, 14)],
            fill=(254, 229, 0, 255),
            outline=(200, 180, 0, 255),
        )
        draw.line([(18, 32), (26, 42), (46, 20)], fill=(25, 25, 25, 255), width=5)
        return img

    # Tray callbacks are called from tray thread.
    def _safe_after(self, callback) -> None:
        try:
            if hasattr(self.root, "winfo_exists"):
                if not bool(self.root.winfo_exists()):
                    return
            if hasattr(self.root, "after"):
                self.root.after(0, callback)
        except Exception:
            self.logger.debug("Tray callback scheduling skipped")

    def _menu_toggle_blocking(self, _icon, _item) -> None:
        self._safe_after(self.toggle_blocking)

    def _menu_toggle_startup(self, _icon, _item) -> None:
        self._safe_after(self.toggle_startup)

    def _menu_toggle_aggressive_mode(self, _icon, _item) -> None:
        self._safe_after(self.toggle_aggressive_mode)

    def _menu_show_window(self, _icon, _item) -> None:
        self._safe_after(self.show_window)

    def _menu_open_logs(self, _icon, _item) -> None:
        self._safe_after(self.open_log_folder)

    def _menu_open_release(self, _icon, _item) -> None:
        self._safe_after(self.open_releases_page)

    def _menu_exit(self, _icon, _item) -> None:
        self._safe_after(self.shutdown)

    def show_startup_notice(self) -> None:
        if self._startup_notice_shown:
            return
        self._startup_notice_shown = True
        try:
            messagebox.showinfo(
                "KakaoTalk Layout AdBlocker",
                "카카오톡 광고 레이아웃 차단이 활성화되었습니다.",
                parent=self.root if hasattr(self.root, "winfo_exists") else None,
            )
        except Exception:
            self.logger.debug("Startup notice popup skipped")

    def _sync_startup_setting(self) -> None:
        actual = StartupManager.is_enabled()
        if self.settings.run_on_startup == actual:
            return
        self.settings.run_on_startup = actual
        self.settings.save(SETTINGS_FILE)
        self.logger.info("Startup setting synchronized from registry: %s", "ON" if actual else "OFF")


class _ValueHolder:
    def __init__(self, value: str):
        self._value = value

    def set(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


__all__ = ["TrayController", "PYSTRAY_AVAILABLE"]
