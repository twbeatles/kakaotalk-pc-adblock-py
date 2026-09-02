from __future__ import annotations

import threading
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .models import LayoutRulesV11

_LOAD_WARNINGS: List[str] = []
_LOAD_WARNINGS_LOCK = threading.Lock()

# Store intentional mojibake signatures via escapes so code pages/editors do not rewrite them.
_MOJIBAKE_KAKAOTALK = "\u79fb\ub301\ubb45?\u317d\ub11a"
_MOJIBAKE_AD = "\u613f\ubb0e\ud02c"
_MOJIBAKE_SIGNATURES = (_MOJIBAKE_KAKAOTALK, _MOJIBAKE_AD)


def _push_load_warning(message: str) -> None:
    with _LOAD_WARNINGS_LOCK:
        _LOAD_WARNINGS.append(message)


def consume_load_warnings() -> List[str]:
    with _LOAD_WARNINGS_LOCK:
        out = list(_LOAD_WARNINGS)
        _LOAD_WARNINGS.clear()
        return out


def _is_mojibake_text(value: str) -> bool:
    if not value:
        return False
    if "\ufffd" in value:
        return True
    return any(signature in value for signature in _MOJIBAKE_SIGNATURES)


def _warn_if_rules_text_corrupted(rules: "LayoutRulesV11", source_label: str) -> None:
    corrupted = []
    if any(_is_mojibake_text(token) for token in rules.main_window_titles):
        corrupted.append("main_window_titles")
    if any(_is_mojibake_text(token) for token in rules.aggressive_ad_tokens):
        corrupted.append("aggressive_ad_tokens")
    if any(_is_mojibake_text(token) for token in rules.chrome_legacy_title_contains):
        corrupted.append("chrome_legacy_title_contains")
    if corrupted:
        _push_load_warning(
            f"{source_label} 문자열 무결성 경고: {', '.join(corrupted)}에 인코딩 이상 징후가 있습니다."
        )
