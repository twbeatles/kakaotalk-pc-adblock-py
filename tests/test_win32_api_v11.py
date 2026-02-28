import ctypes

from kakao_adblocker.win32_api import Win32API


class _FakeFunc:
    def __init__(self):
        self.argtypes = None
        self.restype = None


class _FakeUser32:
    def __init__(self):
        self.EnumWindows = _FakeFunc()
        self.EnumChildWindows = _FakeFunc()
        self.GetWindowThreadProcessId = _FakeFunc()
        self.GetClassNameW = _FakeFunc()
        self.GetWindowTextW = _FakeFunc()
        self.GetParent = _FakeFunc()
        self.GetWindowRect = _FakeFunc()
        self.GetClientRect = _FakeFunc()
        self.IsWindow = _FakeFunc()
        self.IsWindowVisible = _FakeFunc()
        self.ShowWindow = _FakeFunc()
        self.SetWindowPos = _FakeFunc()
        self.SendMessageW = _FakeFunc()
        self.UpdateWindow = _FakeFunc()


def test_bind_signatures_sets_argtypes_and_restypes():
    api = Win32API.__new__(Win32API)
    api.user32 = _FakeUser32()
    api.WNDENUMPROC = object()

    api._bind_signatures()

    assert api.user32.EnumWindows.argtypes == [api.WNDENUMPROC, ctypes.wintypes.LPARAM]
    assert api.user32.EnumChildWindows.argtypes == [ctypes.wintypes.HWND, api.WNDENUMPROC, ctypes.wintypes.LPARAM]
    assert api.user32.GetClassNameW.restype == ctypes.c_int
    assert api.user32.GetWindowTextW.restype == ctypes.c_int
    assert api.user32.SetWindowPos.restype == ctypes.wintypes.BOOL


def test_get_last_error_returns_zero_when_unavailable():
    api = Win32API.__new__(Win32API)
    api.available = False

    assert api.get_last_error() == 0


def test_get_last_error_reads_ctypes_when_available(monkeypatch):
    api = Win32API.__new__(Win32API)
    api.available = True
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 321)

    assert api.get_last_error() == 321
