from kakao_adblocker import services


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


def test_process_inspector_falls_back_to_tasklist_when_psutil_init_fails(monkeypatch):
    class BrokenPsutil:
        @staticmethod
        def process_iter(_attrs):
            raise RuntimeError("psutil unavailable")

    called = {"tasklist": 0}

    class Result:
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
    assert "읽기 가능" in detail


def test_startup_manager_probe_access_failure(monkeypatch):
    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 0x20019

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
    assert "PermissionError" in detail
