from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from ..protocols import Rect, WindowIdentity
from ..win32_api import SW_HIDE, SW_SHOW, SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOZORDER, WM_CLOSE
from .constants import ACTION_HIDE, POPUP_GUARD_ALLOW, RESTORE_MISS_THRESHOLD
from .models import AdDecision, CandidateState, HiddenWindowSnapshot

if TYPE_CHECKING:
    from .controller import LayoutOnlyEngine


class WindowActionExecutor:
    def __init__(self, engine: "LayoutOnlyEngine") -> None:
        self.engine = engine

    def apply_once(self) -> None:
        if not self.engine._is_enabled() or self.engine._is_stopping():
            return

        with self.engine._data_lock:
            main_handles = list(self.engine._main_window_handles)
            candidates = list(self.engine._ad_subwindow_candidates)
            kakao_pids = set(self.engine._kakao_pids)

        resized = 0
        hidden = 0
        closed = 0
        now = time.time()
        matched_hidden_identities: Set[WindowIdentity] = set()
        legacy_text_memo: Dict[Tuple[int, str, int], bool] = {}
        legacy_contains_memo: Dict[Tuple[int, str, int], bool] = {}
        ad_token_memo: Dict[Tuple[int, int], bool] = {}

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
                window_text = self.engine._get_text(child, pid, class_name)
                child_rect: Optional[Rect] = None
                aggressive_decision = self.engine._signals.decision_none()
                legacy_kind = ""
                if self.engine.settings.aggressive_mode:
                    child_rect = self.engine.api.get_window_rect(child)
                    if child_rect:
                        has_ad_token = self.engine._signals.subtree_contains_ad_token(child, memo=ad_token_memo)
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
                        (child, pid, class_name),
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
                    with self.engine._cache_lock:
                        has_custom_scroll = self.engine._custom_scroll_cache.get(identity)
                    if has_custom_scroll is None:
                        has_custom_scroll = self.engine._signals.class_name_starts_with(
                            child,
                            self.engine.rules.custom_scroll_prefix,
                        )
                        with self.engine._cache_lock:
                            self.engine._custom_scroll_cache[identity] = has_custom_scroll
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
                            if self.engine._is_stopping():
                                return
                            self.engine.api.send_message(child, WM_CLOSE, 0, 0)
                            closed += 1
                    elif self.engine._signals.has_relevant_signal(close_decision):
                        self.engine._update_candidate_state(identity, close_decision, now)
                    if close_decision.matched and self.engine._is_hidden_identity(identity):
                        matched_hidden_identities.add(identity)

                if self.engine._is_stopping():
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
                        if self.engine._is_stopping():
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

        popup_hidden, popup_closed = self.remove_popup_ads(kakao_pids, now=now)
        hidden += popup_hidden
        closed += popup_closed

        self.restore_no_longer_matched_hidden_windows(matched_hidden_identities, now=now)

        with self.engine._state_lock:
            self.engine._state.resized_windows += resized
            self.engine._state.hidden_windows += hidden
            self.engine._state.closed_windows += closed
            self.engine._state.last_tick = now

        self.engine._maybe_cleanup_caches(now)

    def remove_popup_ads(self, kakao_pids: Set[int], now: Optional[float] = None) -> Tuple[int, int]:
        if not kakao_pids or not self.engine._popup_ad_class_set or self.engine._is_stopping():
            return 0, 0

        hidden = 0
        closed = 0
        handled_hwnds: Set[int] = set()
        decision_time = now or time.time()

        for item in self.engine._scanner.collect_windows(kakao_pids):
            if self.engine._is_stopping():
                return hidden, closed
            if item.parent_hwnd != 0:
                continue
            if self.engine._scanner.is_confirmed_main_window(item.hwnd, item=item):
                continue
            if not self.engine.api.is_window_visible(item.hwnd):
                continue
            popup_guard = self.engine._signals.popup_host_guard_status(item.text)

            for child in self.engine._scanner.enum_children(item.hwnd):
                if self.engine._is_stopping():
                    return hidden, closed
                if not self.engine.api.is_window(child):
                    continue
                if self.engine.api.get_parent(child) != item.hwnd:
                    continue
                if not self.engine.api.is_window_visible(child):
                    continue
                if self.engine._get_class(child) not in self.engine._popup_ad_class_set:
                    continue
                child_identity = (
                    child,
                    self.engine.api.get_window_thread_process_id(child),
                    self.engine._get_class(child),
                )
                popup_signals = self.engine._signals.blank_signals()
                popup_signals["popup_direct_class"] = True
                popup_signals["popup_host_guard"] = popup_guard
                popup_decision = (
                    self.engine._signals.decision_dismiss_popup(popup_signals)
                    if popup_guard == POPUP_GUARD_ALLOW
                    else self.engine._signals.decision_none(popup_signals)
                )
                self.engine._update_candidate_state(child_identity, popup_decision, decision_time)
                if popup_guard != POPUP_GUARD_ALLOW:
                    continue

                if item.hwnd not in handled_hwnds:
                    parent_hidden, parent_closed = self.dismiss_popup_window(item.hwnd)
                    hidden += parent_hidden
                    closed += parent_closed
                    handled_hwnds.add(item.hwnd)
                if child not in handled_hwnds:
                    child_hidden, child_closed = self.dismiss_popup_window(child)
                    hidden += child_hidden
                    closed += child_closed
                    handled_hwnds.add(child)
        return hidden, closed

    def dismiss_popup_window(self, hwnd: int) -> Tuple[int, int]:
        if self.engine._is_stopping() or hwnd <= 0 or not self.engine.api.is_window(hwnd):
            return 0, 0
        self.engine.api.send_message(hwnd, WM_CLOSE, 0, 0)
        if not self.engine.api.is_window(hwnd):
            return 1, 1

        self.engine.api.show_window(hwnd, SW_HIDE)
        if not self.engine.api.is_window(hwnd):
            return 1, 1
        hidden_ok = not self.engine.api.is_window_visible(hwnd)
        if not hidden_ok:
            self.engine.logger.debug(
                "popup window still visible after SW_HIDE hwnd=%s win32err=%s",
                hwnd,
                self.engine._api_last_error(),
            )

        resized_ok = bool(self.engine.api.set_window_pos(hwnd, 0, 0, 0, 0, 0))
        if not self.engine.api.is_window(hwnd):
            return 1, 1
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

        return (1 if hidden_ok or resized_ok else 0, 0)

    def hide_window(self, hwnd: int, pid: int, class_name: str, hide_reason: str) -> bool:
        if self.engine._is_stopping():
            return False
        if pid <= 0 or not self.engine.api.is_window(hwnd):
            return False
        identity = (hwnd, pid, class_name)
        with self.engine._cache_lock:
            if identity not in self.engine._hidden_windows:
                self.engine._hidden_windows[identity] = HiddenWindowSnapshot(
                    was_visible=bool(self.engine.api.is_window_visible(hwnd)),
                    rect=self.engine.api.get_window_rect(hwnd),
                    pid=pid,
                    class_name=class_name,
                    hide_reason=hide_reason,
                )
            snapshot = self.engine._hidden_windows.get(identity)
        self.engine._note_candidate_snapshot(identity, snapshot)

        self.engine.api.show_window(hwnd, SW_HIDE)
        if not self.engine.api.is_window_visible(hwnd):
            return True
        self.engine.logger.debug("window still visible after SW_HIDE hwnd=%s win32err=%s", hwnd, self.engine._api_last_error())

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
