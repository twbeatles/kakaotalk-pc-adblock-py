import logging

from kakao_adblocker.config import LayoutSettingsV11
from kakao_adblocker.ui import TrayController


class FakeRoot:
    def after(self, _ms, fn):
        self._last_after = fn

    def deiconify(self):
        self.deiconified = True

    def lift(self):
        self.lifted = True

    def withdraw(self):
        self.withdrawn = True

    def quit(self):
        self.quitted = True

    def destroy(self):
        self.destroyed = True


class FakeEngine:
    def __init__(self):
        self.enabled = True
        self.stop_called = False
        self._state = type(
            "S",
            (),
            {"enabled": True, "kakao_pid_count": 1, "main_window_count": 1, "hidden_windows": 2, "resized_windows": 3},
        )()

    @property
    def state(self):
        self._state.enabled = self.enabled
        return self._state

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def stop(self):
        self.stop_called = True


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
