from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from ..protocols import Rect, WindowIdentity
from ..win32_api import SW_HIDE, SW_SHOW, SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOZORDER, WM_CLOSE
from .constants import (
    ACTION_HIDE,
    DEFAULT_CLOSE_TIMEOUT_MS,
    HIDE_REASON_AGGRESSIVE,
    HIDE_REASON_POPUP,
    POPUP_GUARD_ALLOW,
    RESTORE_MISS_THRESHOLD,
)
from .models import AdDecision, CandidateState, HiddenWindowSnapshot

if TYPE_CHECKING:
    from .controller import LayoutOnlyEngine


class WindowActionExecutor:
    def __init__(self, engine: "LayoutOnlyEngine") -> None:
        self.engine = engine

    def apply_once(self) -> None:
        if not self.engine._can_mutate_windows():
            return

        with self.engine._data_lock:
            main_handles = list(self.engine._main_window_handles)
            candidates = list(self.engine._ad_subwindow_candidates)
            kakao_pids = set(self.engine._kakao_pids)

        resized = 0
        hidden = 0
        closed = 0
        popup_close_requests = 0
        popup_hide_fallbacks = 0
        popup_zero_size_fallbacks = 0
        now = time.time()
        matched_hidden_identities: Set[WindowIdentity] = set()
        legacy_text_memo: Dict[Tuple[int, str, int], bool] = {}
        legacy_contains_memo: Dict[Tuple[int, str, int], bool] = {}
        ad_token_memo: Dict[Tuple[int, int, bool], bool] = {}
        custom_scroll_memo: Dict[WindowIdentity, bool] = {}

        for wnd in main_handles:
            if self.engine._is_stopping():
                return
            if not self.engine.api.is_window(wnd):
                continue
            pid = self.engine.api.get_window_thread_process_id(wnd)
            if pid not in kakao_pids:
                continue
            parent_rect = self.engine.api.get_window_rect(wnd)
            if not parent_rect:
                continue
            if not self.engine._scanner.is_confirmed_main_window(wnd):
                continue
            parent_class_name = self.engine._get_class(wnd)

            children = self.engine._scanner.enum_children(wnd)
            parent_text = self.engine._get_text(wnd, pid, parent_class_name)
            main_window_has_ad_signal = False
            child_contexts: List[Tuple[int, WindowIdentity, str, str, Optional[Rect], AdDecision]] = []

            for child in children:
                if self.engine._is_stopping():
                    return
                if not self.engine.api.is_window(child):
                    continue
                if self.engine.api.get_parent(child) != wnd:
                    continue
                class_name = self.engine._get_class(child)
                identity = (child, pid, class_name)
                window_text = self.engine._get_text(child, pid, class_name)
                child_rect: Optional[Rect] = None
                aggressive_decision = self.engine._signals.decision_none()
                legacy_kind = ""
                if self.engine.settings.aggressive_mode:
                    child_rect = self.engine.api.get_window_rect(child)
                    if child_rect:
                        has_prior_state = (
                            self.engine._candidate_state(identity) is not None
                            or self.engine._is_hidden_identity(identity)
                        )
                        has_ad_token = self.engine._signals.subtree_contains_ad_token(
                            child,
                            memo=ad_token_memo,
                            fresh_text=has_prior_state,
                        )
                        aggressive_decision = self.engine._signals.aggressive_hide_decision(
                            class_name,
                            child_rect,
                            parent_rect,
                            has_ad_token,
                        )
                if self.engine.rules.close_empty_eva_child_requires_ad_signal:
                    legacy_kind = self.engine._signals.legacy_signature_kind(
                        child,
                        memo_exact=legacy_text_memo,
                        memo_contains=legacy_contains_memo,
                    )
                if legacy_kind or aggressive_decision.matched:
                    main_window_has_ad_signal = True
                child_contexts.append(
                    (
                        child,
                        identity,
                        class_name,
                        window_text,
                        child_rect,
                        aggressive_decision,
                    )
                )

            for child, identity, class_name, window_text, child_rect, aggressive_decision in child_contexts:
                if self.engine._is_stopping():
                    return
                if class_name == self.engine.rules.eva_child_class and window_text == "" and parent_text != "":
                    has_custom_scroll = custom_scroll_memo.get(identity)
                    if has_custom_scroll is None:
                        has_custom_scroll = self.engine._signals.class_name_starts_with(
                            child,
                            self.engine.rules.custom_scroll_prefix,
                        )
                        custom_scroll_memo[identity] = has_custom_scroll
                    close_decision = self.engine._signals.empty_eva_close_decision(
                        class_name,
                        window_text,
                        parent_text,
                        has_custom_scroll,
                        main_window_has_ad_signal,
                    )
                    if close_decision.matched or self.engine._candidate_state(identity) is not None:
                        _close_state, close_confirmed = self.engine._update_candidate_state(identity, close_decision, now)
                        if close_confirmed:
                            if not self.engine._can_mutate_windows():
                                return
                            if self.close_window(child, "empty-eva-close"):
                                closed += 1
                    elif self.engine._signals.has_relevant_signal(close_decision):
                        self.engine._update_candidate_state(identity, close_decision, now)
                    if close_decision.matched and self.engine._is_hidden_identity(identity):
                        matched_hidden_identities.add(identity)

                if not self.engine._can_mutate_windows():
                    return
                if self.engine._layout.apply_view_resize(child, window_text, parent_rect):
                    resized += 1

                if not self.engine.settings.aggressive_mode or child_rect is None:
                    continue
                if aggressive_decision.matched or self.engine._candidate_state(identity) is not None or self.engine._is_hidden_identity(identity):
                    _aggressive_state, aggressive_confirmed = self.engine._update_candidate_state(identity, aggressive_decision, now)
                    if aggressive_decision.matched and self.engine._is_hidden_identity(identity):
                        matched_hidden_identities.add(identity)
                    if aggressive_confirmed and aggressive_decision.action == ACTION_HIDE:
                        if not self.engine._can_mutate_windows():
                            return
                        hidden_ok, hide_applied = self.ensure_window_hidden(
                            child,
                            pid,
                            class_name,
                            hide_reason=aggressive_decision.hide_reason,
                        )
                        if hidden_ok:
                            matched_hidden_identities.add(identity)
                            if hide_applied:
                                hidden += 1

        for wnd in candidates:
            if self.engine._is_stopping():
                return
            if not self.engine.api.is_window(wnd):
                continue
            pid = self.engine.api.get_window_thread_process_id(wnd)
            if pid not in kakao_pids:
                continue
            class_name = self.engine._get_class(wnd)
            identity = (wnd, pid, class_name)
            legacy_kind = self.engine._signals.legacy_signature_kind(
                wnd,
                memo_exact=legacy_text_memo,
                memo_contains=legacy_contains_memo,
            )
            legacy_decision = self.engine._signals.legacy_hide_decision(legacy_kind)
            if legacy_decision.matched or self.engine._candidate_state(identity) is not None or self.engine._is_hidden_identity(identity):
                _legacy_state, legacy_confirmed = self.engine._update_candidate_state(identity, legacy_decision, now)
                if legacy_decision.matched and self.engine._is_hidden_identity(identity):
                    matched_hidden_identities.add(identity)
                if legacy_confirmed and legacy_decision.action == ACTION_HIDE:
                    if not self.engine._can_mutate_windows():
                        return
                    hidden_ok, hide_applied = self.ensure_window_hidden(
                        wnd,
                        pid,
                        class_name,
                        hide_reason=legacy_decision.hide_reason,
                    )
                    if hidden_ok:
                        matched_hidden_identities.add(identity)
                        if hide_applied:
                            hidden += 1

        (
            popup_hidden,
            popup_closed,
            popup_close_requests,
            popup_hide_fallbacks,
            popup_zero_size_fallbacks,
            popup_matched_identities,
        ) = self.remove_popup_ads(kakao_pids, now=now)
        hidden += popup_hidden
        closed += popup_closed
        matched_hidden_identities.update(popup_matched_identities)

        self.restore_no_longer_matched_hidden_windows(matched_hidden_identities, now=now)

        with self.engine._state_lock:
            self.engine._state.resized_windows += resized
            self.engine._state.hidden_windows += hidden
            self.engine._state.closed_windows += closed
            self.engine._state.popup_close_requests += popup_close_requests
            self.engine._state.popup_hide_fallbacks += popup_hide_fallbacks
            self.engine._state.popup_zero_size_fallbacks += popup_zero_size_fallbacks
            self.engine._state.last_tick = now

        self.engine._maybe_cleanup_caches(now)

    def close_window(self, hwnd: int, reason: str) -> bool:
        if not self.engine._can_mutate_windows() or hwnd <= 0 or not self.engine.api.is_window(hwnd):
            return False
        ok, _result = self.engine.api.send_message_timeout(
            hwnd,
            WM_CLOSE,
            0,
            0,
            timeout_ms=DEFAULT_CLOSE_TIMEOUT_MS,
        )
        if not ok:
            self.engine._set_error(f"{reason}: hwnd={hwnd} close timeout/failure win32err={self.engine._api_last_error()}")
        return ok

    def _capture_hidden_snapshot(
        self,
        hwnd: int,
        pid: int,
        class_name: str,
        hide_reason: str,
    ) -> Optional[HiddenWindowSnapshot]:
        if pid <= 0 or not self.engine.api.is_window(hwnd):
            return None
        return HiddenWindowSnapshot(
            was_visible=bool(self.engine.api.is_window_visible(hwnd)),
            rect=self.engine.api.get_window_rect(hwnd),
            pid=pid,
            class_name=class_name,
            hide_reason=hide_reason,
        )

    def _track_hidden_snapshot(self, identity: WindowIdentity, snapshot: HiddenWindowSnapshot) -> None:
        with self.engine._cache_lock:
            self.engine._hidden_windows.setdefault(identity, snapshot)
            tracked_snapshot = self.engine._hidden_windows.get(identity)
        self.engine._note_candidate_snapshot(identity, tracked_snapshot)

    def _is_hidden_with_reason(self, identity: WindowIdentity, hide_reason: str) -> bool:
        with self.engine._cache_lock:
            snapshot = self.engine._hidden_windows.get(identity)
        return bool(snapshot and snapshot.hide_reason == hide_reason)

    def remove_popup_ads(
        self,
        kakao_pids: Set[int],
        now: Optional[float] = None,
    ) -> Tuple[int, int, int, int, int, Set[WindowIdentity]]:
        if not kakao_pids or not self.engine._popup_ad_class_set or not self.engine._can_mutate_windows():
            return 0, 0, 0, 0, 0, set()

        hidden = 0
        closed = 0
        close_requests = 0
        hide_fallbacks = 0
        zero_size_fallbacks = 0
        matched_identities: Set[WindowIdentity] = set()
        handled_hwnds: Set[int] = set()
        decision_time = now or time.time()

        for item in self.engine._scanner.collect_windows(kakao_pids):
            if self.engine._is_stopping():
                return hidden, closed, close_requests, hide_fallbacks, zero_size_fallbacks, matched_identities
            if item.parent_hwnd != 0:
                continue
            if self.engine._scanner.is_confirmed_main_window(item.hwnd, item=item):
                continue
            host_identity = (item.hwnd, item.pid, item.class_name)
            host_hidden_popup = self._is_hidden_with_reason(host_identity, HIDE_REASON_POPUP)
            if not self.engine.api.is_window_visible(item.hwnd) and not host_hidden_popup:
                continue
            popup_guard = self.engine._signals.popup_host_guard_status(item.text)

            for child, depth, class_name in self.engine._scanner.find_popup_matches(
                item.hwnd,
                require_visible=not host_hidden_popup,
            ):
                if self.engine._is_stopping():
                    return hidden, closed, close_requests, hide_fallbacks, zero_size_fallbacks, matched_identities
                if not self.engine.api.is_window(child):
                    continue
                child_identity = (
                    child,
                    self.engine.api.get_window_thread_process_id(child),
                    class_name,
                )
                popup_decision = self.engine._signals.popup_dismiss_decision(popup_guard, depth)
                self.engine._update_candidate_state(child_identity, popup_decision, decision_time)
                if popup_guard != POPUP_GUARD_ALLOW:
                    continue

                matched_identities.add(host_identity)
                matched_identities.add(child_identity)

                if item.hwnd not in handled_hwnds and not self._is_hidden_with_reason(host_identity, HIDE_REASON_POPUP):
                    (
                        parent_hidden,
                        parent_closed,
                        parent_close_requests,
                        parent_hide_fallbacks,
                        parent_zero_size_fallbacks,
                    ) = self.dismiss_popup_window(item.hwnd)
                    hidden += parent_hidden
                    closed += parent_closed
                    close_requests += parent_close_requests
                    hide_fallbacks += parent_hide_fallbacks
                    zero_size_fallbacks += parent_zero_size_fallbacks
                    handled_hwnds.add(item.hwnd)
                if child not in handled_hwnds and not self._is_hidden_with_reason(child_identity, HIDE_REASON_POPUP):
                    (
                        child_hidden,
                        child_closed,
                        child_close_requests,
                        child_hide_fallbacks,
                        child_zero_size_fallbacks,
                    ) = self.dismiss_popup_window(child)
                    hidden += child_hidden
                    closed += child_closed
                    close_requests += child_close_requests
                    hide_fallbacks += child_hide_fallbacks
                    zero_size_fallbacks += child_zero_size_fallbacks
                    handled_hwnds.add(child)
        return hidden, closed, close_requests, hide_fallbacks, zero_size_fallbacks, matched_identities

    def dismiss_popup_window(self, hwnd: int) -> Tuple[int, int, int, int, int]:
        if not self.engine._can_mutate_windows() or hwnd <= 0 or not self.engine.api.is_window(hwnd):
            return 0, 0, 0, 0, 0
        pid = self.engine.api.get_window_thread_process_id(hwnd)
        class_name = self.engine._get_class(hwnd)
        identity = (hwnd, pid, class_name)
        snapshot = self._capture_hidden_snapshot(hwnd, pid, class_name, HIDE_REASON_POPUP)

        close_requests = 1
        self.close_window(hwnd, "popup-dismiss")
        if not self.engine.api.is_window(hwnd):
            return 1, 1, close_requests, 0, 0

        if not self.engine._can_mutate_windows():
            return 0, 0, close_requests, 0, 0
        self.engine.api.show_window(hwnd, SW_HIDE)
        if not self.engine.api.is_window(hwnd):
            return 1, 1, close_requests, 0, 0
        hidden_ok = not self.engine.api.is_window_visible(hwnd)
        hide_fallbacks = 1 if hidden_ok else 0
        if not hidden_ok:
            self.engine.logger.debug(
                "popup window still visible after SW_HIDE hwnd=%s win32err=%s",
                hwnd,
                self.engine._api_last_error(),
            )

        if not self.engine._can_mutate_windows():
            return (1 if hidden_ok else 0, 0, close_requests, hide_fallbacks, 0)
        resized_ok = bool(self.engine.api.set_window_pos(hwnd, 0, 0, 0, 0, 0))
        if not self.engine.api.is_window(hwnd):
            return 1, 1, close_requests, hide_fallbacks, 0
        zero_size_fallbacks = 1 if resized_ok else 0
        if not resized_ok:
            self.engine.logger.debug(
                "popup set_window_pos(zero-size) failed hwnd=%s win32err=%s",
                hwnd,
                self.engine._api_last_error(),
            )

        if not hidden_ok or not resized_ok:
            failures: list[str] = []
            if not hidden_ok:
                failures.append("hide failed")
            if not resized_ok:
                failures.append("zero-size failed")
            self.engine._set_error(f"popup-dismiss: hwnd={hwnd} {'; '.join(failures)}")

        if (hidden_ok or resized_ok) and snapshot is not None:
            self._track_hidden_snapshot(identity, snapshot)

        return (1 if hidden_ok or resized_ok else 0, 0, close_requests, hide_fallbacks, zero_size_fallbacks)

    def hide_window(self, hwnd: int, pid: int, class_name: str, hide_reason: str) -> bool:
        if not self.engine._can_mutate_windows():
            return False
        if hide_reason == HIDE_REASON_AGGRESSIVE and not self.engine.settings.aggressive_mode:
            return False
        if pid <= 0 or not self.engine.api.is_window(hwnd):
            return False
        identity = (hwnd, pid, class_name)
        with self.engine._cache_lock:
            if identity not in self.engine._hidden_windows:
                snapshot = self._capture_hidden_snapshot(hwnd, pid, class_name, hide_reason)
                if snapshot is not None:
                    self.engine._hidden_windows[identity] = snapshot
            snapshot = self.engine._hidden_windows.get(identity)
        self.engine._note_candidate_snapshot(identity, snapshot)

        if not self.engine._can_mutate_windows():
            return False
        self.engine.api.show_window(hwnd, SW_HIDE)
        if not self.engine.api.is_window_visible(hwnd):
            return True
        self.engine.logger.debug("window still visible after SW_HIDE hwnd=%s win32err=%s", hwnd, self.engine._api_last_error())

        if not self.engine._can_mutate_windows():
            return False
        moved = bool(
            self.engine.api.set_window_pos(
                hwnd,
                -32000,
                -32000,
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
        )
        if moved:
            return True
        self.engine.logger.debug("set_window_pos(offscreen) failed hwnd=%s win32err=%s", hwnd, self.engine._api_last_error())

        with self.engine._cache_lock:
            self.engine._hidden_windows.pop(identity, None)
        self.engine._note_candidate_snapshot(identity, None)
        return False

    def ensure_window_hidden(self, hwnd: int, pid: int, class_name: str, hide_reason: str) -> tuple[bool, bool]:
        identity = (hwnd, pid, class_name)
        if self.engine._is_hidden_identity(identity) and not self.engine.api.is_window_visible(hwnd):
            return True, False
        return self.hide_window(hwnd, pid, class_name, hide_reason=hide_reason), True

    def restore_no_longer_matched_hidden_windows(
        self,
        matched_identities: Set[WindowIdentity],
        *,
        now: Optional[float] = None,
    ) -> None:
        now_value = now or time.time()
        with self.engine._cache_lock:
            stale_identities = {
                identity for identity in self.engine._hidden_windows.keys() if identity not in matched_identities
            }
            restore_ready: Set[WindowIdentity] = set()
            for identity in stale_identities:
                state = self.engine._candidate_states.get(identity)
                if state is None:
                    state = CandidateState()
                    self.engine._candidate_states[identity] = state
                state.match_streak = 0
                state.miss_streak += 1
                grace_elapsed_ms = max(now_value - state.last_action_at, 0.0) * 1000.0
                if (
                    grace_elapsed_ms >= float(self.engine.rules.hidden_restore_grace_ms)
                    or state.miss_streak >= RESTORE_MISS_THRESHOLD
                ):
                    restore_ready.add(identity)
        if restore_ready:
            self.restore_hidden_windows(reason="stale-mismatch", target_identities=restore_ready)

    def restore_hidden_windows(
        self,
        reason: str,
        target_identities: Optional[Set[WindowIdentity]] = None,
        target_hide_reasons: Optional[Set[str]] = None,
    ) -> None:
        with self.engine._cache_lock:
            snapshots = [
                (identity, snap)
                for identity, snap in self.engine._hidden_windows.items()
                if (target_identities is None or identity in target_identities)
                and (target_hide_reasons is None or snap.hide_reason in target_hide_reasons)
            ]
        if not snapshots:
            return

        for identity, snap in snapshots:
            hwnd, expected_pid, expected_class = identity
            if not self.engine.api.is_window(hwnd):
                with self.engine._cache_lock:
                    self.engine._hidden_windows.pop(identity, None)
                continue

            current_pid = self.engine.api.get_window_thread_process_id(hwnd)
            current_class = self.engine._get_class(hwnd)
            if current_pid != expected_pid or current_class != expected_class:
                self.engine.logger.debug(
                    "Skip restore for recycled hwnd=%s reason=%s expected=(%s,%s) current=(%s,%s)",
                    hwnd,
                    reason,
                    expected_pid,
                    expected_class,
                    current_pid,
                    current_class,
                )
                with self.engine._cache_lock:
                    self.engine._hidden_windows.pop(identity, None)
                continue

            restored = True
            failure_reason = ""
            if snap.rect:
                left, top, right, bottom = snap.rect
                width = right - left
                height = bottom - top
                if width > 0 and height > 0:
                    if not self.engine.api.set_window_pos(
                        hwnd,
                        left,
                        top,
                        width,
                        height,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    ):
                        restored = False
                        failure_reason = "set_window_pos failed"
                        self.engine.logger.debug(
                            "set_window_pos(restore) failed hwnd=%s win32err=%s",
                            hwnd,
                            self.engine._api_last_error(),
                        )
                else:
                    restored = False
                    failure_reason = "invalid rect size"

            if snap.was_visible:
                self.engine.api.show_window(hwnd, SW_SHOW)
                if not self.engine.api.is_window_visible(hwnd):
                    restored = False
                    failure_reason = "window still hidden after SW_SHOW"
                    self.engine.logger.debug(
                        "window still hidden after SW_SHOW hwnd=%s win32err=%s",
                        hwnd,
                        self.engine._api_last_error(),
                    )

            if not restored:
                self.engine.logger.warning("Failed to restore hidden window hwnd=%s reason=%s", hwnd, reason)
                with self.engine._state_lock:
                    self.engine._state.restore_failures += 1
                    self.engine._state.last_restore_error = (
                        f"hwnd={hwnd} restore failed ({failure_reason or 'unknown'})"
                    )
            else:
                with self.engine._cache_lock:
                    self.engine._hidden_windows.pop(identity, None)
                    state = self.engine._candidate_states.get(identity)
                    if state is not None:
                        state.snapshot = None
