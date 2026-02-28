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
