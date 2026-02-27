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
