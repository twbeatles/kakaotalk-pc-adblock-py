from __future__ import annotations

import logging
from typing import Optional, Tuple

from .config import LayoutRulesV11
from .win32_api import SWP_NOMOVE, Win32API

Rect = Tuple[int, int, int, int]


def _rect_width(rect: Rect) -> int:
    return rect[2] - rect[0]


def _rect_height(rect: Rect) -> int:
    return rect[3] - rect[1]


class LayoutEngine:
    def __init__(self, api: Win32API, rules: LayoutRulesV11, logger: logging.Logger):
        self.api = api
        self.rules = rules
        self.logger = logger

    def apply_view_resize(self, child_hwnd: int, window_text: str, parent_rect: Rect) -> bool:
        width = _rect_width(parent_rect) - self.rules.layout_shadow_padding_px
        height: Optional[int] = None
        if window_text.startswith(self.rules.main_view_prefix):
            height = _rect_height(parent_rect) - self.rules.main_view_padding_px
        elif window_text.startswith(self.rules.lock_view_prefix):
            height = _rect_height(parent_rect)
        if height is None or width < 1 or height < 1:
            return False
        self.api.update_window(child_hwnd)
        return bool(self.api.set_window_pos(child_hwnd, 0, 0, width, height, SWP_NOMOVE))

    def should_close_empty_eva_child(
        self,
        class_name: str,
        window_text: str,
        parent_text: str,
        has_custom_scroll: bool,
    ) -> bool:
        return (
            class_name == self.rules.eva_child_class
            and window_text == ""
            and parent_text != ""
            and not has_custom_scroll
        )

    def contains_ad_token(self, text: str) -> bool:
        low = (text or "").lower()
        return any(token in low for token in self.rules.aggressive_ad_tokens_lc)

    def is_chrome_widget_class(self, class_name: str) -> bool:
        return any(class_name.startswith(prefix) for prefix in self.rules.chrome_widget_prefixes)

    def is_aggressive_chrome_ad(self, class_name: str, window_text: str) -> bool:
        return self.is_chrome_widget_class(class_name) and self.contains_ad_token(window_text)

    def is_bottom_banner_candidate(self, class_name: str, window_text: str, child_rect: Rect, parent_rect: Rect) -> bool:
        height = _rect_height(child_rect)
        width = _rect_width(child_rect)
        parent_width = _rect_width(parent_rect)
        if height < self.rules.banner_min_height_px or height > self.rules.banner_max_height_px:
            return False
        if parent_width <= 0:
            return False
        if (width / parent_width) < self.rules.banner_min_width_ratio:
            return False
        if abs(child_rect[3] - parent_rect[3]) > self.rules.banner_bottom_margin_px:
            return False
        return self.is_chrome_widget_class(class_name) or self.contains_ad_token(window_text)

    def should_hide_aggressive(self, class_name: str, window_text: str, child_rect: Rect, parent_rect: Rect) -> bool:
        if self.is_aggressive_chrome_ad(class_name, window_text):
            return True
        return self.is_bottom_banner_candidate(class_name, window_text, child_rect, parent_rect)


__all__ = ["LayoutEngine"]
