import logging
import threading
import time

from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11
from kakao_adblocker.event_engine import LayoutOnlyEngine
from kakao_adblocker.win32_api import SW_HIDE, SW_SHOW


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
        self.rect_calls = 0
        self.visible_calls = 0
        self.set_pos_calls = []
        self.hide_calls = []
        self.show_calls = []
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
        self.rect_calls += 1
        return self.windows[hwnd]["rect"]

    def is_window(self, hwnd):
        return hwnd in self.windows

    def is_window_visible(self, hwnd):
        self.visible_calls += 1
        return self.windows[hwnd]["visible"]

    def show_window(self, hwnd, _cmd):
        if _cmd == SW_HIDE:
            self.hide_calls.append(hwnd)
            self.windows[hwnd]["visible"] = False
        elif _cmd == SW_SHOW:
            self.show_calls.append(hwnd)
            self.windows[hwnd]["visible"] = True
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
    engine._text_cache[(9999, 42, "UnknownClass")] = (old, "x")
    engine._cleanup_caches()
    assert (9999, 42, "UnknownClass") not in engine._text_cache


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


def test_engine_restores_hidden_windows_when_disabled():
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
    engine.apply_once()
    assert api.windows[102]["visible"] is False
    assert api.windows[200]["visible"] is False

    engine.set_enabled(False)

    assert api.windows[102]["visible"] is True
    assert api.windows[200]["visible"] is True
    assert 102 in api.show_calls
    assert 200 in api.show_calls


def test_engine_restores_hidden_windows_on_stop():
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
    engine.apply_once()
    assert api.windows[102]["visible"] is False
    assert api.windows[200]["visible"] is False

    engine.stop()

    assert api.windows[102]["visible"] is True
    assert api.windows[200]["visible"] is True


def test_engine_cache_access_is_thread_safe_under_stress():
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
    errors = []

    def read_loop():
        try:
            for _ in range(800):
                engine._get_text(100)
                engine._get_class(100)
        except Exception as exc:  # pragma: no cover - should never happen
            errors.append(exc)

    def cleanup_loop():
        try:
            for _ in range(800):
                engine._cleanup_caches()
        except Exception as exc:  # pragma: no cover - should never happen
            errors.append(exc)

    threads = [
        threading.Thread(target=read_loop),
        threading.Thread(target=read_loop),
        threading.Thread(target=cleanup_loop),
        threading.Thread(target=cleanup_loop),
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=5.0)

    assert errors == []


def test_engine_candidate_detection_requires_class_and_legacy_signature():
    api = FakeAPI()
    api.windows[200]["class"] = "AdCandidateWin"
    api.windows[210] = {
        "pid": 42,
        "class": "AdCandidateWin",
        "text": "",
        "parent": 0,
        "rect": (20, 20, 320, 320),
        "visible": True,
    }
    api.children[210] = []
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=False)
    rules = LayoutRulesV11(ad_candidate_classes=["AdCandidateWin"])
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        rules,
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    engine.scan_once()
    engine.apply_once()

    assert 200 in api.hide_calls
    assert 210 not in api.hide_calls


def test_engine_hides_eva_window_dblclk_legacy_candidate_with_default_rules():
    api = FakeAPI()
    api.windows[220] = {
        "pid": 42,
        "class": "EVA_Window_Dblclk",
        "text": "",
        "parent": 0,
        "rect": (20, 620, 480, 700),
        "visible": True,
    }
    api.windows[221] = {
        "pid": 42,
        "class": "Chrome_WidgetWin_1",
        "text": "Chrome Legacy Window",
        "parent": 220,
        "rect": (20, 620, 480, 700),
        "visible": True,
    }
    api.children[220] = [221]
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=False)
    rules = LayoutRulesV11()
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        rules,
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    engine.scan_once()
    assert 220 in engine._ad_subwindow_candidates

    engine.apply_once()

    assert 220 in api.hide_calls


def test_engine_pid_scan_is_throttled():
    api = FakeAPI()
    calls = {"count": 0}

    def provider(_name):
        calls["count"] += 1
        return {42}

    settings = LayoutSettingsV11(
        enabled=True,
        poll_interval_ms=100,
        idle_poll_interval_ms=500,
        pid_scan_interval_ms=5000,
        cache_cleanup_interval_ms=1000,
        aggressive_mode=True,
    )
    engine = LayoutOnlyEngine(logging.getLogger("test"), settings, LayoutRulesV11(), api=api, process_ids_provider=provider)

    engine.scan_once()
    engine.scan_once()

    assert calls["count"] == 1


def test_engine_switches_between_idle_and_active_intervals():
    api = FakeAPI()
    settings = LayoutSettingsV11(
        enabled=True,
        poll_interval_ms=100,
        idle_poll_interval_ms=500,
        pid_scan_interval_ms=500,
        cache_cleanup_interval_ms=1000,
        aggressive_mode=True,
    )
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: set(),
    )

    now = time.time()
    with engine._data_lock:
        engine._kakao_pids = set()
        engine._last_activity = 0.0
    assert abs(engine._current_loop_interval_seconds(now) - 0.5) < 1e-9

    with engine._data_lock:
        engine._kakao_pids = {42}
    assert abs(engine._current_loop_interval_seconds(now) - 0.1) < 1e-9

    with engine._data_lock:
        engine._kakao_pids = set()
        engine._last_activity = now - 1.0
    assert abs(engine._current_loop_interval_seconds(now) - 0.1) < 1e-9

    with engine._data_lock:
        engine._last_activity = now - 4.0
    assert abs(engine._current_loop_interval_seconds(now) - 0.5) < 1e-9


def test_engine_cache_cleanup_is_throttled(monkeypatch):
    api = FakeAPI()
    settings = LayoutSettingsV11(
        enabled=True,
        poll_interval_ms=100,
        idle_poll_interval_ms=500,
        pid_scan_interval_ms=500,
        cache_cleanup_interval_ms=1000,
        aggressive_mode=True,
    )
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: {42},
    )
    called = {"count": 0}
    monkeypatch.setattr(engine, "_cleanup_caches", lambda: called.__setitem__("count", called["count"] + 1))

    engine._maybe_cleanup_caches(now=10.0)
    engine._maybe_cleanup_caches(now=10.4)
    engine._maybe_cleanup_caches(now=11.1)

    assert called["count"] == 2


def test_engine_watch_loop_runs_apply_in_same_cycle(monkeypatch):
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
    calls = []

    monkeypatch.setattr(engine, "_watch_once", lambda: calls.append("watch"))

    def _apply_once():
        calls.append("apply")
        engine._stop_event.set()

    monkeypatch.setattr(engine, "_apply_once", _apply_once)
    monkeypatch.setattr(engine, "_wait_next_tick", lambda _timeout: None)

    engine._stop_event.clear()
    engine._watch_loop()

    assert calls == ["watch", "apply"]


def test_engine_start_runs_warmup_before_background_thread(monkeypatch):
    api = FakeAPI()
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: {42},
    )
    calls = []
    monkeypatch.setattr("kakao_adblocker.event_engine.time.time", lambda: 10.0)

    monkeypatch.setattr(engine, "_watch_once", lambda: calls.append("warmup_watch"))
    monkeypatch.setattr(engine, "_apply_once", lambda: calls.append("warmup_apply"))

    class DummyThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            calls.append("thread_start")

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    monkeypatch.setattr("kakao_adblocker.event_engine.threading.Thread", DummyThread)

    engine.start()

    assert calls[:2] == ["warmup_watch", "warmup_apply"]
    assert "thread_start" in calls
    assert engine.state.running is True
    assert abs(engine._current_loop_interval_seconds(now=10.1) - 0.1) < 1e-9


def test_engine_default_idle_settings_meet_500ms_target():
    api = FakeAPI()
    settings = LayoutSettingsV11()
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: set(),
    )

    assert engine._idle_poll_interval_seconds() <= 0.5
    assert engine._pid_scan_interval_seconds() <= 0.5


def test_engine_scan_path_skips_rect_and_visibility_calls():
    api = FakeAPI()
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    engine.scan_once()

    assert api.rect_calls == 0
    assert api.visible_calls == 0


def test_engine_text_cache_uses_hwnd_pid_class_identity():
    api = FakeAPI()
    api.windows[400] = {
        "pid": 42,
        "class": "ClassA",
        "text": "OldText",
        "parent": 0,
        "rect": (0, 0, 100, 100),
        "visible": True,
    }
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    old_text = engine._get_text(400, 42, "ClassA")
    api.windows[400]["class"] = "ClassB"
    api.windows[400]["text"] = "NewText"
    new_text = engine._get_text(400, 42, "ClassB")

    assert old_text == "OldText"
    assert new_text == "NewText"
    cached_keys = [key for key in engine._text_cache.keys() if key[0] == 400]
    assert len(cached_keys) == 2


def test_engine_empty_text_cache_refreshes_quickly(monkeypatch):
    api = FakeAPI()
    api.windows[400] = {
        "pid": 42,
        "class": "ClassA",
        "text": "",
        "parent": 0,
        "rect": (0, 0, 100, 100),
        "visible": True,
    }
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(cache_ttl_seconds=8.0),
        api=api,
        process_ids_provider=lambda _name: {42},
    )
    now = {"value": 0.0}
    monkeypatch.setattr("kakao_adblocker.event_engine.time.time", lambda: now["value"])

    first = engine._get_text(400, 42, "ClassA")
    api.windows[400]["text"] = "NowReady"
    now["value"] = 0.11
    second = engine._get_text(400, 42, "ClassA")

    assert first == ""
    assert second == "NowReady"


def test_engine_skips_restore_for_recycled_hwnd():
    api = FakeAPI()
    settings = LayoutSettingsV11(enabled=True, poll_interval_ms=100, aggressive_mode=True)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings,
        LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: {42},
    )

    engine.scan_once()
    engine.apply_once()
    assert api.windows[200]["visible"] is False

    # Simulate HWND reuse by a different process/class.
    api.windows[200]["pid"] = 777
    api.windows[200]["class"] = "ReusedWindowClass"
    api.windows[200]["visible"] = False

    engine.set_enabled(False)

    assert 200 not in api.show_calls
    assert api.windows[200]["visible"] is False
