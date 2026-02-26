from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from typing import Callable, Optional, Tuple

SW_HIDE = 0
SW_SHOW = 5
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
WM_CLOSE = 0x0010


class Win32API:
    def __init__(self) -> None:
        self.available = os.name == "nt"
        self._callback_refs = []
        if not self.available:
            return

        self.user32 = ctypes.windll.user32
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )

    def enum_windows(self, callback: Callable[[int], bool]) -> bool:
        if not self.available:
            return False

        def _cb(hwnd, _lparam):
            try:
                return bool(callback(int(hwnd)))
            except Exception:
                return True

        c_cb = self.WNDENUMPROC(_cb)
        self._callback_refs.append(c_cb)
        try:
            return bool(self.user32.EnumWindows(c_cb, 0))
        finally:
            self._callback_refs.remove(c_cb)

    def enum_child_windows(self, parent_hwnd: int, callback: Callable[[int], bool]) -> bool:
        if not self.available:
            return False

        def _cb(hwnd, _lparam):
            try:
                return bool(callback(int(hwnd)))
            except Exception:
                return True

        c_cb = self.WNDENUMPROC(_cb)
        self._callback_refs.append(c_cb)
        try:
            return bool(self.user32.EnumChildWindows(parent_hwnd, c_cb, 0))
        finally:
            self._callback_refs.remove(c_cb)

    def get_window_thread_process_id(self, hwnd: int) -> int:
        if not self.available:
            return 0
        pid = ctypes.wintypes.DWORD(0)
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def get_class_name(self, hwnd: int) -> str:
        if not self.available:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def get_window_text(self, hwnd: int) -> str:
        if not self.available:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        self.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value

    def get_parent(self, hwnd: int) -> int:
        if not self.available:
            return 0
        return int(self.user32.GetParent(hwnd) or 0)

    def get_window_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        if not self.available:
            return None
        rect = ctypes.wintypes.RECT()
        ok = self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if not ok:
            return None
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

    def get_client_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        if not self.available:
            return None
        rect = ctypes.wintypes.RECT()
        ok = self.user32.GetClientRect(hwnd, ctypes.byref(rect))
        if not ok:
            return None
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

    def is_window(self, hwnd: int) -> bool:
        if not self.available:
            return False
        return bool(self.user32.IsWindow(hwnd))

    def is_window_visible(self, hwnd: int) -> bool:
        if not self.available:
            return False
        return bool(self.user32.IsWindowVisible(hwnd))

    def show_window(self, hwnd: int, cmd: int) -> bool:
        if not self.available:
            return False
        return bool(self.user32.ShowWindow(hwnd, cmd))

    def set_window_pos(
        self,
        hwnd: int,
        x: int,
        y: int,
        width: int,
        height: int,
        flags: int,
        insert_after: int = 0,
    ) -> bool:
        if not self.available:
            return False
        return bool(self.user32.SetWindowPos(hwnd, insert_after, x, y, width, height, flags))

    def send_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> int:
        if not self.available:
            return 0
        return int(self.user32.SendMessageW(hwnd, msg, wparam, lparam))

    def update_window(self, hwnd: int) -> bool:
        if not self.available:
            return False
        return bool(self.user32.UpdateWindow(hwnd))


__all__ = [
    "Win32API",
    "SW_HIDE",
    "SW_SHOW",
    "SWP_NOSIZE",
    "SWP_NOMOVE",
    "SWP_NOZORDER",
    "SWP_NOACTIVATE",
    "WM_CLOSE",
]
