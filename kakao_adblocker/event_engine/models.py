from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ..protocols import Rect, WindowIdentity
from .constants import ACTION_NONE, DECISION_NONE


@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    class_name: str
    text: str
    parent_hwnd: int
    rect: Optional[Rect]
    visible: bool


@dataclass
class EngineState:
    enabled: bool = True
    running: bool = False
    kakao_pid_count: int = 0
    candidate_main_window_count: int = 0
    main_window_count: int = 0
    resized_windows: int = 0
    hidden_windows: int = 0
    closed_windows: int = 0
    popup_close_requests: int = 0
    popup_hide_fallbacks: int = 0
    popup_zero_size_fallbacks: int = 0
    last_tick: float = 0.0
    last_error: str = ""
    restore_failures: int = 0
    last_restore_error: str = ""


@dataclass
class HiddenWindowSnapshot:
    was_visible: bool
    rect: Optional[Rect]
    pid: int
    class_name: str
    hide_reason: str


@dataclass(frozen=True)
class AdDecision:
    signals: Dict[str, object]
    decision: str = DECISION_NONE
    action: str = ACTION_NONE
    hide_reason: str = ""

    @property
    def matched(self) -> bool:
        return self.decision != DECISION_NONE and self.action != ACTION_NONE


@dataclass
class CandidateState:
    match_streak: int = 0
    miss_streak: int = 0
    last_decision: Optional[AdDecision] = None
    last_action_at: float = 0.0
    snapshot: Optional[HiddenWindowSnapshot] = None


__all__ = [
    "WindowInfo",
    "EngineState",
    "HiddenWindowSnapshot",
    "AdDecision",
    "CandidateState",
    "WindowIdentity",
]
