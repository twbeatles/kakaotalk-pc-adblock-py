from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class PatternType(Enum):
    TEXT_CONTAINS = "text_contains"


@dataclass
class AdPattern:
    pattern_type: PatternType
    value: str
    description: str = ""


class PatternMatcher:
    def __init__(self, patterns: List[AdPattern] | None = None) -> None:
        self.patterns = patterns or []

    def is_ad_window(self, window_text: str, _window_class: str = "") -> bool:
        text = (window_text or "").lower()
        for pattern in self.patterns:
            if pattern.pattern_type == PatternType.TEXT_CONTAINS and pattern.value.lower() in text:
                return True
        return False


__all__ = ["PatternType", "AdPattern", "PatternMatcher"]
