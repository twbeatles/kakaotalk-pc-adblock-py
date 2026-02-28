import logging

from kakao_adblocker import app
from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11


class FakeRoot:
    def __init__(self):
        self.mainloop_called = False

    def mainloop(self):
        self.mainloop_called = True


class FakeEngine:
    last_instance = None

    def __init__(self, *_args, **_kwargs):
        self.started = False
        self.stopped = False
        self.reported_warnings = []
        FakeEngine.last_instance = self

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def report_warning(self, message):
        self.reported_warnings.append(message)


class FakeController:
    last_instance = None

    def __init__(self, root, engine, settings, logger):
        self.root = root
        self.engine = engine
        self.settings = settings
        self.logger = logger
        self.notice_called = False
        self.hidden_called = False
        self.shown_called = False
        self.started = False
        self.stopped = False
        FakeController.last_instance = self

    def start(self):
        self.started = True

    def show_startup_notice(self):
        self.notice_called = True

    def hide_window(self):
        self.hidden_called = True

    def show_window(self):
        self.shown_called = True

    def stop_tray(self):
        self.stopped = True


def _patch_main_dependencies(monkeypatch, settings, load_warnings=None):
    monkeypatch.setattr(app.os, "name", "nt")
    monkeypatch.setattr(app, "ensure_runtime_files", lambda: None)
    monkeypatch.setattr(app.LayoutSettingsV11, "load", classmethod(lambda _cls: settings))
    monkeypatch.setattr(app.LayoutRulesV11, "load", classmethod(lambda _cls: LayoutRulesV11()))
    monkeypatch.setattr(app, "consume_load_warnings", lambda: list(load_warnings or []))
    monkeypatch.setattr(app, "setup_logging", lambda _level: logging.getLogger("test"))
    monkeypatch.setattr(app, "LayoutOnlyEngine", FakeEngine)
    monkeypatch.setattr(app.tk, "Tk", FakeRoot)
    monkeypatch.setattr(app, "TrayController", FakeController)


def test_main_skips_startup_notice_when_minimized(monkeypatch):
    settings = LayoutSettingsV11(start_minimized=True)
    _patch_main_dependencies(monkeypatch, settings)

    rc = app.main(["--minimized"])
    assert rc == 0
    controller = FakeController.last_instance
    assert controller is not None
    assert controller.notice_called is False
    assert controller.hidden_called is True


def test_main_shows_startup_notice_when_not_minimized(monkeypatch):
    settings = LayoutSettingsV11(start_minimized=False)
    _patch_main_dependencies(monkeypatch, settings)

    rc = app.main([])
    assert rc == 0
    controller = FakeController.last_instance
    assert controller is not None
    assert controller.notice_called is True
    assert controller.shown_called is True


def test_main_fail_fast_on_non_windows(monkeypatch, capsys):
    called = {"runtime": 0}
    monkeypatch.setattr(app.os, "name", "posix")
    monkeypatch.setattr(app, "ensure_runtime_files", lambda: called.__setitem__("runtime", called["runtime"] + 1))

    rc = app.main([])

    captured = capsys.readouterr()
    assert rc == 2
    assert "This application only supports Windows." in captured.err
    assert called["runtime"] == 0


def test_dump_tree_path_skips_ui_loading(monkeypatch):
    class DumpEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        def dump_window_tree(self, out_dir=None):
            return "C:\\temp\\dump.json"

    called = {"ui_load": 0}
    monkeypatch.setattr(app.os, "name", "nt")
    monkeypatch.setattr(app, "ensure_runtime_files", lambda: None)
    monkeypatch.setattr(app.LayoutSettingsV11, "load", classmethod(lambda _cls: LayoutSettingsV11()))
    monkeypatch.setattr(app.LayoutRulesV11, "load", classmethod(lambda _cls: LayoutRulesV11()))
    monkeypatch.setattr(app, "consume_load_warnings", lambda: [])
    monkeypatch.setattr(app, "setup_logging", lambda _level: logging.getLogger("test"))
    monkeypatch.setattr(app, "LayoutOnlyEngine", DumpEngine)
    monkeypatch.setattr(app, "_load_ui_dependencies", lambda: called.__setitem__("ui_load", called["ui_load"] + 1))

    rc = app.main(["--dump-tree"])

    assert rc == 0
    assert called["ui_load"] == 0


def test_main_reports_first_load_warning_to_engine(monkeypatch):
    settings = LayoutSettingsV11(start_minimized=True)
    _patch_main_dependencies(monkeypatch, settings, load_warnings=["설정 파일 손상", "추가 경고"])

    rc = app.main([])

    assert rc == 0
    engine = FakeEngine.last_instance
    assert engine is not None
    assert engine.reported_warnings == ["설정 파일 손상"]


def test_main_cleans_up_when_controller_start_fails(monkeypatch):
    class BrokenController(FakeController):
        def start(self):
            raise RuntimeError("start failed")

    settings = LayoutSettingsV11(start_minimized=True)
    _patch_main_dependencies(monkeypatch, settings)
    monkeypatch.setattr(app, "TrayController", BrokenController)

    try:
        app.main([])
    except RuntimeError as exc:
        assert str(exc) == "start failed"
    else:
        raise AssertionError("expected RuntimeError")

    engine = FakeEngine.last_instance
    controller = FakeController.last_instance
    assert engine is not None
    assert engine.stopped is True
    assert controller is not None
    assert controller.stopped is True


def test_main_cleans_up_when_mainloop_fails(monkeypatch):
    class BrokenRoot(FakeRoot):
        def mainloop(self):
            raise RuntimeError("mainloop failed")

    settings = LayoutSettingsV11(start_minimized=True)
    _patch_main_dependencies(monkeypatch, settings)
    monkeypatch.setattr(app.tk, "Tk", BrokenRoot)

    try:
        app.main([])
    except RuntimeError as exc:
        assert str(exc) == "mainloop failed"
    else:
        raise AssertionError("expected RuntimeError")

    engine = FakeEngine.last_instance
    controller = FakeController.last_instance
    assert engine is not None
    assert engine.stopped is True
    assert controller is not None
    assert controller.stopped is True


def test_self_check_path_skips_engine_and_ui(monkeypatch):
    called = {"runtime": 0, "engine": 0, "ui_load": 0}

    class NeverEngine:
        def __init__(self, *_args, **_kwargs):
            called["engine"] += 1

    monkeypatch.setattr(app.os, "name", "nt")
    monkeypatch.setattr(app, "ensure_runtime_files", lambda: called.__setitem__("runtime", called["runtime"] + 1))
    monkeypatch.setattr(app, "LayoutOnlyEngine", NeverEngine)
    monkeypatch.setattr(app, "_load_ui_dependencies", lambda: called.__setitem__("ui_load", called["ui_load"] + 1))
    monkeypatch.setattr(app, "_check_appdata_writable", lambda: (True, "ok"))
    monkeypatch.setattr(app.ProcessInspector, "probe_tasklist", staticmethod(lambda: (True, "ok")))
    monkeypatch.setattr(app.StartupManager, "probe_access", staticmethod(lambda: (True, "ok")))
    monkeypatch.setattr(app, "_check_tray_import", lambda: (True, "ok"))

    rc = app.main(["--self-check"])

    assert rc == 0
    assert called["runtime"] == 0
    assert called["engine"] == 0
    assert called["ui_load"] == 0
