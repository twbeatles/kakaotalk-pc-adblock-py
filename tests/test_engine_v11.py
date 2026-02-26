import logging
import time

from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11
from kakao_adblocker.event_engine import LayoutOnlyEngine


class FakeAPI:
    def __init__(self):
        self.windows = {
            100: {"pid": 42, "class": "EVA_Window_Dblclk", "text": "카카오톡", "parent": 0, "rect": (0, 0, 500, 700), "visible": True},
            101: {"pid": 42, "class": "EVA_ChildWindow", "text": "OnlineMainView_0x1", "parent": 100, "rect": (0, 0, 500, 669), "visible": True},
            102: {"pid": 42, "class": "Chrome_WidgetWin_1", "text": "Advertisement", "parent": 100, "rect": (0, 620, 500, 700), "visible": True},
            200: {"pid": 42, "class": "EVA_Window", "text": "", "parent": 0, "rect": (10, 10, 410, 410), "visible": True},
            201: {"pid": 42, "class": "Chrome_WidgetWin_1", "text": "Chrome Legacy Window", "parent": 200, "rect": (10, 10, 410, 410), "visible": True},
            300: {"pid": 99, "class": "EVA_Window_Dblclk", "text": "카카오톡", "parent": 0, "rect": (0, 0, 600, 800), "visible": True},
            301: {"pid": 99, "class": "EVA_ChildWindow", "text": "OnlineMainView_0x2", "parent": 300, "rect": (0, 0, 600, 769), "visible": True},
        }
        self.children = {
            100: [101, 102],
            200: [201],
            300: [301],
        }
        self.set_pos_calls = []
        self.hide_calls = []
        self.send_calls = []

    def enum_windows(self, callback):
        for hwnd, info in sorted(self.windows.items()):
            if info["parent"] == 0:
                callback(hwnd)
        return True

    def enum_child_windows(self, parent_hwnd, callback):
        for child in self.children.get(parent_hwnd, []):
            callback(child)
        return True

    def get_window_thread_process_id(self, hwnd):
        return self.windows[hwnd]["pid"]

    def get_class_name(self, hwnd):
        return self.windows[hwnd]["class"]

    def get_window_text(self, hwnd):
        return self.windows[hwnd]["text"]

    def get_parent(self, hwnd):
        return self.windows[hwnd]["parent"]

    def get_window_rect(self, hwnd):
        return self.windows[hwnd]["rect"]

    def is_window(self, hwnd):
        return hwnd in self.windows

    def is_window_visible(self, hwnd):
        return self.windows[hwnd]["visible"]

    def show_window(self, hwnd, _cmd):
        self.hide_calls.append(hwnd)
        self.windows[hwnd]["visible"] = False
        return True

    def set_window_pos(self, hwnd, x, y, width, height, _flags):
        self.set_pos_calls.append((hwnd, x, y, width, height))
        return True

    def update_window(self, hwnd):
        return hwnd in self.windows

    def send_message(self, hwnd, msg, wparam=0, lparam=0):
        self.send_calls.append((hwnd, msg, wparam, lparam))
        return 1


def test_engine_applies_layout_only_to_kakao_pid():
    api = FakeAPI()
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    rules = LayoutRulesV11()
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        rules,
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    engine.scan_once()
    state = engine.state
    assert state.kakao_pid_count == 1
    assert state.main_window_count == 1

    engine.apply_once()
    resized_handles = [x[0] for x in api.set_pos_calls]
    assert 101 in resized_handles
    assert 301 not in resized_handles
    assert 102 in api.hide_calls
    assert 200 in api.hide_calls


def test_engine_invalid_handles_are_ignored():
    api = FakeAPI()
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    rules = LayoutRulesV11()
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        rules,
        api=api,
        process_ids_provider=lambda _name: {42},
    )
    engine.scan_once()
    engine._main_window_handles.add(9999)
    engine.apply_once()
    assert True


def test_engine_cache_cleanup_removes_stale():
    api = FakeAPI()
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    rules = LayoutRulesV11(cache_ttl_seconds=0.1)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        rules,
        api=api,
        process_ids_provider=lambda _name: {42},
    )
    old = time.time() - 5
    engine._text_cache[9999] = (old, "x")
    engine._class_cache[9999] = (old, "y")
    engine._cleanup_caches()
    assert 9999 not in engine._text_cache
    assert 9999 not in engine._class_cache


def test_engine_uses_rules_main_window_classes():
    api = FakeAPI()
    api.windows[100]["class"] = "CustomMainWindow"
    api.windows[100]["text"] = "Custom Main"
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    rules = LayoutRulesV11(main_window_classes=["CustomMainWindow"], main_window_titles=["Custom"])
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        rules,
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    engine.scan_once()
    assert engine.state.main_window_count == 1

    engine.apply_once()
    resized_handles = [x[0] for x in api.set_pos_calls]
    assert 101 in resized_handles
