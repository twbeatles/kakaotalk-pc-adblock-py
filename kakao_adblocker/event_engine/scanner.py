from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from .models import WindowInfo

if TYPE_CHECKING:
    from .controller import LayoutOnlyEngine


class WindowScanner:
    def __init__(self, engine: "LayoutOnlyEngine") -> None:
        self.engine = engine

    def get_kakao_pids(self, now: float) -> Set[int]:
        scan_interval = self.engine._pid_scan_interval_seconds()
        with self.engine._data_lock:
            use_cached = self.engine._last_pid_scan > 0 and (now - self.engine._last_pid_scan) < scan_interval
            if use_cached:
                return set(self.engine._pid_scan_cache)

        pids = set(self.engine._process_ids_provider("kakaotalk.exe"))
        pid_warning = self.engine._consume_process_warning()
        if pid_warning:
            self.engine._set_error(f"pid-scan: {pid_warning}")
        with self.engine._data_lock:
            self.engine._pid_scan_cache = set(pids)
            self.engine._last_pid_scan = now
        return pids

    def collect_windows(self, pids: Set[int], include_geometry: bool = False) -> List[WindowInfo]:
        if not pids:
            return []
        result: List[WindowInfo] = []

        def cb(hwnd: int) -> bool:
            pid = self.engine.api.get_window_thread_process_id(hwnd)
            if pid not in pids:
                return True
            class_name = self.engine._get_class(hwnd)
            result.append(
                WindowInfo(
                    hwnd=hwnd,
                    pid=pid,
                    class_name=class_name,
                    text=self.engine._get_text(hwnd, pid, class_name),
                    parent_hwnd=self.engine.api.get_parent(hwnd),
                    rect=self.engine.api.get_window_rect(hwnd) if include_geometry else None,
                    visible=bool(self.engine.api.is_window_visible(hwnd)) if include_geometry else False,
                )
            )
            return True

        self.engine.api.enum_windows(cb)
        return result

    def enum_children(self, parent_hwnd: int) -> List[int]:
        children: List[int] = []
        self.engine.api.enum_child_windows(parent_hwnd, lambda hwnd: children.append(hwnd) or True)
        return children

    def is_main_window_candidate(self, item: WindowInfo) -> bool:
        if item.class_name not in self.engine._main_window_class_set:
            return False
        if item.parent_hwnd != 0:
            return False
        if item.text and not self.engine._is_main_title(item.text):
            return False
        return True

    def is_confirmed_main_window(self, hwnd: int, item: Optional[WindowInfo] = None) -> bool:
        if item is not None and not self.is_main_window_candidate(item):
            return False
        if item is None:
            pid = self.engine.api.get_window_thread_process_id(hwnd)
            if pid <= 0:
                return False
            class_name = self.engine._get_class(hwnd)
            item = WindowInfo(
                hwnd=hwnd,
                pid=pid,
                class_name=class_name,
                text=self.engine._get_text(hwnd, pid, class_name),
                parent_hwnd=self.engine.api.get_parent(hwnd),
                rect=None,
                visible=False,
            )
            if not self.is_main_window_candidate(item):
                return False
        return self.has_main_view_signature(hwnd)

    def is_main_window(self, child_handles: List[int]) -> bool:
        for hwnd in child_handles:
            class_name = self.engine._get_class(hwnd)
            if class_name != self.engine.rules.eva_child_class:
                continue
            pid = self.engine.api.get_window_thread_process_id(hwnd)
            txt = self.engine._get_text(hwnd, pid, class_name)
            if txt.startswith(self.engine.rules.main_view_prefix) or txt.startswith(self.engine.rules.lock_view_prefix):
                return True
        return False

    def has_main_view_signature(self, parent_hwnd: int) -> bool:
        if not self.engine.api.is_window(parent_hwnd):
            return False
        return self.is_main_window(self.enum_children(parent_hwnd))

    def watch_once(self) -> None:
        if self.engine._is_stopping():
            return
        now = time.time()
        was_active = self.engine._is_active_mode(now)
        pids = self.get_kakao_pids(now)
        windows = self.collect_windows(pids) if pids else []
        if self.engine._is_stopping():
            return
        candidate_main_handles: Set[int] = set()
        main_handles: Set[int] = set()
        candidates: Set[int] = set()
        legacy_text_memo: Dict[Tuple[int, str, int], bool] = {}
        legacy_contains_memo: Dict[Tuple[int, str, int], bool] = {}

        for item in windows:
            if self.engine._is_stopping():
                return
            if not self.is_main_window_candidate(item):
                continue
            candidate_main_handles.add(item.hwnd)
            if self.is_confirmed_main_window(item.hwnd, item=item):
                main_handles.add(item.hwnd)

        for item in windows:
            if self.engine._is_stopping():
                return
            if item.class_name not in self.engine._ad_candidate_class_set:
                continue
            if item.parent_hwnd in main_handles:
                if item.text == "":
                    candidates.add(item.hwnd)
                continue
            if item.parent_hwnd == 0 and self.engine._signals.matches_legacy_signature(
                item.hwnd,
                memo_exact=legacy_text_memo,
                memo_contains=legacy_contains_memo,
            ):
                candidates.add(item.hwnd)

        with self.engine._data_lock:
            previous_pids = set(self.engine._kakao_pids)
            previous_main_handles = set(self.engine._main_window_handles)
            previous_candidates = set(self.engine._ad_subwindow_candidates)
            self.engine._kakao_pids = pids
            self.engine._main_window_handles = main_handles
            self.engine._ad_subwindow_candidates = candidates
            if (
                self.engine.settings.burst_scan_iterations > 0
                and (
                    bool(pids - previous_pids)
                    or bool(main_handles - previous_main_handles)
                    or bool(candidates - previous_candidates)
                )
            ):
                self.engine._burst_scans_remaining = max(
                    self.engine._burst_scans_remaining,
                    int(self.engine.settings.burst_scan_iterations),
                )

        if pids:
            self.engine._mark_activity(now, wake=not was_active)

        with self.engine._state_lock:
            self.engine._state.kakao_pid_count = len(pids)
            self.engine._state.candidate_main_window_count = len(candidate_main_handles)
            self.engine._state.main_window_count = len(main_handles)
            self.engine._state.last_tick = now

        self.engine._maybe_cleanup_caches(now)
