from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11
from kakao_adblocker.event_engine import LayoutOnlyEngine
from kakao_adblocker.protocols import WindowTextResult
from kakao_adblocker.win32_api import SW_HIDE, SW_SHOW, WM_CLOSE

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "window_dumps"
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "golden"


@dataclass(frozen=True)
class FixtureCase:
    fixture: str
    aggressive_mode: bool
    rules_overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def settings(self) -> LayoutSettingsV11:
        return LayoutSettingsV11(enabled=True, aggressive_mode=self.aggressive_mode)

    @property
    def rules(self) -> LayoutRulesV11:
        return LayoutRulesV11(**self.rules_overrides)


# Keep these aligned with tests/test_window_dump_fixtures_v11.py.
FIXTURE_CASES: tuple[FixtureCase, ...] = (
    FixtureCase("normal_main_window.json", aggressive_mode=False),
    FixtureCase("legacy_ad_surface.json", aggressive_mode=False),
    FixtureCase("bottom_web_panel_no_token.json", aggressive_mode=True, rules_overrides={"hide_bottom_banner_without_token": False}),
    FixtureCase("empty_eva_child_no_ad_signal.json", aggressive_mode=False, rules_overrides={"close_empty_eva_child_requires_ad_signal": True}),
    FixtureCase("popup_adfit_webview.json", aggressive_mode=False, rules_overrides={"popup_ad_classes": ["AdFitWebView"]}),
    FixtureCase("popup_non_adfit_viewer.json", aggressive_mode=False, rules_overrides={"popup_ad_classes": ["AdFitWebView"]}),
    FixtureCase("launch_ad_flash_banner.json", aggressive_mode=True),
    FixtureCase("guarded_popup_adfit_viewer.json", aggressive_mode=False, rules_overrides={"popup_ad_classes": ["AdFitWebView"]}),
    FixtureCase("owned_popup_legacy_ad.json", aggressive_mode=True),
    FixtureCase("non_main_media_viewer.json", aggressive_mode=True),
)

_CASES_BY_NAME = {case.fixture: case for case in FIXTURE_CASES}


class FixtureAPI:
    def __init__(self, payload: dict[str, Any]):
        self.windows: dict[int, dict[str, Any]] = {}
        self.children: dict[int, list[int]] = {}
        self.set_pos_calls: list[tuple[int, int, int, int, int]] = []
        self.hide_calls: list[int] = []
        self.show_calls: list[int] = []
        self.send_calls: list[tuple[int, int, int, int]] = []
        for node in payload["windows"]:
            self._load_node(node, parent=0)

    def _load_node(self, node: dict[str, Any], parent: int) -> None:
        hwnd = int(node["hwnd"])
        rect = tuple(node["rect"]) if node.get("rect") is not None else None
        # "owner" models an owned top-level WS_POPUP window (e.g. the KakaoTalk
        # 26.5 banner ad host): it is still enumerated as top-level by
        # enum_windows (structural parent stays 0) and is NOT in the owner's
        # EnumChildWindows, but Win32 GetParent returns the owner handle.
        owner = int(node.get("owner", 0))
        self.windows[hwnd] = {
            "pid": int(node["pid"]),
            "class": str(node["class"]),
            "text": str(node["text"]),
            "parent": parent,
            "owner": owner,
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

    def get_window_text_result(self, hwnd) -> WindowTextResult:
        return WindowTextResult(self.get_window_text(hwnd), known=True)

    def get_parent(self, hwnd):
        # Win32 GetParent returns the owner for top-level owned (WS_POPUP)
        # windows, and the parent for child windows.
        info = self.windows[hwnd]
        return info["owner"] or info["parent"]

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


def load_dump_payload(fixture_name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))


def get_fixture_case(fixture_name: str) -> FixtureCase:
    try:
        return _CASES_BY_NAME[fixture_name]
    except KeyError as exc:
        raise KeyError(f"unknown fixture: {fixture_name}") from exc


def run_fixture(
    fixture_name: str,
    *,
    settings: LayoutSettingsV11 | None = None,
    rules: LayoutRulesV11 | None = None,
) -> tuple[dict[str, Any], FixtureAPI, LayoutOnlyEngine]:
    payload = load_dump_payload(fixture_name)
    case = _CASES_BY_NAME.get(fixture_name)
    api = FixtureAPI(payload)
    engine = LayoutOnlyEngine(
        logging.getLogger("test"),
        settings or (case.settings if case is not None else LayoutSettingsV11(enabled=True, aggressive_mode=True)),
        rules or (case.rules if case is not None else LayoutRulesV11()),
        api=api,
        process_ids_provider=lambda _name: set(payload["pids"]),
    )
    engine.scan_once()
    engine.apply_once()
    return payload, api, engine


def _sorted_unique(values: list[int]) -> list[int]:
    return sorted(set(values))


def build_golden_payload(fixture_name: str) -> dict[str, Any]:
    case = get_fixture_case(fixture_name)
    dump_payload = load_dump_payload(fixture_name)
    api = FixtureAPI(dump_payload)
    engine = LayoutOnlyEngine(
        logging.getLogger("golden"),
        case.settings,
        case.rules,
        api=api,
        process_ids_provider=lambda _name: set(dump_payload["pids"]),
    )
    pids = set(dump_payload["pids"])
    engine.scan_once()
    main_windows = engine._dump.inspect_main_windows_for_dump(pids)
    candidates = engine._dump.inspect_candidates_for_dump(pids, {}, 0.0)
    engine.apply_once()
    state = engine.state
    close_hwnds = [hwnd for hwnd, msg, _wparam, _lparam in api.send_calls if msg == WM_CLOSE]
    return {
        "fixture": fixture_name,
        "settings": {
            "enabled": True,
            "aggressive_mode": case.aggressive_mode,
        },
        "rules_overrides": dict(case.rules_overrides),
        "expected": {
            "main_windows": main_windows,
            "candidates": candidates,
            "actions": {
                "hide": _sorted_unique(api.hide_calls),
                "show": _sorted_unique(api.show_calls),
                "close": _sorted_unique(close_hwnds),
                "set_pos": [list(item) for item in api.set_pos_calls],
            },
            "state": {
                "main_window_count": state.main_window_count,
                "candidate_main_window_count": state.candidate_main_window_count,
                "hidden_windows": state.hidden_windows,
                "closed_windows": state.closed_windows,
                "resized_windows": state.resized_windows,
                "popup_close_requests": state.popup_close_requests,
                "popup_hide_fallbacks": state.popup_hide_fallbacks,
                "popup_zero_size_fallbacks": state.popup_zero_size_fallbacks,
            },
        },
    }


def dumps_golden(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def golden_path(fixture_name: str) -> Path:
    return GOLDEN_DIR / fixture_name
