from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set, Tuple

from .config import APPDATA_DIR, LayoutRulesV11, LayoutSettingsV11
from .layout_engine import LayoutEngine
from .services import ProcessInspector
from .win32_api import SW_HIDE, SW_SHOW, SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOZORDER, WM_CLOSE, Win32API

Rect = Tuple[int, int, int, int]
WindowIdentity = Tuple[int, int, str]


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
    main_window_count: int = 0
    resized_windows: int = 0
    hidden_windows: int = 0
    closed_windows: int = 0
    last_tick: float = 0.0
    last_error: str = ""


@dataclass
class HiddenWindowSnapshot:
    was_visible: bool
    rect: Optional[Rect]
    pid: int
    class_name: str


class LayoutOnlyEngine:
    def __init__(
        self,
        logger: logging.Logger,
        settings: LayoutSettingsV11,
        rules: LayoutRulesV11,
        api: Optional[Win32API] = None,
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
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None

        self._main_window_class_set = frozenset(self.rules.main_window_classes)
        self._ad_candidate_class_set = frozenset(self.rules.ad_candidate_classes)
        self._main_window_handles: Set[int] = set()
        self._ad_subwindow_candidates: Set[int] = set()
        self._kakao_pids: Set[int] = set()
        self._pid_scan_cache: Set[int] = set()
        self._last_pid_scan: float = 0.0
        self._last_cache_cleanup: float = 0.0
        self._last_activity: float = 0.0
        self._hidden_windows: Dict[WindowIdentity, HiddenWindowSnapshot] = {}
        self._custom_scroll_cache: Dict[WindowIdentity, bool] = {}

        self._text_cache: Dict[WindowIdentity, Tuple[float, str]] = {}
        self._last_log: Dict[str, float] = {}

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
        with self._data_lock:
            self._pid_scan_cache = set()
            self._last_pid_scan = 0.0
            self._last_cache_cleanup = 0.0
            self._last_activity = 0.0

        self._stop_event.clear()
        self._wake_event.clear()
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._watch_thread and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=2.0)
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
        if enabled_value:
            self._wake_event.set()

    def report_warning(self, message: str) -> None:
        if not message:
            return
        now = time.time()
        with self._state_lock:
            self._state.last_error = message
            self._state.last_tick = now

    def force_scan(self) -> None:
        self.scan_once()
        self.apply_once()

    def scan_once(self) -> None:
        self._watch_once()

    def apply_once(self) -> None:
        self._apply_once()

    def _active_poll_interval_seconds(self) -> float:
        return max(int(self.settings.poll_interval_ms), 50) / 1000.0

    def _idle_poll_interval_seconds(self) -> float:
        return max(int(self.settings.idle_poll_interval_ms), 200) / 1000.0

    def _pid_scan_interval_seconds(self) -> float:
        return max(int(self.settings.pid_scan_interval_ms), 100) / 1000.0

    def _cache_cleanup_interval_seconds(self) -> float:
        return max(int(self.settings.cache_cleanup_interval_ms), 250) / 1000.0

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

    def _get_kakao_pids(self, now: float) -> Set[int]:
        scan_interval = self._pid_scan_interval_seconds()
        with self._data_lock:
            use_cached = self._last_pid_scan > 0 and (now - self._last_pid_scan) < scan_interval
            if use_cached:
                return set(self._pid_scan_cache)

        pids = set(self._process_ids_provider("kakaotalk.exe"))
        with self._data_lock:
            self._pid_scan_cache = set(pids)
            self._last_pid_scan = now
        return pids

    def _maybe_cleanup_caches(self, now: Optional[float] = None, force: bool = False) -> None:
        now_value = now or time.time()
        interval = self._cache_cleanup_interval_seconds()
        with self._data_lock:
            if not force and self._last_cache_cleanup > 0 and (now_value - self._last_cache_cleanup) < interval:
                return
            self._last_cache_cleanup = now_value
        self._cleanup_caches()

    def _watch_loop(self) -> None:
        # v11 keeps a single watch+apply loop to minimize race windows.
        while not self._stop_event.is_set():
            try:
                self._watch_once()
            except Exception as e:
                self._set_error(f"watch: {e}")
            else:
                try:
                    self._apply_once()
                except Exception as e:
                    self._set_error(f"apply: {e}")
            self._wait_next_tick(self._current_loop_interval_seconds())

    def _watch_once(self) -> None:
        now = time.time()
        was_active = self._is_active_mode(now)
        pids = self._get_kakao_pids(now)
        windows = self._collect_windows(pids) if pids else []
        main_handles: Set[int] = set()
        candidates: Set[int] = set()
        legacy_text_memo: Dict[Tuple[int, str, int], bool] = {}

        for item in windows:
            if item.class_name not in self._main_window_class_set:
                continue
            if item.parent_hwnd != 0 or not item.text:
                continue
            if item.class_name == "EVA_Window" and not self._is_main_title(item.text):
                continue
            main_handles.add(item.hwnd)

        for item in windows:
            if item.class_name not in self._ad_candidate_class_set or item.text != "":
                continue
            if item.parent_hwnd in main_handles:
                candidates.add(item.hwnd)
                continue
            if item.parent_hwnd == 0 and self._has_window_text(
                item.hwnd,
                self.rules.chrome_legacy_title,
                memo=legacy_text_memo,
            ):
                candidates.add(item.hwnd)

        with self._data_lock:
            self._kakao_pids = pids
            self._main_window_handles = main_handles
            self._ad_subwindow_candidates = candidates

        if pids:
            self._mark_activity(now, wake=not was_active)

        with self._state_lock:
            self._state.kakao_pid_count = len(pids)
            self._state.main_window_count = len(main_handles)
            self._state.last_tick = now

        self._maybe_cleanup_caches(now)

    def _apply_once(self) -> None:
        if not self._is_enabled():
            return

        with self._data_lock:
            main_handles = list(self._main_window_handles)
            candidates = list(self._ad_subwindow_candidates)
            kakao_pids = set(self._kakao_pids)

        resized = 0
        hidden = 0
        closed = 0
        now = time.time()
        legacy_text_memo: Dict[Tuple[int, str, int], bool] = {}

        for wnd in main_handles:
            if not self.api.is_window(wnd):
                continue
            pid = self.api.get_window_thread_process_id(wnd)
            if pid not in kakao_pids:
                continue
            parent_rect = self.api.get_window_rect(wnd)
            if not parent_rect:
                continue
            parent_class_name = self._get_class(wnd)
            parent_identity = (wnd, pid, parent_class_name)

            children = self._enum_children(wnd)
            if not self._is_main_window(children):
                continue
            parent_text = self._get_text(wnd, pid, parent_class_name)

            for child in children:
                if not self.api.is_window(child):
                    continue
                if self.api.get_parent(child) != wnd:
                    continue
                class_name = self._get_class(child)
                window_text = self._get_text(child, pid, class_name)

                if class_name == self.rules.eva_child_class and window_text == "" and parent_text != "":
                    with self._cache_lock:
                        has_custom_scroll = self._custom_scroll_cache.get(parent_identity)
                    if has_custom_scroll is None:
                        has_custom_scroll = self._class_name_starts_with(wnd, self.rules.custom_scroll_prefix)
                        with self._cache_lock:
                            self._custom_scroll_cache[parent_identity] = has_custom_scroll
                    if self._layout.should_close_empty_eva_child(class_name, window_text, parent_text, has_custom_scroll):
                        self.api.send_message(child, WM_CLOSE, 0, 0)
                        closed += 1

                if self._layout.apply_view_resize(child, window_text, parent_rect):
                    resized += 1

                if not self.settings.aggressive_mode:
                    continue
                child_rect = self.api.get_window_rect(child)
                if child_rect and self._layout.should_hide_aggressive(class_name, window_text, child_rect, parent_rect):
                    if self._hide_window(child, pid, class_name):
                        hidden += 1

        for wnd in candidates:
            if not self.api.is_window(wnd):
                continue
            pid = self.api.get_window_thread_process_id(wnd)
            if pid not in kakao_pids:
                continue
            class_name = self._get_class(wnd)
            if self._has_window_text(wnd, self.rules.chrome_legacy_title, memo=legacy_text_memo):
                if self._hide_window(wnd, pid, class_name):
                    hidden += 1

        with self._state_lock:
            self._state.resized_windows += resized
            self._state.hidden_windows += hidden
            self._state.closed_windows += closed
            self._state.last_tick = now

        self._maybe_cleanup_caches(now)

    def _collect_windows(self, pids: Set[int], include_geometry: bool = False) -> List[WindowInfo]:
        if not pids:
            return []
        result: List[WindowInfo] = []

        def cb(hwnd: int) -> bool:
            pid = self.api.get_window_thread_process_id(hwnd)
            if pid not in pids:
                return True
            class_name = self._get_class(hwnd)
            result.append(
                WindowInfo(
                    hwnd=hwnd,
                    pid=pid,
                    class_name=class_name,
                    text=self._get_text(hwnd, pid, class_name),
                    parent_hwnd=self.api.get_parent(hwnd),
                    rect=self.api.get_window_rect(hwnd) if include_geometry else None,
                    visible=bool(self.api.is_window_visible(hwnd)) if include_geometry else False,
                )
            )
            return True

        self.api.enum_windows(cb)
        return result

    def _enum_children(self, parent_hwnd: int) -> List[int]:
        children: List[int] = []
        self.api.enum_child_windows(parent_hwnd, lambda hwnd: children.append(hwnd) or True)
        return children

    def _is_main_window(self, child_handles: List[int]) -> bool:
        for hwnd in child_handles:
            class_name = self._get_class(hwnd)
            if class_name != self.rules.eva_child_class:
                continue
            pid = self.api.get_window_thread_process_id(hwnd)
            txt = self._get_text(hwnd, pid, class_name)
            if txt.startswith(self.rules.main_view_prefix) or txt.startswith(self.rules.lock_view_prefix):
                return True
        return False

    def _class_name_starts_with(self, hwnd: int, prefix: str, max_depth: int = 8) -> bool:
        if max_depth < 0 or not self.api.is_window(hwnd):
            return False
        if self._get_class(hwnd).startswith(prefix):
            return True
        for child in self._enum_children(hwnd):
            if self._class_name_starts_with(child, prefix, max_depth - 1):
                return True
        return False

    def _has_window_text(
        self,
        hwnd: int,
        target: str,
        max_depth: int = 8,
        memo: Optional[Dict[Tuple[int, str, int], bool]] = None,
    ) -> bool:
        cache_key = (hwnd, target, max_depth)
        if memo is not None and cache_key in memo:
            return memo[cache_key]
        if max_depth < 0 or not self.api.is_window(hwnd):
            if memo is not None:
                memo[cache_key] = False
            return False

        pid = self.api.get_window_thread_process_id(hwnd)
        class_name = self._get_class(hwnd)
        if self._get_text(hwnd, pid, class_name) == target:
            if memo is not None:
                memo[cache_key] = True
            return True

        for child in self._enum_children(hwnd):
            if self._has_window_text(child, target, max_depth - 1, memo=memo):
                if memo is not None:
                    memo[cache_key] = True
                return True

        if memo is not None:
            memo[cache_key] = False
        return False

    def _hide_window(self, hwnd: int, pid: int, class_name: str) -> bool:
        if pid <= 0 or not self.api.is_window(hwnd):
            return False
        identity = (hwnd, pid, class_name)
        with self._cache_lock:
            if identity not in self._hidden_windows:
                self._hidden_windows[identity] = HiddenWindowSnapshot(
                    was_visible=bool(self.api.is_window_visible(hwnd)),
                    rect=self.api.get_window_rect(hwnd),
                    pid=pid,
                    class_name=class_name,
                )

        self.api.show_window(hwnd, SW_HIDE)
        if not self.api.is_window_visible(hwnd):
            return True

        moved = bool(
            self.api.set_window_pos(
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

        with self._cache_lock:
            self._hidden_windows.pop(identity, None)
        return False

    def _restore_hidden_windows(self, reason: str) -> None:
        with self._cache_lock:
            snapshots = list(self._hidden_windows.items())
            self._hidden_windows.clear()
        if not snapshots:
            return

        for identity, snap in snapshots:
            hwnd, expected_pid, expected_class = identity
            if not self.api.is_window(hwnd):
                continue

            current_pid = self.api.get_window_thread_process_id(hwnd)
            current_class = self._get_class(hwnd)
            if current_pid != expected_pid or current_class != expected_class:
                self.logger.debug(
                    "Skip restore for recycled hwnd=%s reason=%s expected=(%s,%s) current=(%s,%s)",
                    hwnd,
                    reason,
                    expected_pid,
                    expected_class,
                    current_pid,
                    current_class,
                )
                continue

            restored = True
            if snap.rect:
                left, top, right, bottom = snap.rect
                width = right - left
                height = bottom - top
                if width > 0 and height > 0:
                    if not self.api.set_window_pos(
                        hwnd,
                        left,
                        top,
                        width,
                        height,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    ):
                        restored = False
                else:
                    restored = False

            if snap.was_visible:
                self.api.show_window(hwnd, SW_SHOW)
                if not self.api.is_window_visible(hwnd):
                    restored = False

            if not restored:
                self.logger.warning("Failed to restore hidden window hwnd=%s reason=%s", hwnd, reason)

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
            if hit and (now - hit[0]) <= self.rules.cache_ttl_seconds:
                return hit[1]
            value = loader() or ""
            cache[key] = (now, value)
            return value

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

    def _set_error(self, message: str) -> None:
        now = time.time()
        last = self._last_log.get(message, 0.0)
        if now - last >= self.rules.log_rate_limit_seconds:
            self._last_log[message] = now
            self.logger.error(message)
        with self._state_lock:
            self._state.last_error = message
            self._state.last_tick = now

    def dump_window_tree(self, out_dir: Optional[str] = None) -> Optional[str]:
        pids = set(self._process_ids_provider("kakaotalk.exe"))
        if not pids:
            return None

        roots = self._collect_windows(pids, include_geometry=True)
        roots = [w for w in roots if w.parent_hwnd == 0]
        if not roots:
            return None

        data = {
            "timestamp": datetime.now().isoformat(),
            "pids": sorted(pids),
            "windows": [self._dump_node(root.hwnd, 0, 6) for root in roots],
        }
        dump_dir = out_dir or APPDATA_DIR
        os.makedirs(dump_dir, exist_ok=True)
        path = os.path.join(dump_dir, f"window_dump_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def _dump_node(self, hwnd: int, depth: int, max_depth: int) -> Dict[str, object]:
        class_name = self._get_class(hwnd)
        pid = self.api.get_window_thread_process_id(hwnd)
        node: Dict[str, object] = {
            "hwnd": hwnd,
            "class": class_name,
            "text": self._get_text(hwnd, pid, class_name),
            "pid": pid,
            "visible": self.api.is_window_visible(hwnd),
            "rect": self.api.get_window_rect(hwnd),
            "depth": depth,
            "children": [],
        }
        if depth >= max_depth:
            return node
        children = self._enum_children(hwnd)
        node["children"] = [self._dump_node(child, depth + 1, max_depth) for child in children]
        return node


__all__ = ["LayoutOnlyEngine", "EngineState", "WindowInfo", "HiddenWindowSnapshot", "WindowIdentity"]
