from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from typing import Callable, Dict, Optional, Set, Tuple

from ..config import LayoutRulesV11, LayoutSettingsV11, get_runtime_paths
from ..layout_engine import LayoutEngine
from ..protocols import JoinableThreadLike, WindowIdentity, Win32ApiLike
from ..services import ProcessInspector
from ..win32_api import Win32API
from .actions import WindowActionExecutor
from .constants import (
    DISABLED_LOOP_WAIT_SECONDS,
    ERROR_LOG_PRUNE_TARGET,
    HIDE_REASON_AGGRESSIVE,
    MAX_ERROR_LOG_KEYS,
)
from .dump import WindowDumpBuilder
from .models import AdDecision, CandidateState, EngineState, HiddenWindowSnapshot
from .scanner import WindowScanner
from .signals import SignalEvaluator


class LayoutOnlyEngine:
    def __init__(
        self,
        logger: logging.Logger,
        settings: LayoutSettingsV11,
        rules: LayoutRulesV11,
        api: Optional[Win32ApiLike] = None,
        process_ids_provider: Optional[Callable[[str], Set[int]]] = None,
    ) -> None:
        self.logger = logger.getChild("LayoutOnlyEngine")
        self.settings = settings
        self.rules = rules
        self.api = api or Win32API()
        self._process_ids_provider = process_ids_provider or ProcessInspector.get_process_ids
        self._layout = LayoutEngine(self.api, self.rules, self.logger.getChild("Layout"))

        self._state = EngineState(enabled=self.settings.enabled, running=False)
        self._state_lock = threading.Lock()
        self._data_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._error_log_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._watch_thread: Optional[JoinableThreadLike] = None

        self._main_window_class_set = frozenset(self.rules.main_window_classes)
        self._ad_candidate_class_set = frozenset(self.rules.ad_candidate_classes)
        self._popup_ad_class_set = frozenset(self.rules.popup_ad_classes)
        self._main_window_handles: Set[int] = set()
        self._ad_subwindow_candidates: Set[int] = set()
        self._kakao_pids: Set[int] = set()
        self._pid_scan_cache: Set[int] = set()
        self._last_pid_scan: float = 0.0
        self._last_cache_cleanup: float = 0.0
        self._last_activity: float = 0.0
        self._hidden_windows: Dict[WindowIdentity, HiddenWindowSnapshot] = {}
        self._custom_scroll_cache: Dict[WindowIdentity, bool] = {}
        self._candidate_states: Dict[WindowIdentity, CandidateState] = {}
        self._burst_scans_remaining = 0

        self._text_cache: Dict[WindowIdentity, Tuple[float, str]] = {}
        self._last_log: Dict[str, float] = {}

        self._scanner = WindowScanner(self)
        self._signals = SignalEvaluator(self)
        self._actions = WindowActionExecutor(self)
        self._dump = WindowDumpBuilder(self)

    @property
    def state(self) -> EngineState:
        with self._state_lock:
            return EngineState(**asdict(self._state))

    def start(self) -> None:
        with self._state_lock:
            if self._state.running:
                return
            self._state.running = True
            self._state.enabled = bool(self.settings.enabled)
            self._state.last_error = ""
            self._state.resized_windows = 0
            self._state.hidden_windows = 0
            self._state.closed_windows = 0
            self._state.candidate_main_window_count = 0
            self._state.restore_failures = 0
            self._state.last_restore_error = ""
            enabled_on_start = self._state.enabled
        with self._data_lock:
            self._pid_scan_cache = set()
            self._last_pid_scan = 0.0
            self._last_cache_cleanup = 0.0
            self._last_activity = time.time()
            self._burst_scans_remaining = 0
        with self._cache_lock:
            self._candidate_states.clear()
        self._stop_event.clear()
        self._wake_event.clear()

        if enabled_on_start:
            try:
                self._watch_once()
                self._apply_once()
            except Exception as e:
                self._set_error(f"warmup: {e}")

        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        watch_thread = self._watch_thread
        timed_out = False
        if watch_thread and watch_thread.is_alive():
            watch_thread.join(timeout=2.0)
            timed_out = watch_thread.is_alive()
        if timed_out:
            self._set_error("stop: watch thread did not terminate within 2.0s")
            self.logger.warning("Watch thread join timed out during stop")
        self._watch_thread = None
        self._restore_hidden_windows(reason="stop")
        with self._state_lock:
            self._state.running = False

    def set_enabled(self, enabled: bool) -> None:
        enabled_value = bool(enabled)
        self.settings.enabled = enabled_value
        with self._state_lock:
            was_enabled = self._state.enabled
            self._state.enabled = enabled_value
        if was_enabled and not enabled_value:
            self._restore_hidden_windows(reason="disabled")
            self._clear_scan_state()
        self._wake_event.set()

    def set_aggressive_mode(self, enabled: bool) -> None:
        enabled_value = bool(enabled)
        self.settings.aggressive_mode = enabled_value
        if not enabled_value:
            self._restore_hidden_windows(
                reason="aggressive-disabled",
                target_hide_reasons={HIDE_REASON_AGGRESSIVE},
            )
        if self._is_enabled():
            self.force_scan()
            self._wake_event.set()

    def report_warning(self, message: str) -> None:
        if not message:
            return
        now = time.time()
        with self._state_lock:
            self._state.last_error = message
            self._state.last_tick = now

    def reset_restore_failures(self) -> None:
        now = time.time()
        with self._state_lock:
            self._state.restore_failures = 0
            self._state.last_restore_error = ""
            self._state.last_tick = now

    def force_scan(self) -> None:
        self.scan_once()
        self.apply_once()

    def scan_once(self) -> None:
        self._watch_once()

    def apply_once(self) -> None:
        self._apply_once()

    def _watch_once(self) -> None:
        self._scanner.watch_once()

    def _apply_once(self) -> None:
        self._actions.apply_once()

    def _active_poll_interval_seconds(self) -> float:
        return max(int(self.settings.poll_interval_ms), 50) / 1000.0

    def _idle_poll_interval_seconds(self) -> float:
        return max(int(self.settings.idle_poll_interval_ms), 200) / 1000.0

    def _pid_scan_interval_seconds(self) -> float:
        return max(int(self.settings.pid_scan_interval_ms), 100) / 1000.0

    def _cache_cleanup_interval_seconds(self) -> float:
        return max(int(self.settings.cache_cleanup_interval_ms), 250) / 1000.0

    def _burst_scan_interval_seconds(self) -> float:
        return max(int(self.settings.burst_scan_interval_ms), 10) / 1000.0

    def _is_stopping(self) -> bool:
        return self._stop_event.is_set()

    def _is_enabled(self) -> bool:
        with self._state_lock:
            return self._state.enabled

    def _is_active_mode(self, now: Optional[float] = None) -> bool:
        now_value = now or time.time()
        with self._data_lock:
            if self._kakao_pids:
                return True
            last_activity = self._last_activity
        return bool(last_activity and (now_value - last_activity) <= 3.0)

    def _current_loop_interval_seconds(self, now: Optional[float] = None) -> float:
        if self._is_active_mode(now):
            return self._active_poll_interval_seconds()
        return self._idle_poll_interval_seconds()

    def _is_burst_mode_active(self) -> bool:
        with self._data_lock:
            return self._burst_scans_remaining > 0

    def _next_wait_interval_seconds(self, now: Optional[float] = None) -> float:
        with self._data_lock:
            if self._burst_scans_remaining > 0:
                self._burst_scans_remaining -= 1
                return self._burst_scan_interval_seconds()
        return self._current_loop_interval_seconds(now)

    def _wait_next_tick(self, timeout: float) -> None:
        if timeout <= 0:
            return
        self._wake_event.wait(timeout)
        self._wake_event.clear()

    def _mark_activity(self, now: float, wake: bool = False) -> None:
        with self._data_lock:
            self._last_activity = now
        if wake:
            self._wake_event.set()

    def _watch_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._is_enabled():
                self._wait_next_tick(DISABLED_LOOP_WAIT_SECONDS)
                continue
            try:
                self._watch_once()
            except Exception as e:
                self._set_error(f"watch: {e}")
            if self._is_stopping():
                break
            try:
                self._apply_once()
            except Exception as e:
                self._set_error(f"apply: {e}")
            self._wait_next_tick(self._next_wait_interval_seconds())

    def _update_candidate_state(self, identity: WindowIdentity, decision: AdDecision, now: float) -> tuple[CandidateState, bool]:
        with self._cache_lock:
            return self._signals.update_candidate_state_store(self._candidate_states, identity, decision, now)

    def _candidate_state(self, identity: WindowIdentity) -> Optional[CandidateState]:
        with self._cache_lock:
            return self._candidate_states.get(identity)

    def _is_hidden_identity(self, identity: WindowIdentity) -> bool:
        with self._cache_lock:
            return identity in self._hidden_windows

    def _note_candidate_snapshot(self, identity: WindowIdentity, snapshot: Optional[HiddenWindowSnapshot]) -> None:
        with self._cache_lock:
            state = self._candidate_states.get(identity)
            if state is None:
                state = CandidateState()
                self._candidate_states[identity] = state
            state.snapshot = snapshot

    def _consume_process_warning(self) -> str | None:
        return ProcessInspector.consume_last_warning()

    def _clear_scan_state(self) -> None:
        now = time.time()
        with self._data_lock:
            self._kakao_pids.clear()
            self._main_window_handles.clear()
            self._ad_subwindow_candidates.clear()
            self._pid_scan_cache.clear()
            self._last_pid_scan = 0.0
            self._last_activity = 0.0
            self._burst_scans_remaining = 0
        with self._cache_lock:
            self._candidate_states.clear()
        with self._state_lock:
            self._state.kakao_pid_count = 0
            self._state.candidate_main_window_count = 0
            self._state.main_window_count = 0
            self._state.last_tick = now

    def _is_main_title(self, title: str) -> bool:
        title_lc = (title or "").lower()
        for token in self.rules.main_window_titles:
            if token and token.lower() in title_lc:
                return True
        return False

    def _get_cached(self, cache: Dict[WindowIdentity, Tuple[float, str]], key: WindowIdentity, loader: Callable[[], str]) -> str:
        now = time.time()
        with self._cache_lock:
            hit = cache.get(key)
            if hit:
                ts, cached_value = hit
                ttl = self.rules.cache_ttl_seconds if cached_value else self._empty_text_cache_ttl_seconds()
                if (now - ts) <= ttl:
                    return cached_value
            value = loader() or ""
            cache[key] = (now, value)
            return value

    def _empty_text_cache_ttl_seconds(self) -> float:
        active_ttl = max(self._active_poll_interval_seconds(), 0.05)
        if self._is_burst_mode_active():
            active_ttl = min(active_ttl, self._burst_scan_interval_seconds())
        return min(self.rules.cache_ttl_seconds, active_ttl)

    def _window_identity(self, hwnd: int, pid: Optional[int] = None, class_name: Optional[str] = None) -> Optional[WindowIdentity]:
        resolved_pid = pid if pid is not None else self.api.get_window_thread_process_id(hwnd)
        if resolved_pid <= 0:
            return None
        resolved_class = class_name if class_name is not None else self._get_class(hwnd)
        return (hwnd, resolved_pid, resolved_class)

    def _get_text(self, hwnd: int, pid: Optional[int] = None, class_name: Optional[str] = None) -> str:
        identity = self._window_identity(hwnd, pid, class_name)
        if identity is None:
            return self.api.get_window_text(hwnd) or ""
        return self._get_cached(self._text_cache, identity, lambda: self.api.get_window_text(hwnd))

    def _get_class(self, hwnd: int) -> str:
        return self.api.get_class_name(hwnd) or ""

    def _is_identity_alive(self, identity: WindowIdentity) -> bool:
        hwnd, pid, class_name = identity
        if not self.api.is_window(hwnd):
            return False
        if self.api.get_window_thread_process_id(hwnd) != pid:
            return False
        if self._get_class(hwnd) != class_name:
            return False
        return True

    def _maybe_cleanup_caches(self, now: Optional[float] = None, force: bool = False) -> None:
        now_value = now or time.time()
        interval = self._cache_cleanup_interval_seconds()
        with self._data_lock:
            if not force and self._last_cache_cleanup > 0 and (now_value - self._last_cache_cleanup) < interval:
                return
            self._last_cache_cleanup = now_value
        self._cleanup_caches()

    def _cleanup_caches(self) -> None:
        now = time.time()
        max_age = self.rules.cache_ttl_seconds
        with self._cache_lock:
            stale_text = [
                key
                for key, (ts, _value) in self._text_cache.items()
                if now - ts > max_age or not self._is_identity_alive(key)
            ]
            for key in stale_text:
                self._text_cache.pop(key, None)

            self._hidden_windows = {
                key: snap for key, snap in self._hidden_windows.items() if self._is_identity_alive(key)
            }
            self._custom_scroll_cache = {
                key: val for key, val in self._custom_scroll_cache.items() if self._is_identity_alive(key)
            }
            self._candidate_states = {
                key: state for key, state in self._candidate_states.items() if self._is_identity_alive(key)
            }

    def _set_error(self, message: str) -> None:
        now = time.time()
        should_log = False
        with self._error_log_lock:
            last = self._last_log.get(message, 0.0)
            if now - last >= self.rules.log_rate_limit_seconds:
                self._last_log[message] = now
                self._prune_error_log_keys_locked()
                should_log = True
        if should_log:
            self.logger.error(message)
        with self._state_lock:
            self._state.last_error = message
            self._state.last_tick = now

    def _api_last_error(self) -> int:
        try:
            return int(self.api.get_last_error())
        except Exception:
            return 0

    def _prune_error_log_keys_locked(self) -> None:
        size = len(self._last_log)
        if size <= MAX_ERROR_LOG_KEYS:
            return
        trim_count = size - ERROR_LOG_PRUNE_TARGET
        if trim_count <= 0:
            return
        oldest = sorted(self._last_log.items(), key=lambda item: item[1])[:trim_count]
        for key, _timestamp in oldest:
            self._last_log.pop(key, None)

    def _prune_error_log_keys(self) -> None:
        with self._error_log_lock:
            self._prune_error_log_keys_locked()

    def _restore_hidden_windows(
        self,
        reason: str,
        target_identities: Optional[Set[WindowIdentity]] = None,
        target_hide_reasons: Optional[Set[str]] = None,
    ) -> None:
        self._actions.restore_hidden_windows(
            reason,
            target_identities=target_identities,
            target_hide_reasons=target_hide_reasons,
        )

    def _hide_window(self, hwnd: int, pid: int, class_name: str, hide_reason: str) -> bool:
        return self._actions.hide_window(hwnd, pid, class_name, hide_reason)

    def _dismiss_popup_window(self, hwnd: int) -> tuple[int, int]:
        return self._actions.dismiss_popup_window(hwnd)

    def _remove_popup_ads(self, kakao_pids: Set[int], now: Optional[float] = None) -> tuple[int, int]:
        return self._actions.remove_popup_ads(kakao_pids, now=now)

    def dump_window_tree(self, out_dir: Optional[str] = None) -> Optional[str]:
        return self._dump.dump_window_tree(out_dir=out_dir)

    def dump_window_tree_series(
        self,
        out_dir: Optional[str] = None,
        duration_ms: int = 1000,
        interval_ms: int = 100,
    ) -> Optional[str]:
        return self._dump.dump_window_tree_series(
            out_dir=out_dir,
            duration_ms=duration_ms,
            interval_ms=interval_ms,
        )

    def _runtime_paths(self):
        return get_runtime_paths(create=True)


__all__ = ["LayoutOnlyEngine"]
