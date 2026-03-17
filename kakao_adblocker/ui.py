from __future__ import annotations

import importlib
import logging
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional, cast

from .config import APP_NAME, APPDATA_DIR, LayoutSettingsV11, SETTINGS_FILE
from .protocols import EngineLike, RootLike, StatusVarLike
from .services import ReleaseService, ShellService, StartupManager

pystray: Any = None
Image: Any = None
ImageDraw: Any = None
PYSTRAY_AVAILABLE = False
_LAST_TRAY_IMPORT_FAILURE_AT: Optional[float] = None
_TRAY_IMPORT_RETRY_TTL_SECONDS = 30.0
_TRAY_READY_TIMEOUT_SECONDS = 1.5
_TRAY_READY_TIMEOUT_MINIMIZED_SECONDS = 8.0
_STARTUP_TRAY_REFRESH_DELAY_MS = 3000


def _load_tray_modules() -> bool:
    global pystray, Image, ImageDraw, PYSTRAY_AVAILABLE, _LAST_TRAY_IMPORT_FAILURE_AT
    if PYSTRAY_AVAILABLE:
        return True
    now = time.time()
    if _LAST_TRAY_IMPORT_FAILURE_AT is not None:
        if (now - _LAST_TRAY_IMPORT_FAILURE_AT) < _TRAY_IMPORT_RETRY_TTL_SECONDS:
            return False
    try:
        pystray = importlib.import_module("pystray")
        Image = importlib.import_module("PIL.Image")
        ImageDraw = importlib.import_module("PIL.ImageDraw")
        PYSTRAY_AVAILABLE = True
        _LAST_TRAY_IMPORT_FAILURE_AT = None
        return True
    except Exception:
        _LAST_TRAY_IMPORT_FAILURE_AT = now
        return False


def _require_tray_modules() -> tuple[Any, Any, Any]:
    if not _load_tray_modules():
        raise RuntimeError("tray modules unavailable")
    if pystray is None or Image is None or ImageDraw is None:
        raise RuntimeError("tray modules unresolved")
    return pystray, Image, ImageDraw


class TrayController:
    def __init__(
        self,
        root: RootLike,
        engine: EngineLike,
        settings: LayoutSettingsV11,
        logger: logging.Logger,
    ) -> None:
        self.root = root
        self.engine = engine
        self.settings = settings
        self.logger = logger.getChild("TrayController")
        self.icon: Any = None
        self._tray_running = False
        self._tray_available = False
        self._tray_thread: Optional[threading.Thread] = None
        self._tray_ready_event = threading.Event()
        self._tray_start_error = ""
        self._tray_stopping = False
        self._startup_notice_shown = False
        self._last_status_text: Optional[str] = None
        self._ui_warning = ""
        self._ui_warning_at = 0.0
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._ui_queue_running = False
        self._ui_queue_batch_size = 32
        self._status_label: Any = None
        self._startup_tray_refresh_scheduled = False
        try:
            if isinstance(self.root, tk.Misc):
                self._status_var: StatusVarLike = tk.StringVar(master=self.root, value="상태: 초기화")
            else:
                self._status_var = _ValueHolder("상태: 초기화")
        except Exception:
            self._status_var = _ValueHolder("상태: 초기화")
        self._build_window()

    def _build_window(self) -> None:
        title = getattr(self.root, "title", None)
        if not callable(title):
            return
        title(APP_NAME)
        geometry = getattr(self.root, "geometry", None)
        if callable(geometry):
            geometry("460x260")
        resizable = getattr(self.root, "resizable", None)
        if callable(resizable):
            resizable(False, False)
        protocol = getattr(self.root, "protocol", None)
        if callable(protocol):
            protocol("WM_DELETE_WINDOW", self._on_close_requested)

        wrapper = ttk.Frame(cast(Any, self.root), padding=16)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper, text="KakaoTalk Layout AdBlocker v11", font=("Malgun Gothic", 12, "bold")).pack(anchor="w")
        if isinstance(self._status_var, tk.Variable):
            self._status_label = ttk.Label(wrapper, textvariable=self._status_var)
        else:
            self._status_label = ttk.Label(wrapper, text=self._status_var.get())
        self._status_label.pack(anchor="w", pady=(10, 8))

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

    def start(self, startup_minimized: bool = False) -> None:
        self._ui_queue_running = True
        self._schedule_ui_queue_drain()
        self._sync_startup_setting()
        self._tray_available = False
        self._tray_start_error = ""
        self._tray_stopping = False
        if _load_tray_modules():
            ready_timeout_seconds = _TRAY_READY_TIMEOUT_MINIMIZED_SECONDS if startup_minimized else _TRAY_READY_TIMEOUT_SECONDS
            self._setup_tray(ready_timeout_seconds=ready_timeout_seconds)
            if not self._tray_available:
                if self._tray_start_error:
                    self.logger.warning("tray mode disabled: %s", self._tray_start_error)
                    self._set_ui_warning(f"tray unavailable: {self._tray_start_error}")
                else:
                    self.logger.warning("tray mode disabled: tray startup timeout")
                    self._set_ui_warning("tray unavailable: startup timeout")
            else:
                self._clear_ui_warning(("tray unavailable:",))
        else:
            self.logger.warning("pystray is unavailable; tray mode disabled")
            self._set_ui_warning("tray unavailable: pystray import failed")
        self._configure_close_behavior()
        self._tick_status()

    def is_tray_available(self) -> bool:
        return bool(self._tray_available)

    def _schedule_ui_queue_drain(self) -> None:
        if not self._ui_queue_running:
            return
        try:
            if hasattr(self.root, "winfo_exists") and not bool(self.root.winfo_exists()):
                return
            if hasattr(self.root, "after"):
                self.root.after(50, self._drain_ui_queue)
        except Exception:
            self.logger.debug("UI queue drain scheduling skipped")

    def _drain_ui_queue(self) -> None:
        processed = 0
        while self._ui_queue_running and processed < self._ui_queue_batch_size:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                self.logger.exception("Queued UI callback failed")
            processed += 1
        self._schedule_ui_queue_drain()

    def _tick_status(self) -> None:
        self._update_status()
        try:
            if hasattr(self.root, "winfo_exists") and not bool(self.root.winfo_exists()):
                return
            if hasattr(self.root, "after"):
                self.root.after(1000, self._tick_status)
        except Exception:
            self.logger.debug("Status tick scheduling skipped")

    def _update_status(self, force: bool = False) -> None:
        text = self.status_text()
        if not force and text == self._last_status_text:
            return
        self._status_var.set(text)
        if self._status_label is not None and not isinstance(self._status_var, tk.Variable):
            try:
                self._status_label.configure(text=text)
            except Exception:
                pass
        self._last_status_text = text

    def _save_setting_attr(self, attr_name: str, new_value) -> bool:
        previous = getattr(self.settings, attr_name)
        setattr(self.settings, attr_name, new_value)
        try:
            self.settings.save(SETTINGS_FILE)
            return True
        except Exception:
            setattr(self.settings, attr_name, previous)
            self.logger.warning("Failed to save setting '%s'; rolled back", attr_name)
            self._update_status(force=True)
            return False

    def _set_ui_warning(self, message: str) -> None:
        self._ui_warning = message or ""
        self._ui_warning_at = time.time() if message else 0.0

    def _clear_ui_warning(self, prefixes: tuple[str, ...] | None = None) -> None:
        if not self._ui_warning:
            return
        if prefixes is not None and not any(self._ui_warning.startswith(prefix) for prefix in prefixes):
            return
        self._ui_warning = ""
        self._ui_warning_at = 0.0

    def _format_time(self, timestamp: float) -> str:
        if timestamp <= 0:
            return "-"
        return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

    def status_text(self) -> str:
        state = self.engine.state
        mode = "ON" if state.enabled else "OFF"
        tick_text = self._format_time(state.last_tick)
        candidate_main_count = int(getattr(state, "candidate_main_window_count", state.main_window_count) or 0)
        base = (
            f"상태: {mode} | PID {state.kakao_pid_count} | 메인윈도우 {state.main_window_count} | "
            f"누적 숨김 {state.hidden_windows} | 누적 리사이즈 {state.resized_windows}"
        )
        if candidate_main_count > state.main_window_count:
            base = f"{base} | 후보 {candidate_main_count}"
        restore_failures = int(getattr(state, "restore_failures", 0) or 0)
        if restore_failures > 0:
            restore_error = str(getattr(state, "last_restore_error", "") or "")
            compact_restore_error = restore_error if len(restore_error) <= 80 else f"{restore_error[:77]}..."
            base = f"{base} | 복원실패 {restore_failures}"
            if compact_restore_error:
                base = f"{base} {compact_restore_error}"
        if state.last_error:
            compact_error = state.last_error if len(state.last_error) <= 80 else f"{state.last_error[:77]}..."
            return f"{base} | 오류 {tick_text} {compact_error}"
        if self._ui_warning:
            warning_time = self._format_time(self._ui_warning_at)
            compact_warning = self._ui_warning if len(self._ui_warning) <= 80 else f"{self._ui_warning[:77]}..."
            return f"{base} | 경고 {warning_time} {compact_warning}"
        return f"{base} | 마지막 갱신 {tick_text}"

    def toggle_blocking(self) -> None:
        new_value = not self.settings.enabled
        if not self._save_setting_attr("enabled", new_value):
            return
        self.engine.set_enabled(new_value)
        self.logger.info("Blocking toggled: %s", "ON" if new_value else "OFF")
        self._update_status(force=True)

    def toggle_startup(self) -> None:
        current = StartupManager.is_enabled()
        target = not current
        if not StartupManager.set_enabled(target):
            self.logger.warning("Failed to update startup registration")
            self._set_ui_warning("startup registry update failed")
            self._update_status(force=True)
            return
        if not self._save_setting_attr("run_on_startup", target):
            rollback_ok = StartupManager.set_enabled(current)
            if rollback_ok:
                self.logger.warning("Failed to save startup setting; registry change rolled back")
                self._set_ui_warning("startup setting save failed; registry rolled back")
            else:
                self.logger.error("Failed to save startup setting and registry rollback failed")
                self._set_ui_warning("startup rollback failed")
            self._update_status(force=True)
            return
        self._clear_ui_warning(("startup ",))
        self.logger.info("Startup registration toggled: %s", "ON" if target else "OFF")
        self._update_status(force=True)

    def toggle_aggressive_mode(self) -> None:
        target = not self.settings.aggressive_mode
        if not self._save_setting_attr("aggressive_mode", target):
            return
        apply_change = getattr(self.engine, "set_aggressive_mode", None)
        if callable(apply_change):
            apply_change(target)
        self.logger.info("Aggressive mode toggled: %s", "ON" if self.settings.aggressive_mode else "OFF")
        self._update_status(force=True)

    def reset_restore_failures(self) -> None:
        self.engine.reset_restore_failures()
        self.logger.info("Restore failure counters reset")
        self._update_status(force=True)

    def _report_ui_action_failure(self, action: str, warning: str) -> None:
        self.logger.warning("UI action failed: %s", action)
        self._set_ui_warning(warning)
        self._update_status(force=True)

    def open_log_folder(self) -> None:
        if ShellService.open_folder(APPDATA_DIR):
            return
        self._report_ui_action_failure("open_log_folder", "log folder open failed")

    def open_releases_page(self) -> None:
        if ReleaseService.open_releases_page():
            return
        self._report_ui_action_failure("open_releases_page", "release page open failed")

    def show_window(self) -> None:
        if hasattr(self.root, "deiconify"):
            self.root.deiconify()
        if hasattr(self.root, "lift"):
            self.root.lift()

    def hide_window(self) -> None:
        if hasattr(self.root, "withdraw"):
            self.root.withdraw()

    def _on_close_requested(self) -> None:
        if self.is_tray_available():
            self.hide_window()
            return
        self.shutdown()

    def _configure_close_behavior(self) -> None:
        protocol = getattr(self.root, "protocol", None)
        if not callable(protocol):
            return
        try:
            protocol("WM_DELETE_WINDOW", self._on_close_requested)
        except Exception:
            self.logger.debug("Close behavior update skipped")

    def schedule_startup_tray_refresh(self, delay_ms: int = _STARTUP_TRAY_REFRESH_DELAY_MS) -> None:
        if self._startup_tray_refresh_scheduled or not self.is_tray_available():
            return
        if not hasattr(self.root, "after"):
            return
        self._startup_tray_refresh_scheduled = True
        try:
            self.root.after(delay_ms, self._refresh_tray_after_startup_launch)
        except Exception:
            self._startup_tray_refresh_scheduled = False
            self.logger.debug("Startup tray refresh scheduling skipped")

    def shutdown(self) -> None:
        self._ui_queue_running = False
        self.stop_tray()
        self.engine.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _setup_tray(self, ready_timeout_seconds: float = _TRAY_READY_TIMEOUT_SECONDS) -> None:
        try:
            pystray_mod, _image_mod, _draw_mod = _require_tray_modules()
        except RuntimeError:
            return
        self._tray_ready_event.clear()
        self._tray_start_error = ""
        self._tray_stopping = False
        self.icon = pystray_mod.Icon(
            "KakaoTalkLayoutAdBlocker",
            self._create_icon(),
            APP_NAME,
            pystray_mod.Menu(
                pystray_mod.MenuItem(lambda _item: self.status_text(), None, enabled=False),
                pystray_mod.MenuItem(lambda _item: "차단 끄기" if self.settings.enabled else "차단 켜기", self._menu_toggle_blocking),
                pystray_mod.MenuItem("공격 모드", self._menu_toggle_aggressive_mode, checked=lambda _item: self.settings.aggressive_mode),
                pystray_mod.MenuItem("시작프로그램 등록", self._menu_toggle_startup, checked=lambda _item: StartupManager.is_enabled()),
                pystray_mod.MenuItem("복원 실패 초기화", self._menu_reset_restore_failures),
                pystray_mod.MenuItem("창 열기", self._menu_show_window),
                pystray_mod.MenuItem("로그 폴더 열기", self._menu_open_logs),
                pystray_mod.MenuItem("GitHub 리포 열기", self._menu_open_release),
                pystray_mod.MenuItem("종료", self._menu_exit),
            ),
        )

        def _setup_callback(_icon) -> None:
            self._tray_running = True
            self._tray_available = True
            self._tray_ready_event.set()

        def _runner() -> None:
            try:
                self.icon.run(setup=_setup_callback)
            except Exception as exc:
                self._tray_start_error = f"{exc.__class__.__name__}: {exc}"
            finally:
                self._tray_running = False
                self._tray_available = False
                self._tray_ready_event.set()
                if not self._tray_stopping:
                    self._safe_after(self._on_tray_unexpected_exit)

        self._tray_thread = threading.Thread(target=_runner, daemon=True)
        self._tray_thread.start()
        ready = self._tray_ready_event.wait(ready_timeout_seconds)
        if not ready or not self._tray_running or self._tray_start_error:
            if not ready and not self._tray_start_error:
                self._tray_start_error = "startup timeout"
            self._tray_available = False
            self._tray_stopping = True
            try:
                self.icon.stop()
            except Exception:
                pass
            if self._tray_thread and self._tray_thread.is_alive():
                self._tray_thread.join(timeout=0.3)
            self._tray_running = False
            if not self._tray_thread or not self._tray_thread.is_alive():
                self._tray_stopping = False

    def stop_tray(self) -> None:
        self._tray_stopping = True
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        thread = self._tray_thread
        timed_out = False
        if thread and thread.is_alive():
            thread.join(timeout=0.5)
            timed_out = thread.is_alive()
        if timed_out:
            self.logger.debug("Tray thread did not terminate within timeout")
        else:
            self._tray_stopping = False
        self._tray_thread = None
        self._tray_running = False
        self._tray_available = False
        self._tray_ready_event.clear()

    def _create_icon(self):
        try:
            _pystray_mod, image_mod, image_draw_mod = _require_tray_modules()
        except RuntimeError:
            return None
        img = image_mod.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = image_draw_mod.Draw(img)
        draw.polygon(
            [(32, 4), (60, 14), (60, 32), (32, 60), (4, 32), (4, 14)],
            fill=(254, 229, 0, 255),
            outline=(200, 180, 0, 255),
        )
        draw.line([(18, 32), (26, 42), (46, 20)], fill=(25, 25, 25, 255), width=5)
        return img

    # Tray callbacks are called from tray thread.
    def _safe_after(self, callback) -> None:
        if not self._ui_queue_running:
            return
        try:
            if hasattr(self.root, "winfo_exists"):
                if not bool(self.root.winfo_exists()):
                    return
            self._ui_queue.put_nowait(callback)
        except Exception:
            self.logger.debug("Tray callback queueing skipped")

    def _is_window_visible(self) -> bool:
        if hasattr(self.root, "winfo_viewable"):
            try:
                return bool(self.root.winfo_viewable())
            except Exception:
                pass
        if hasattr(self.root, "state"):
            try:
                state = str(self.root.state()).lower()
                return state not in {"withdrawn", "iconic"}
            except Exception:
                pass
        return True

    def _on_tray_unexpected_exit(self) -> None:
        if self._tray_stopping:
            return
        self._tray_available = False
        self._set_ui_warning("tray unavailable: tray runtime stopped unexpectedly")
        self.logger.warning("Tray runtime stopped unexpectedly; forcing main window visible")
        if not self._is_window_visible():
            self.show_window()

    def _refresh_tray_after_startup_launch(self) -> None:
        self._startup_tray_refresh_scheduled = False
        if not self._ui_queue_running:
            return
        if not self.is_tray_available():
            return
        self.logger.info("Refreshing tray icon after startup launch")
        window_was_hidden = not self._is_window_visible()
        self.stop_tray()
        self._setup_tray(ready_timeout_seconds=_TRAY_READY_TIMEOUT_SECONDS)
        if self._tray_available:
            self._clear_ui_warning(("tray unavailable:",))
            return
        message = self._tray_start_error or "startup refresh failed"
        self._set_ui_warning(f"tray unavailable: {message}")
        if window_was_hidden:
            self.show_window()

    def _menu_toggle_blocking(self, _icon, _item) -> None:
        self._safe_after(self.toggle_blocking)

    def _menu_toggle_startup(self, _icon, _item) -> None:
        self._safe_after(self.toggle_startup)

    def _menu_toggle_aggressive_mode(self, _icon, _item) -> None:
        self._safe_after(self.toggle_aggressive_mode)

    def _menu_reset_restore_failures(self, _icon, _item) -> None:
        self._safe_after(self.reset_restore_failures)

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
            kwargs: dict[str, Any] = {}
            if isinstance(self.root, tk.Misc):
                kwargs["parent"] = self.root
            messagebox.showinfo(
                "KakaoTalk Layout AdBlocker",
                "카카오톡 광고 레이아웃 차단이 활성화되었습니다.",
                **kwargs,
            )
        except Exception:
            self.logger.debug("Startup notice popup skipped")

    def _sync_startup_setting(self) -> None:
        actual = StartupManager.is_enabled()
        if actual and not StartupManager.sync_registration_command():
            self.logger.warning("Failed to refresh startup registration command")
            self._set_ui_warning("startup command refresh failed")
        if self.settings.run_on_startup == actual:
            return
        if not self._save_setting_attr("run_on_startup", actual):
            return
        self.logger.info("Startup setting synchronized from registry: %s", "ON" if actual else "OFF")


class _ValueHolder:
    def __init__(self, value: str):
        self._value = value

    def set(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


__all__ = ["TrayController", "PYSTRAY_AVAILABLE"]
