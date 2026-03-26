from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Tuple

from .constants import (
    ACTION_CLOSE,
    ACTION_DISMISS_POPUP,
    ACTION_HIDE,
    DECISION_STRONG,
    DECISION_WEAK,
    HIDE_REASON_AGGRESSIVE,
    HIDE_REASON_LEGACY,
    POPUP_GUARD_ALLOW,
    POPUP_GUARD_BLOCKED,
    POPUP_GUARD_NA,
)
from .models import AdDecision, CandidateState

if TYPE_CHECKING:
    from .controller import LayoutOnlyEngine


class SignalEvaluator:
    def __init__(self, engine: "LayoutOnlyEngine") -> None:
        self.engine = engine

    def popup_host_text_matches(self, text: str) -> bool:
        normalized = (text or "").strip()
        if not normalized:
            return True
        text_lc = normalized.lower()
        if any(token and token.lower() in text_lc for token in self.engine.rules.popup_host_text_contains):
            return True
        return not self.engine.rules.popup_host_require_empty_text

    def popup_host_guard_status(self, text: str) -> str:
        return POPUP_GUARD_ALLOW if self.popup_host_text_matches(text) else POPUP_GUARD_BLOCKED

    def blank_signals(self) -> Dict[str, object]:
        return {
            "legacy_signature": "",
            "popup_direct_class": False,
            "chrome_widget_bottom_banner": False,
            "subtree_ad_token": False,
            "empty_eva_child": False,
            "popup_host_guard": POPUP_GUARD_NA,
        }

    def has_relevant_signal(self, decision: AdDecision) -> bool:
        signals = decision.signals
        return any(
            (
                bool(signals.get("legacy_signature")),
                bool(signals.get("popup_direct_class")),
                bool(signals.get("chrome_widget_bottom_banner")),
                bool(signals.get("subtree_ad_token")),
                bool(signals.get("empty_eva_child")),
                str(signals.get("popup_host_guard", POPUP_GUARD_NA)) != POPUP_GUARD_NA,
            )
        )

    def decision_none(self, signals: Optional[Dict[str, object]] = None) -> AdDecision:
        return AdDecision(signals=signals or self.blank_signals())

    def decision_hide(self, decision: str, hide_reason: str, signals: Dict[str, object]) -> AdDecision:
        return AdDecision(signals=signals, decision=decision, action=ACTION_HIDE, hide_reason=hide_reason)

    def decision_close(self, decision: str, signals: Dict[str, object]) -> AdDecision:
        return AdDecision(signals=signals, decision=decision, action=ACTION_CLOSE)

    def decision_dismiss_popup(self, signals: Dict[str, object]) -> AdDecision:
        return AdDecision(signals=signals, decision=DECISION_STRONG, action=ACTION_DISMISS_POPUP)

    def update_candidate_state_store(
        self,
        state_store: dict[tuple[int, int, str], CandidateState],
        identity: tuple[int, int, str],
        decision: AdDecision,
        now: float,
    ) -> tuple[CandidateState, bool]:
        state = state_store.get(identity)
        if state is None:
            state = CandidateState()
            state_store[identity] = state
        if decision.matched:
            state.match_streak += 1
            state.miss_streak = 0
        else:
            state.match_streak = 0
            state.miss_streak += 1
        state.last_decision = decision
        confirmed = decision.matched and (
            decision.decision == DECISION_STRONG
            or state.match_streak >= max(int(self.engine.rules.weak_signal_confirm_ticks), 1)
        )
        if confirmed:
            state.last_action_at = now
        return state, confirmed

    def candidate_payload(
        self,
        identity: tuple[int, int, str],
        decision: AdDecision,
        state: Optional[CandidateState],
        *,
        confirmed: bool,
    ) -> Dict[str, object]:
        action = decision.action
        if decision.matched and not confirmed:
            action = f"pending_{decision.action}"
        hwnd, pid, class_name = identity
        return {
            "hwnd": hwnd,
            "pid": pid,
            "class": class_name,
            "signals": dict(decision.signals),
            "decision": decision.decision,
            "action": action,
            "match_streak": 0 if state is None else int(state.match_streak),
            "miss_streak": 0 if state is None else int(state.miss_streak),
        }

    def legacy_signature_kind(
        self,
        hwnd: int,
        memo_exact: Optional[Dict[Tuple[int, str, int], bool]] = None,
        memo_contains: Optional[Dict[Tuple[int, str, int], bool]] = None,
    ) -> str:
        if self.has_window_text(hwnd, self.engine.rules.chrome_legacy_title, memo=memo_exact):
            return "exact"
        for token in self.engine.rules.chrome_legacy_title_contains:
            if not token:
                continue
            if self.has_window_text_contains(hwnd, token, memo=memo_contains):
                return "substring"
        return ""

    def legacy_hide_decision(self, legacy_kind: str) -> AdDecision:
        signals = self.blank_signals()
        signals["legacy_signature"] = legacy_kind
        if legacy_kind == "exact":
            return self.decision_hide(DECISION_STRONG, HIDE_REASON_LEGACY, signals)
        if legacy_kind == "substring":
            return self.decision_hide(DECISION_WEAK, HIDE_REASON_LEGACY, signals)
        return self.decision_none(signals)

    def aggressive_hide_decision(
        self,
        class_name: str,
        child_rect: Optional[tuple[int, int, int, int]],
        parent_rect: tuple[int, int, int, int],
        has_ad_token: bool,
    ) -> AdDecision:
        signals = self.blank_signals()
        signals["subtree_ad_token"] = bool(has_ad_token)
        is_chrome_widget = self.engine._layout.is_chrome_widget_class(class_name)
        is_bottom_banner = bool(
            child_rect
            and is_chrome_widget
            and self.engine._layout.is_bottom_banner_candidate(class_name, "", child_rect, parent_rect)
        )
        signals["chrome_widget_bottom_banner"] = is_bottom_banner
        if is_bottom_banner and has_ad_token:
            return self.decision_hide(DECISION_STRONG, HIDE_REASON_AGGRESSIVE, signals)
        if is_bottom_banner and self.engine.rules.hide_bottom_banner_without_token:
            return self.decision_hide(DECISION_STRONG, HIDE_REASON_AGGRESSIVE, signals)
        if is_chrome_widget and has_ad_token:
            return self.decision_hide(DECISION_WEAK, HIDE_REASON_AGGRESSIVE, signals)
        return self.decision_none(signals)

    def empty_eva_close_decision(
        self,
        class_name: str,
        window_text: str,
        parent_text: str,
        has_custom_scroll: bool,
        has_ad_signal: bool,
    ) -> AdDecision:
        signals = self.blank_signals()
        if (
            class_name == self.engine.rules.eva_child_class
            and window_text == ""
            and parent_text != ""
            and not has_custom_scroll
        ):
            signals["empty_eva_child"] = True
        if self.engine._layout.should_close_empty_eva_child(
            class_name,
            window_text,
            parent_text,
            has_custom_scroll,
            has_ad_signal,
        ):
            return self.decision_close(DECISION_WEAK, signals)
        return self.decision_none(signals)

    def subtree_contains_ad_token(
        self,
        hwnd: int,
        max_depth: int = 8,
        memo: Optional[Dict[Tuple[int, int], bool]] = None,
    ) -> bool:
        cache_key = (hwnd, max_depth)
        if memo is not None and cache_key in memo:
            return memo[cache_key]
        if max_depth < 0 or not self.engine.api.is_window(hwnd):
            if memo is not None:
                memo[cache_key] = False
            return False
        pid = self.engine.api.get_window_thread_process_id(hwnd)
        class_name = self.engine._get_class(hwnd)
        if self.engine._layout.contains_ad_token(self.engine._get_text(hwnd, pid, class_name)):
            if memo is not None:
                memo[cache_key] = True
            return True
        for child in self.engine._scanner.enum_children(hwnd):
            if self.subtree_contains_ad_token(child, max_depth - 1, memo=memo):
                if memo is not None:
                    memo[cache_key] = True
                return True
        if memo is not None:
            memo[cache_key] = False
        return False

    def class_name_starts_with(self, hwnd: int, prefix: str, max_depth: int = 8) -> bool:
        if max_depth < 0 or not self.engine.api.is_window(hwnd):
            return False
        if self.engine._get_class(hwnd).startswith(prefix):
            return True
        for child in self.engine._scanner.enum_children(hwnd):
            if self.class_name_starts_with(child, prefix, max_depth - 1):
                return True
        return False

    def has_window_text(
        self,
        hwnd: int,
        target: str,
        max_depth: int = 8,
        memo: Optional[Dict[Tuple[int, str, int], bool]] = None,
    ) -> bool:
        cache_key = (hwnd, target, max_depth)
        if memo is not None and cache_key in memo:
            return memo[cache_key]
        if max_depth < 0 or not self.engine.api.is_window(hwnd):
            if memo is not None:
                memo[cache_key] = False
            return False

        if (self.engine.api.get_window_text(hwnd) or "") == target:
            if memo is not None:
                memo[cache_key] = True
            return True

        for child in self.engine._scanner.enum_children(hwnd):
            if self.has_window_text(child, target, max_depth - 1, memo=memo):
                if memo is not None:
                    memo[cache_key] = True
                return True

        if memo is not None:
            memo[cache_key] = False
        return False

    def has_window_text_contains(
        self,
        hwnd: int,
        target: str,
        max_depth: int = 8,
        memo: Optional[Dict[Tuple[int, str, int], bool]] = None,
    ) -> bool:
        needle = (target or "").lower()
        if not needle:
            return False
        cache_key = (hwnd, needle, max_depth)
        if memo is not None and cache_key in memo:
            return memo[cache_key]
        if max_depth < 0 or not self.engine.api.is_window(hwnd):
            if memo is not None:
                memo[cache_key] = False
            return False

        text = (self.engine.api.get_window_text(hwnd) or "").lower()
        if needle in text:
            if memo is not None:
                memo[cache_key] = True
            return True

        for child in self.engine._scanner.enum_children(hwnd):
            if self.has_window_text_contains(child, needle, max_depth - 1, memo=memo):
                if memo is not None:
                    memo[cache_key] = True
                return True

        if memo is not None:
            memo[cache_key] = False
        return False

    def matches_legacy_signature(
        self,
        hwnd: int,
        memo_exact: Optional[Dict[Tuple[int, str, int], bool]] = None,
        memo_contains: Optional[Dict[Tuple[int, str, int], bool]] = None,
    ) -> bool:
        return bool(self.legacy_signature_kind(hwnd, memo_exact=memo_exact, memo_contains=memo_contains))
