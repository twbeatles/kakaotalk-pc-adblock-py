import logging
import time
import types
import threading
from dataclasses import dataclass
from typing import Callable

from kakao_adblocker.config import LayoutSettingsV11
from kakao_adblocker.ui import TrayController


class FakeRoot:
    def __init__(self):
        self._visible = True
        self._after_calls = []

    def after(self, ms: int, fn: Callable[[], None]):
        self._after_calls.append((ms, fn))
        self._last_after = fn

    def deiconify(self):
        self._visible = True
        self.deiconified = True

    def lift(self):
        self.lifted = True

    def withdraw(self):
        self._visible = False
        self.withdrawn = True

    def winfo_viewable(self):
        return self._visible

    def state(self):
        return "normal" if self._visible else "withdrawn"

    def winfo_exists(self):
        return True

    def quit(self):
        self.quitted = True

    def destroy(self):
        self.destroyed = True


@dataclass
class FakeState:
    enabled: bool = True
    kakao_pid_count: int = 1
    candidate_main_window_count: int = 1
    main_window_count: int = 1
    hidden_windows: int = 2
    closed_windows: int = 1
    resized_windows: int = 3
    last_error: str = ""
    last_tick: float = 0.0
    restore_failures: int = 0
    last_restore_error: str = ""


class FakeEngine:
    def __init__(self):
        self.enabled = True
        self.stop_called = False
        self.reset_called = 0
        self.aggressive_mode_calls = []
        self._state = FakeState()

    @property
    def state(self):
        self._state.enabled = self.enabled
        return self._state

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def stop(self):
        self.stop_called = True

    def reset_restore_failures(self):
        self.reset_called += 1
        self._state.restore_failures = 0
        self._state.last_restore_error = ""

    def set_aggressive_mode(self, enabled):
        self.aggressive_mode_calls.append(bool(enabled))


def test_tray_controller_toggle_and_status(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    saved = {"called": 0}
    monkeypatch.setattr(settings, "save", lambda _path=None: saved.__setitem__("called", saved["called"] + 1))

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    before = controller.status_text()
    assert "상태: ON" in before
    assert "누적 닫힘 1" in before
    assert "마지막 갱신" in before

    controller.toggle_blocking()
    after = controller.status_text()
    assert "상태: OFF" in after
    assert saved["called"] == 1


def test_tray_controller_release_menu(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    called = {"url": 0}
    monkeypatch.setattr("kakao_adblocker.ui.ReleaseService.open_releases_page", lambda: called.__setitem__("url", called["url"] + 1) or True)
    controller.open_releases_page()
    assert called["url"] == 1


def test_tray_controller_open_log_folder_sets_warning_on_failure(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    monkeypatch.setattr("kakao_adblocker.ui.ShellService.open_folder", lambda _path: False)
    controller.open_log_folder()

    assert "log folder open failed" in controller.status_text()


def test_tray_controller_open_release_page_sets_warning_on_failure(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    monkeypatch.setattr("kakao_adblocker.ui.ReleaseService.open_releases_page", lambda: False)
    controller.open_releases_page()

    assert "release page open failed" in controller.status_text()


def test_tray_controller_startup_notice_once(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    called = {"popup": 0}

    def fake_showinfo(*_args, **_kwargs):
        called["popup"] += 1
        return "ok"

    monkeypatch.setattr("kakao_adblocker.ui.messagebox.showinfo", fake_showinfo)
    controller.show_startup_notice()
    controller.show_startup_notice()
    assert called["popup"] == 1


def test_toggle_startup_does_not_persist_on_registry_failure(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=False)
    saved = {"called": 0}
    monkeypatch.setattr(settings, "save", lambda _path=None: saved.__setitem__("called", saved["called"] + 1))
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: False)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.set_enabled", lambda _enable: False)

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller.toggle_startup()

    assert settings.run_on_startup is False
    assert saved["called"] == 0
    assert "startup registry update failed" in controller.status_text()


def test_toggle_startup_persists_on_registry_success(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=False)
    saved = {"called": 0}
    monkeypatch.setattr(settings, "save", lambda _path=None: saved.__setitem__("called", saved["called"] + 1))
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: False)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.set_enabled", lambda _enable: True)

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller.toggle_startup()

    assert settings.run_on_startup is True
    assert saved["called"] == 1


def test_start_syncs_startup_setting_from_registry(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(TrayController, "_setup_tray", lambda self, **_kwargs: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=False)
    saved = {"called": 0}
    monkeypatch.setattr(settings, "save", lambda _path=None: saved.__setitem__("called", saved["called"] + 1))
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.probe_registration_command", lambda: (True, "Run 등록 명령 정상"))

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller.start()

    assert settings.run_on_startup is True
    assert saved["called"] == 1


def test_start_uses_extended_tray_timeout_for_minimized_launch(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda: True)

    captured: dict[str, float | None] = {"timeout": None}

    def fake_setup(self, ready_timeout_seconds=ui._TRAY_READY_TIMEOUT_SECONDS):
        captured["timeout"] = ready_timeout_seconds

    monkeypatch.setattr(TrayController, "_setup_tray", fake_setup)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: False)

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller.start(startup_minimized=True)

    assert captured["timeout"] == ui._TRAY_READY_TIMEOUT_MINIMIZED_SECONDS


def test_startup_sync_skips_save_when_already_synced(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(TrayController, "_setup_tray", lambda self, **_kwargs: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=True)
    saved = {"called": 0}
    monkeypatch.setattr(settings, "save", lambda _path=None: saved.__setitem__("called", saved["called"] + 1))
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.probe_registration_command", lambda: (True, "Run 등록 명령 정상"))

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller.start()

    assert saved["called"] == 0


def test_toggle_aggressive_mode_persists_setting(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, aggressive_mode=True)
    saved = {"called": 0}
    monkeypatch.setattr(settings, "save", lambda _path=None: saved.__setitem__("called", saved["called"] + 1))

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller.toggle_aggressive_mode()

    assert settings.aggressive_mode is False
    assert saved["called"] == 1
    assert engine.aggressive_mode_calls == [False]


def test_toggle_blocking_rolls_back_when_save_fails(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)

    def broken_save(_path=None):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "save", broken_save)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller.toggle_blocking()

    assert settings.enabled is True
    assert engine.enabled is True


def test_toggle_startup_rolls_back_when_save_fails(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=False)

    def broken_save(_path=None):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "save", broken_save)
    calls = []
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: False)
    monkeypatch.setattr(
        "kakao_adblocker.ui.StartupManager.set_enabled",
        lambda enable: calls.append(enable) or True,
    )
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller.toggle_startup()

    assert settings.run_on_startup is False
    assert calls == [True, False]
    assert "registry rolled back" in controller.status_text()


def test_toggle_aggressive_mode_rolls_back_when_save_fails(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, aggressive_mode=True)

    def broken_save(_path=None):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "save", broken_save)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller.toggle_aggressive_mode()

    assert settings.aggressive_mode is True
    assert engine.aggressive_mode_calls == []


def test_sync_startup_setting_rolls_back_when_save_fails(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=False)

    def broken_save(_path=None):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "save", broken_save)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.probe_registration_command", lambda: (True, "Run 등록 명령 정상"))
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller._sync_startup_setting()

    assert settings.run_on_startup is False


def test_schedule_startup_tray_refresh_registers_delayed_refresh(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._tray_available = True

    controller.schedule_startup_tray_refresh()

    assert controller._startup_tray_refresh_scheduled is True
    assert getattr(root, "_last_after", None) == controller._refresh_tray_after_startup_launch


def test_refresh_tray_after_startup_launch_restarts_icon(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._tray_available = True
    controller._ui_queue_running = True
    calls = []

    monkeypatch.setattr(controller, "stop_tray", lambda: calls.append("stop"))

    def fake_setup(*, ready_timeout_seconds):
        calls.append(("setup", ready_timeout_seconds))
        controller._tray_available = True
        controller._tray_start_error = ""

    monkeypatch.setattr(controller, "_setup_tray", fake_setup)

    controller._refresh_tray_after_startup_launch()

    assert calls[0] == "stop"
    assert calls[1][0] == "setup"


def test_sync_startup_setting_warns_when_command_refresh_fails(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.probe_registration_command", lambda: (False, "Run 등록 명령 불일치"))
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.sync_registration_command", lambda: False)

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._sync_startup_setting()

    assert "startup command refresh failed" in controller.status_text()


def test_sync_startup_setting_repairs_unhealthy_registration(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True, run_on_startup=True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.probe_registration_command", lambda: (False, "Run 등록 명령 불일치"))
    calls = {"sync": 0}
    monkeypatch.setattr(
        "kakao_adblocker.ui.StartupManager.sync_registration_command",
        lambda: calls.__setitem__("sync", calls["sync"] + 1) or True,
    )

    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._sync_startup_setting()

    assert calls["sync"] == 1
    assert "startup command refresh failed" not in controller.status_text()


def test_status_text_shows_compact_error_context(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    engine._state.last_tick = time.time()
    engine._state.last_error = "x" * 120
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    text = controller.status_text()

    assert "오류" in text
    assert "..." in text


def test_status_text_shows_restore_failure_context(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    engine._state.restore_failures = 2
    engine._state.last_restore_error = "restore failed due to set_window_pos"
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    text = controller.status_text()

    assert "복원실패 2" in text
    assert "restore failed" in text


def test_status_text_shows_candidate_main_window_count(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    engine._state.main_window_count = 1
    engine._state.candidate_main_window_count = 3
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    text = controller.status_text()

    assert "후보 3" in text


def test_status_text_uses_ui_warning_when_engine_error_absent(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._set_ui_warning("tray unavailable: startup timeout")

    text = controller.status_text()

    assert "경고" in text
    assert "tray unavailable" in text


def test_status_text_prefers_engine_error_over_ui_warning(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    engine._state.last_tick = time.time()
    engine._state.last_error = "engine error"
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._set_ui_warning("tray unavailable: startup timeout")

    text = controller.status_text()

    assert "오류" in text
    assert "engine error" in text
    assert "tray unavailable" not in text


def test_status_update_skips_redundant_set(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    calls = {"set": 0}

    class CounterVar:
        def set(self, value: str):
            calls["set"] += 1

        def get(self) -> str:
            return ""

    controller._status_var = CounterVar()
    controller._last_status_text = None

    controller._update_status()
    controller._update_status()

    assert calls["set"] == 1


def test_queue_bridge_processes_callbacks_in_order(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    calls = []
    controller._ui_queue_running = True
    controller._safe_after(lambda: calls.append("a"))
    controller._safe_after(lambda: calls.append("b"))
    controller._safe_after(lambda: calls.append("c"))
    controller._drain_ui_queue()

    assert calls == ["a", "b", "c"]


def test_menu_reset_restore_failures_calls_engine(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    engine._state.restore_failures = 4
    engine._state.last_restore_error = "err"
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._ui_queue_running = True

    controller._menu_reset_restore_failures(None, None)
    controller._drain_ui_queue()

    assert engine.reset_called == 1
    assert engine._state.restore_failures == 0
    assert engine._state.last_restore_error == ""


def test_safe_after_ignores_when_queue_not_running(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller._safe_after(lambda: (_ for _ in ()).throw(RuntimeError("should not run")))
    controller._drain_ui_queue()

    assert controller._ui_queue.empty()


def test_close_request_shuts_down_when_tray_unavailable(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._tray_available = False

    controller._on_close_requested()

    assert engine.stop_called is True
    assert root.quitted is True
    assert root.destroyed is True


def test_close_request_hides_window_when_tray_available(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._tray_available = True

    controller._on_close_requested()

    assert getattr(root, "withdrawn", False) is True
    assert engine.stop_called is False


def test_tick_status_swallow_after_error(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)

    class TickFailRoot(FakeRoot):
        def winfo_exists(self):
            return True

        def after(self, ms: int, fn: Callable[[], None]):
            raise RuntimeError("tk closed")

    root = TickFailRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller._tick_status()
    assert True


def test_load_tray_modules_retries_after_ttl(monkeypatch):
    import kakao_adblocker.ui as ui

    ui.pystray = None
    ui.Image = None
    ui.ImageDraw = None
    ui.PYSTRAY_AVAILABLE = False
    ui._LAST_TRAY_IMPORT_FAILURE_AT = None

    calls = {"count": 0}

    def failing_import(_name):
        calls["count"] += 1
        raise ImportError("missing")

    monkeypatch.setattr(ui.importlib, "import_module", failing_import)
    monkeypatch.setattr(ui.time, "time", lambda: 100.0)
    assert ui._load_tray_modules() is False
    first_calls = calls["count"]

    monkeypatch.setattr(ui.time, "time", lambda: 110.0)
    assert ui._load_tray_modules() is False
    assert calls["count"] == first_calls

    monkeypatch.setattr(ui.time, "time", lambda: 131.0)
    assert ui._load_tray_modules() is False
    assert calls["count"] > first_calls


def test_load_tray_modules_resets_failure_timestamp_on_success(monkeypatch):
    import types
    import kakao_adblocker.ui as ui

    ui.pystray = None
    ui.Image = None
    ui.ImageDraw = None
    ui.PYSTRAY_AVAILABLE = False
    ui._LAST_TRAY_IMPORT_FAILURE_AT = 10.0

    modules = {
        "pystray": types.SimpleNamespace(),
        "PIL.Image": types.SimpleNamespace(new=lambda *_args, **_kwargs: None),
        "PIL.ImageDraw": types.SimpleNamespace(Draw=lambda *_args, **_kwargs: None),
    }

    monkeypatch.setattr(ui.time, "time", lambda: 100.0)
    monkeypatch.setattr(ui.importlib, "import_module", lambda name: modules[name])

    assert ui._load_tray_modules() is True
    assert ui.PYSTRAY_AVAILABLE is True
    assert ui._LAST_TRAY_IMPORT_FAILURE_AT is None


def test_setup_tray_marks_available_when_ready(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda: True)

    class ReadyIcon:
        def __init__(self, *_args, **_kwargs):
            self._stop = threading.Event()

        def run(self, setup=None):
            if setup is not None:
                setup(self)
            self._stop.wait(1.0)

        def stop(self):
            self._stop.set()

    ui.pystray = types.SimpleNamespace(
        Icon=ReadyIcon,
        Menu=lambda *items: tuple(items),
        MenuItem=lambda *args, **kwargs: (args, kwargs),
    )

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    monkeypatch.setattr(controller, "_create_icon", lambda: object())

    controller._setup_tray()

    assert controller.is_tray_available() is True
    assert getattr(controller.icon, "visible", False) is True
    controller.stop_tray()


def test_setup_tray_marks_unavailable_on_ready_timeout(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda: True)

    class SlowIcon:
        def __init__(self, *_args, **_kwargs):
            self._stop = threading.Event()

        def run(self, setup=None):
            self._stop.wait(1.0)

        def stop(self):
            self._stop.set()

    ui.pystray = types.SimpleNamespace(
        Icon=SlowIcon,
        Menu=lambda *items: tuple(items),
        MenuItem=lambda *args, **kwargs: (args, kwargs),
    )

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    monkeypatch.setattr(controller, "_create_icon", lambda: object())
    monkeypatch.setattr(ui, "_TRAY_READY_TIMEOUT_SECONDS", 0.05)

    controller._setup_tray()

    assert controller.is_tray_available() is False
    controller.stop_tray()


def test_setup_tray_marks_unavailable_when_icon_show_fails(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda: True)

    class FailingVisibleIcon:
        def __init__(self, *_args, **_kwargs):
            self._stop = threading.Event()

        @property
        def visible(self):
            return False

        @visible.setter
        def visible(self, _value):
            raise RuntimeError("show failed")

        def run(self, setup=None):
            if setup is not None:
                setup(self)
            self._stop.wait(1.0)

        def stop(self):
            self._stop.set()

    ui.pystray = types.SimpleNamespace(
        Icon=FailingVisibleIcon,
        Menu=lambda *items: tuple(items),
        MenuItem=lambda *args, **kwargs: (args, kwargs),
    )

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    monkeypatch.setattr(controller, "_create_icon", lambda: object())

    controller._setup_tray()

    assert controller.is_tray_available() is False
    assert "RuntimeError: show failed" in controller._tray_start_error
    controller.stop_tray()


def test_tray_unexpected_exit_forces_window_visible(monkeypatch):
    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller.hide_window()
    controller._tray_available = True
    controller._tray_stopping = False

    controller._on_tray_unexpected_exit()

    assert controller.is_tray_available() is False
    assert getattr(root, "deiconified", False) is True
    assert "tray unavailable" in controller.status_text()
    assert controller._tray_recovery_attempts_remaining == 3
    assert root._after_calls[-1][1] == controller._retry_tray_start


def test_start_schedules_tray_recovery_when_startup_minimized_fails(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda force_retry=False: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: False)

    def failing_setup(self, ready_timeout_seconds=ui._TRAY_READY_TIMEOUT_SECONDS):
        self._tray_available = False
        self._tray_start_error = "startup timeout"

    monkeypatch.setattr(TrayController, "_setup_tray", failing_setup)

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller.start(startup_minimized=True)

    assert controller._startup_rehide_on_tray_recovery is True
    assert controller._tray_recovery_attempts_remaining == 3
    assert any(fn == controller._retry_tray_start for _ms, fn in root._after_calls)


def test_retry_tray_start_hides_window_after_startup_fallback_recovery(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda force_retry=False: True)
    monkeypatch.setattr("kakao_adblocker.ui.StartupManager.is_enabled", lambda: False)

    calls = {"setup": 0}

    def staged_setup(self, ready_timeout_seconds=ui._TRAY_READY_TIMEOUT_SECONDS):
        calls["setup"] += 1
        self._tray_available = calls["setup"] >= 2
        self._tray_start_error = "" if self._tray_available else "startup timeout"

    monkeypatch.setattr(TrayController, "_setup_tray", staged_setup)

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))

    controller.start(startup_minimized=True)
    controller._retry_tray_start()

    assert controller.is_tray_available() is True
    assert getattr(root, "withdrawn", False) is True
    assert controller._startup_rehide_on_tray_recovery is False


def test_retry_tray_start_keeps_window_visible_after_runtime_recovery(monkeypatch):
    import kakao_adblocker.ui as ui

    monkeypatch.setattr(TrayController, "_build_window", lambda self: None)
    monkeypatch.setattr(ui, "_load_tray_modules", lambda force_retry=False: True)

    root = FakeRoot()
    engine = FakeEngine()
    settings = LayoutSettingsV11(enabled=True)
    controller = TrayController(root, engine, settings, logging.getLogger("test"))
    controller._ui_queue_running = True
    controller._tray_available = True
    controller.hide_window()

    def successful_setup(self, ready_timeout_seconds=ui._TRAY_READY_TIMEOUT_SECONDS):
        self._tray_available = True
        self._tray_start_error = ""

    monkeypatch.setattr(TrayController, "_setup_tray", successful_setup)

    controller._on_tray_unexpected_exit()
    controller._retry_tray_start()

    assert controller.is_tray_available() is True
    assert root._visible is True
    assert controller._startup_rehide_on_tray_recovery is False
