import importlib.util
import importlib
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "카카오톡 광고제거 v10.0.py"
    spec = importlib.util.spec_from_file_location("kakao_adblock", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_is_process_running_normalizes_image_name_in_tasklist(monkeypatch):
    m = load_module()
    legacy = importlib.import_module(m.SystemManager.__module__)

    filters = []

    def fake_run(args, **kwargs):
        filters.append(args[2] if len(args) > 2 else "")

        class Result:
            stdout = "kakaotalk.exe,1234,Console,1,10,000 K"

        return Result()

    monkeypatch.setattr(legacy, "PSUTIL_AVAILABLE", False)
    monkeypatch.setattr(legacy.subprocess, "run", fake_run)

    m.SystemManager._proc_cache.clear()
    assert m.SystemManager.is_process_running("KakaoTalk") is True
    m.SystemManager._proc_cache.clear()
    assert m.SystemManager.is_process_running("kakaotalk.exe") is True

    assert len(filters) == 2
    assert filters[0] == filters[1] == "IMAGENAME eq kakaotalk.exe"
    assert ".exe.exe" not in filters[0]


def test_restart_process_normalizes_image_name_in_taskkill(monkeypatch):
    m = load_module()
    legacy = importlib.import_module(m.SystemManager.__module__)
    commands = []

    def fake_run(args, **kwargs):
        commands.append(args)

        class Result:
            stdout = ""

        return Result()

    monkeypatch.setattr(legacy, "PSUTIL_AVAILABLE", False)
    monkeypatch.setattr(legacy.subprocess, "run", fake_run)
    monkeypatch.setattr(legacy.time, "sleep", lambda _s: None)
    monkeypatch.setattr(legacy.os.path, "exists", lambda _p: False)

    m.SystemManager.restart_process("KakaoTalk")
    m.SystemManager.restart_process("kakaotalk.exe")

    taskkill_calls = [cmd for cmd in commands if cmd and cmd[0] == "taskkill"]
    assert len(taskkill_calls) == 2
    assert taskkill_calls[0] == ["taskkill", "/f", "/im", "kakaotalk.exe"]
    assert taskkill_calls[1] == ["taskkill", "/f", "/im", "kakaotalk.exe"]
    assert not any(".exe.exe" in " ".join(cmd) for cmd in taskkill_calls)
