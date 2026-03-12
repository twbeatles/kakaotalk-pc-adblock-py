from kakao_adblocker import services


def test_startup_manager_build_command_includes_startup_launch(monkeypatch):
    monkeypatch.setattr(services.sys, "frozen", True, raising=False)
    monkeypatch.setattr(services.sys, "executable", r"C:\Apps\KakaoTalkLayoutAdBlocker_v11.exe")

    command = services.StartupManager.build_command()

    assert command == r'"C:\Apps\KakaoTalkLayoutAdBlocker_v11.exe" --startup-launch --minimized'


def test_process_inspector_isolates_per_process_psutil_errors(monkeypatch):
    class BrokenProc:
        @property
        def info(self):
            raise RuntimeError("denied")

    class GoodProc:
        info = {"pid": 4242, "name": "kakaotalk.exe"}

    class FakePsutil:
        @staticmethod
        def process_iter(_attrs):
            return [BrokenProc(), GoodProc()]

    monkeypatch.setattr(services, "PSUTIL_AVAILABLE", True)
    monkeypatch.setattr(services, "psutil", FakePsutil)

    pids = services.ProcessInspector.get_process_ids("kakaotalk.exe")

    assert pids == {4242}
    assert services.ProcessInspector.consume_last_warning() == ""


def test_process_inspector_falls_back_to_tasklist_when_psutil_init_fails(monkeypatch):
    class BrokenPsutil:
        @staticmethod
        def process_iter(_attrs):
            raise RuntimeError("psutil unavailable")

    called = {"tasklist": 0}

    class Result:
        returncode = 0
        stdout = '"kakaotalk.exe","5000","Console","1","10,000 K"\n'

    def fake_run(*_args, **_kwargs):
        called["tasklist"] += 1
        return Result()

    monkeypatch.setattr(services, "PSUTIL_AVAILABLE", True)
    monkeypatch.setattr(services, "psutil", BrokenPsutil)
    monkeypatch.setattr(services.subprocess, "run", fake_run)

    pids = services.ProcessInspector.get_process_ids("kakaotalk.exe")

    assert pids == {5000}
    assert called["tasklist"] == 1
    warning = services.ProcessInspector.consume_last_warning()
    assert "psutil init failed" in warning
    assert "tasklist fallback" in warning


def test_process_inspector_consume_warning_clears_buffer(monkeypatch):
    class BrokenPsutil:
        @staticmethod
        def process_iter(_attrs):
            raise RuntimeError("psutil unavailable")

    class Result:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(services, "PSUTIL_AVAILABLE", True)
    monkeypatch.setattr(services, "psutil", BrokenPsutil)
    monkeypatch.setattr(services.subprocess, "run", lambda *_args, **_kwargs: Result())

    services.ProcessInspector.get_process_ids("kakaotalk.exe")

    first = services.ProcessInspector.consume_last_warning()
    second = services.ProcessInspector.consume_last_warning()
    assert first != ""
    assert second == ""


def test_process_inspector_probe_tasklist_success(monkeypatch):
    class Result:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(services.subprocess, "run", lambda *_args, **_kwargs: Result())

    ok, detail = services.ProcessInspector.probe_tasklist()

    assert ok is True
    assert "실행 가능" in detail


def test_process_inspector_probe_tasklist_failure(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise OSError("not found")

    monkeypatch.setattr(services.subprocess, "run", fake_run)

    ok, detail = services.ProcessInspector.probe_tasklist()

    assert ok is False
    assert "OSError" in detail


def test_startup_manager_probe_access_success(monkeypatch):
    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 0x20019
        KEY_SET_VALUE = 0x0002

        @staticmethod
        def OpenKey(*_args, **_kwargs):
            return "k"

        @staticmethod
        def CloseKey(_key):
            return None

    monkeypatch.setattr(services, "WINREG_AVAILABLE", True)
    monkeypatch.setattr(services, "winreg", FakeWinreg)

    ok, detail = services.StartupManager.probe_access()

    assert ok is True
    assert "읽기/쓰기 가능" in detail


def test_startup_manager_probe_access_failure_on_read(monkeypatch):
    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 0x20019
        KEY_SET_VALUE = 0x0002

        @staticmethod
        def OpenKey(*_args, **_kwargs):
            raise PermissionError("denied")

        @staticmethod
        def CloseKey(_key):
            return None

    monkeypatch.setattr(services, "WINREG_AVAILABLE", True)
    monkeypatch.setattr(services, "winreg", FakeWinreg)

    ok, detail = services.StartupManager.probe_access()

    assert ok is False
    assert "read failed" in detail


def test_startup_manager_probe_access_failure_on_write(monkeypatch):
    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 0x20019
        KEY_SET_VALUE = 0x0002

        @staticmethod
        def OpenKey(_root, _path, _reserved, access):
            if access == FakeWinreg.KEY_SET_VALUE:
                raise PermissionError("denied write")
            return "k"

        @staticmethod
        def CloseKey(_key):
            return None

    monkeypatch.setattr(services, "WINREG_AVAILABLE", True)
    monkeypatch.setattr(services, "winreg", FakeWinreg)

    ok, detail = services.StartupManager.probe_access()

    assert ok is False
    assert "write failed" in detail


def test_startup_manager_sync_registration_command_updates_stale_value(monkeypatch):
    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 0x20019
        KEY_SET_VALUE = 0x0002
        REG_SZ = 1
        written = []

        @staticmethod
        def OpenKey(*_args, **_kwargs):
            return "k"

        @staticmethod
        def QueryValueEx(_key, _name):
            return (r'"C:\Apps\KakaoTalkLayoutAdBlocker_v11.exe" --minimized', FakeWinreg.REG_SZ)

        @staticmethod
        def SetValueEx(_key, _name, _reserved, _regtype, value):
            FakeWinreg.written.append(value)

        @staticmethod
        def CloseKey(_key):
            return None

    monkeypatch.setattr(services, "WINREG_AVAILABLE", True)
    monkeypatch.setattr(services, "winreg", FakeWinreg)
    monkeypatch.setattr(
        services.StartupManager,
        "build_command",
        staticmethod(lambda: r'"C:\Apps\KakaoTalkLayoutAdBlocker_v11.exe" --startup-launch --minimized'),
    )

    ok = services.StartupManager.sync_registration_command()

    assert ok is True
    assert FakeWinreg.written == [r'"C:\Apps\KakaoTalkLayoutAdBlocker_v11.exe" --startup-launch --minimized']


def test_startup_manager_wait_for_shell_ready_requires_stable_shell(monkeypatch):
    class FakeFindWindow:
        def __init__(self):
            self.calls = 0
            self.argtypes = None
            self.restype = None

        def __call__(self, _class_name, _window_name):
            self.calls += 1
            return 0 if self.calls == 1 else 100

    fake_find_window = FakeFindWindow()
    fake_user32 = type("FakeUser32", (), {"FindWindowW": fake_find_window})()

    times = iter([0.0, 0.2, 0.6, 1.0])
    monkeypatch.setattr(services.os, "name", "nt")
    monkeypatch.setattr(services.ctypes, "WinDLL", lambda *_args, **_kwargs: fake_user32)
    monkeypatch.setattr(services.ProcessInspector, "get_process_ids", staticmethod(lambda _name: {1234}))
    monkeypatch.setattr(services.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(services.time, "sleep", lambda _seconds: None)

    ok = services.StartupManager.wait_for_shell_ready(timeout_seconds=2.0, poll_interval_seconds=0.1)

    assert ok is True
