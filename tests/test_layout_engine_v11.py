import logging

from kakao_adblocker.config import LayoutRulesV11
from kakao_adblocker.layout_engine import LayoutEngine
from kakao_adblocker.win32_api import SWP_NOMOVE


class DummyAPI:
    def __init__(self):
        self.calls = []
        self.rects = {}

    def update_window(self, hwnd):
        return True

    def set_window_pos(self, hwnd, x, y, width, height, flags):
        self.calls.append((hwnd, x, y, width, height, flags))
        self.rects[hwnd] = (x, y, x + width, y + height)
        return True

    def get_window_rect(self, hwnd):
        return self.rects.get(hwnd)


def test_resize_formula_online_main_view():
    api = DummyAPI()
    rules = LayoutRulesV11()
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    ok = engine.apply_view_resize(
        child_hwnd=101,
        window_text="OnlineMainView_0x10",
        parent_rect=(0, 0, 500, 700),
    )
    assert ok is True
    assert api.calls == [(101, 0, 0, 498, 669, SWP_NOMOVE)]


def test_resize_formula_lock_mode_view():
    api = DummyAPI()
    rules = LayoutRulesV11()
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    ok = engine.apply_view_resize(
        child_hwnd=201,
        window_text="LockModeView_0x20",
        parent_rect=(0, 0, 500, 700),
    )
    assert ok is True
    assert api.calls == [(201, 0, 0, 498, 700, SWP_NOMOVE)]


def test_resize_skipped_when_already_same_size():
    api = DummyAPI()
    api.rects[301] = (0, 0, 498, 669)
    rules = LayoutRulesV11()
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    ok = engine.apply_view_resize(
        child_hwnd=301,
        window_text="OnlineMainView_0x99",
        parent_rect=(0, 0, 500, 700),
    )
    assert ok is False
    assert api.calls == []


def test_aggressive_banner_heuristic():
    api = DummyAPI()
    rules = LayoutRulesV11()
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.should_hide_aggressive(
        class_name="Chrome_WidgetWin_1",
        window_text="AdFit NAS Advertisement",
        child_rect=(0, 620, 500, 700),
        parent_rect=(0, 0, 500, 700),
    )


def test_short_ascii_ad_token_uses_word_boundary():
    api = DummyAPI()
    rules = LayoutRulesV11(aggressive_ad_tokens=["Ad", "AdFit"])
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.contains_ad_token("ReadLater") is False
    assert engine.contains_ad_token("Header") is False
    assert engine.contains_ad_token("Ad") is True
    assert engine.contains_ad_token("AdFit NAS") is True
