import ctypes
from ctypes import wintypes

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
        self.GetWindowTextLengthW = _FakeFunc()
        self.GetParent = _FakeFunc()
        self.GetWindowRect = _FakeFunc()
        self.GetClientRect = _FakeFunc()
        self.IsWindow = _FakeFunc()
        self.IsWindowVisible = _FakeFunc()
        self.ShowWindow = _FakeFunc()
        self.SetWindowPos = _FakeFunc()
        self.SendMessageW = _FakeFunc()
        self.SendMessageTimeoutW = _FakeFunc()
        self.UpdateWindow = _FakeFunc()


def test_bind_signatures_sets_argtypes_and_restypes():
    api = Win32API.__new__(Win32API)
    api.user32 = _FakeUser32()
    api.WNDENUMPROC = object()

    api._bind_signatures()

    assert api.user32.EnumWindows.argtypes == [api.WNDENUMPROC, wintypes.LPARAM]
    assert api.user32.EnumChildWindows.argtypes == [wintypes.HWND, api.WNDENUMPROC, wintypes.LPARAM]
    assert api.user32.GetClassNameW.restype == ctypes.c_int
    assert api.user32.GetWindowTextW.restype == ctypes.c_int
    assert api.user32.GetWindowTextLengthW.restype == ctypes.c_int
    assert api.user32.SetWindowPos.restype == wintypes.BOOL
    assert api.user32.SendMessageTimeoutW.restype == getattr(wintypes, "LRESULT", ctypes.c_long)


def test_get_last_error_returns_zero_when_unavailable():
    api = Win32API.__new__(Win32API)
    api.available = False

    assert api.get_last_error() == 0
    assert api.send_message_timeout(100, 0x10) == (False, 0)


def test_get_last_error_reads_ctypes_when_available(monkeypatch):
    api = Win32API.__new__(Win32API)
    api.available = True
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 321)

    assert api.get_last_error() == 321


class _CallableFakeFunc:
    def __init__(self, fn):
        self.fn = fn
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.fn(*args)


def test_get_window_text_uses_dynamic_length_buffer(monkeypatch):
    text = "x" * 900
    api = Win32API.__new__(Win32API)
    api.available = True

    def get_text(_hwnd, buf, buf_len):
        copied = min(len(text), buf_len - 1)
        for idx, char in enumerate(text[:copied]):
            buf[idx] = char
        buf[copied] = "\0"
        return copied

    api.user32 = type(
        "FakeUser32",
        (),
        {
            "GetWindowTextLengthW": _CallableFakeFunc(lambda _hwnd: len(text)),
            "GetWindowTextW": _CallableFakeFunc(get_text),
        },
    )()
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0)
    monkeypatch.setattr(ctypes, "set_last_error", lambda _value: None)

    result = api.get_window_text_result(100)

    assert result.known is True
    assert result.text == text
    assert api.get_window_text(100) == text


def test_get_window_text_result_reports_unknown_on_read_failure(monkeypatch):
    errors = iter([0, 123])
    api = Win32API.__new__(Win32API)
    api.available = True
    api.user32 = type(
        "FakeUser32",
        (),
        {
            "GetWindowTextLengthW": _CallableFakeFunc(lambda _hwnd: 10),
            "GetWindowTextW": _CallableFakeFunc(lambda *_args: 0),
        },
    )()
    monkeypatch.setattr(ctypes, "get_last_error", lambda: next(errors))
    monkeypatch.setattr(ctypes, "set_last_error", lambda _value: None)

    result = api.get_window_text_result(100)

    assert result.known is False
    assert result.error_code == 123
