import logging

from kakao_adblocker.config import LayoutRulesV11
from kakao_adblocker.layout_engine import LayoutEngine
from kakao_adblocker.win32_api import SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOZORDER

RESIZE_FLAGS = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE


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
    assert api.calls == [(101, 0, 0, 498, 669, RESIZE_FLAGS)]


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
    assert api.calls == [(201, 0, 0, 498, 700, RESIZE_FLAGS)]


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


def test_resize_uses_parent_relative_size_for_live_2026_geometry():
    """Documents the resize formula against the real KakaoTalk 26.5 main window
    geometry (parent [1337,0,1920,1032], OnlineMainView top offset 38).

    The formula is width=parent_w-2, height=parent_h-31, applied with SWP_NOMOVE
    (top-left unchanged). Because the child top is 38 (not 0), the resulting
    height (1001) plus the offset reaches 1039, i.e. ~7px past the parent bottom
    (1032). This is a latent magic-number/chrome coupling (PROJECT_AUDIT.md 3.4):
    today it is harmless, but it is asserted here so a future change that alters
    the formula or the assumed chrome is caught.
    """
    api = DummyAPI()
    rules = LayoutRulesV11()
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    parent_rect = (1337, 0, 1920, 1032)  # width 583, height 1032
    ok = engine.apply_view_resize(
        child_hwnd=591132,
        window_text="OnlineMainView_0x00090512",
        parent_rect=parent_rect,
    )

    assert ok is True
    assert len(api.calls) == 1
    _hwnd, _x, _y, width, height, flags = api.calls[0]
    assert width == 581  # parent width 583 - layout_shadow_padding_px (2)
    assert height == 1001  # parent height 1032 - main_view_padding_px (31)
    assert flags == RESIZE_FLAGS


def test_aggressive_banner_heuristic():
    api = DummyAPI()
    rules = LayoutRulesV11()
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.should_hide_aggressive(
        class_name="Chrome_WidgetWin_1",
        has_ad_token=True,
        child_rect=(0, 620, 500, 700),
        parent_rect=(0, 0, 500, 700),
    )


def test_bottom_banner_without_token_is_not_hidden_by_default():
    api = DummyAPI()
    rules = LayoutRulesV11(hide_bottom_banner_without_token=False)
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.should_hide_aggressive(
        class_name="Chrome_WidgetWin_1",
        has_ad_token=False,
        child_rect=(0, 620, 500, 700),
        parent_rect=(0, 0, 500, 700),
    ) is False


def test_bottom_banner_without_token_can_be_hidden_when_rule_enabled():
    api = DummyAPI()
    rules = LayoutRulesV11(hide_bottom_banner_without_token=True)
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.should_hide_aggressive(
        class_name="Chrome_WidgetWin_1",
        has_ad_token=False,
        child_rect=(0, 620, 500, 700),
        parent_rect=(0, 0, 500, 700),
    ) is True


def test_short_ascii_ad_token_uses_word_boundary():
    api = DummyAPI()
    rules = LayoutRulesV11(aggressive_ad_tokens=["Ad", "AdFit"])
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.contains_ad_token("ReadLater") is False
    assert engine.contains_ad_token("Header") is False
    assert engine.contains_ad_token("Ad") is True
    assert engine.contains_ad_token("AdFit NAS") is True


def test_contains_ad_token_in_texts_checks_multiple_texts():
    api = DummyAPI()
    rules = LayoutRulesV11(aggressive_ad_tokens=["Ad", "광고"])
    engine = LayoutEngine(api, rules, logging.getLogger("test"))

    assert engine.contains_ad_token_in_texts(["header", "광고 배너"]) is True
    assert engine.contains_ad_token_in_texts(["header", "footer"]) is False
