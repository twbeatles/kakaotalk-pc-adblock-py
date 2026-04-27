import json
import logging
from pathlib import Path

from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11
from kakao_adblocker.event_engine import LayoutOnlyEngine
from kakao_adblocker.win32_api import SW_HIDE, SW_SHOW

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "window_dumps"


class FixtureAPI:
    def __init__(self, payload: dict):
        self.windows: dict[int, dict] = {}
        self.children: dict[int, list[int]] = {}
        self.set_pos_calls: list[tuple[int, int, int, int, int]] = []
        self.hide_calls: list[int] = []
        self.show_calls: list[int] = []
        self.send_calls: list[tuple[int, int, int, int]] = []
        for node in payload["windows"]:
            self._load_node(node, parent=0)

    def _load_node(self, node: dict, parent: int) -> None:
        hwnd = int(node["hwnd"])
        rect = tuple(node["rect"]) if node.get("rect") is not None else None
        self.windows[hwnd] = {
            "pid": int(node["pid"]),
            "class": str(node["class"]),
            "text": str(node["text"]),
            "parent": parent,
            "rect": rect,
            "visible": bool(node["visible"]),
        }
        children = [int(child["hwnd"]) for child in node.get("children", [])]
        self.children[hwnd] = children
        for child in node.get("children", []):
            self._load_node(child, parent=hwnd)

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

    def show_window(self, hwnd, cmd):
        if cmd == SW_HIDE:
            self.hide_calls.append(hwnd)
            self.windows[hwnd]["visible"] = False
        elif cmd == SW_SHOW:
            self.show_calls.append(hwnd)
            self.windows[hwnd]["visible"] = True
        return True

    def set_window_pos(self, hwnd, x, y, width, height, flags):
        self.set_pos_calls.append((hwnd, x, y, width, height))
        return True

    def update_window(self, hwnd):
        return hwnd in self.windows

    def send_message(self, hwnd, msg, wparam=0, lparam=0):
        self.send_calls.append((hwnd, msg, wparam, lparam))
        return 1

    def send_message_timeout(self, hwnd, msg, wparam=0, lparam=0, timeout_ms=500) -> tuple[bool, int]:
        self.send_calls.append((hwnd, msg, wparam, lparam))
        return True, 1

    def get_last_error(self):
        return 0


def _run_fixture(
    fixture_name: str,
    *,
    settings: LayoutSettingsV11 | None = None,
    rules: LayoutRulesV11 | None = None,
):
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    api = FixtureAPI(payload)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings or LayoutSettingsV11(enabled=True, aggressive_mode=True),
        rules or LayoutRulesV11(),
        api=api,
        process_ids_provider=lambda _name: set(payload["pids"]),
    )
    engine.scan_once()
    engine.apply_once()
    return payload, api, engine


def test_window_dump_fixture_normal_main_window():
    _payload, api, engine = _run_fixture(
        "normal_main_window.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
    )

    assert engine.state.main_window_count == 1
    assert engine.state.candidate_main_window_count == 1
    assert api.hide_calls == []


def test_window_dump_fixture_legacy_ad_surface_hides_top_level_candidate():
    _payload, api, engine = _run_fixture(
        "legacy_ad_surface.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
    )

    assert engine.state.main_window_count == 1
    assert 200 in api.hide_calls


def test_window_dump_fixture_bottom_web_panel_without_token_is_not_hidden():
    _payload, api, _engine = _run_fixture(
        "bottom_web_panel_no_token.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
        rules=LayoutRulesV11(hide_bottom_banner_without_token=False),
    )

    assert 102 not in api.hide_calls


def test_window_dump_fixture_empty_eva_child_without_ad_signal_is_not_closed():
    _payload, api, _engine = _run_fixture(
        "empty_eva_child_no_ad_signal.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(close_empty_eva_child_requires_ad_signal=True),
    )

    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    assert 104 not in closed_handles


def test_window_dump_fixture_popup_adfit_webview_is_closed_hidden_and_restored_when_disabled():
    _payload, api, engine = _run_fixture(
        "popup_adfit_webview.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(popup_ad_classes=["AdFitWebView"]),
    )

    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    assert 200 in closed_handles
    assert 201 in closed_handles
    assert 200 in api.hide_calls
    assert 201 in api.hide_calls
    assert (200, 0, 0, 0, 0) in api.set_pos_calls
    assert (201, 0, 0, 0, 0) in api.set_pos_calls
    assert any(identity[0] == 200 for identity in engine._hidden_windows)
    assert any(identity[0] == 201 for identity in engine._hidden_windows)

    engine.set_enabled(False)
    engine.stop()

    assert 200 in api.show_calls
    assert 201 in api.show_calls


def test_window_dump_fixture_popup_non_adfit_viewer_is_ignored_by_default():
    _payload, api, _engine = _run_fixture(
        "popup_non_adfit_viewer.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(popup_ad_classes=["AdFitWebView"]),
    )

    assert api.hide_calls == []
    assert api.send_calls == []


def test_window_dump_fixture_launch_ad_flash_banner_hides_immediately():
    _payload, api, _engine = _run_fixture(
        "launch_ad_flash_banner.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
    )

    assert 102 in api.hide_calls


def test_window_dump_fixture_guarded_popup_adfit_viewer_is_ignored():
    _payload, api, _engine = _run_fixture(
        "guarded_popup_adfit_viewer.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(popup_ad_classes=["AdFitWebView"]),
    )

    assert api.hide_calls == []
    assert api.send_calls == []


def test_window_dump_fixture_non_main_media_viewer_is_ignored():
    _payload, api, _engine = _run_fixture(
        "non_main_media_viewer.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
    )

    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    resized_handles = [hwnd for hwnd, _x, _y, _width, _height in api.set_pos_calls]

    assert 200 not in api.hide_calls
    assert 201 not in api.hide_calls
    assert 200 not in closed_handles
    assert 201 not in closed_handles
    assert 201 not in resized_handles
