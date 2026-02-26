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
from .win32_api import SW_HIDE, SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOZORDER, WM_CLOSE, Win32API

Rect = Tuple[int, int, int, int]


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
        self._stop_event = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None
        self._apply_thread: Optional[threading.Thread] = None

        self._main_window_handles: Set[int] = set()
        self._ad_subwindow_candidates: Set[int] = set()
        self._kakao_pids: Set[int] = set()
        self._hidden_hwnds: Set[int] = set()
        self._custom_scroll_cache: Dict[int, bool] = {}

        self._text_cache: Dict[int, Tuple[float, str]] = {}
        self._class_cache: Dict[int, Tuple[float, str]] = {}
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

        self._stop_event.clear()
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._apply_thread = threading.Thread(target=self._apply_loop, daemon=True)
        self._watch_thread.start()
        self._apply_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._watch_thread and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=2.0)
        if self._apply_thread and self._apply_thread.is_alive():
            self._apply_thread.join(timeout=2.0)
        self._watch_thread = None
        self._apply_thread = None
        with self._state_lock:
            self._state.running = False

    def set_enabled(self, enabled: bool) -> None:
        self.settings.enabled = bool(enabled)
        with self._state_lock:
            self._state.enabled = bool(enabled)

    def force_scan(self) -> None:
        self.scan_once()
        self.apply_once()

    def scan_once(self) -> None:
        self._watch_once()

    def apply_once(self) -> None:
        self._apply_once()

    def _poll_interval_seconds(self) -> float:
        return max(int(self.settings.poll_interval_ms), 50) / 1000.0

    def _watch_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._watch_once()
            except Exception as e:
                self._set_error(f"watch: {e}")
            time.sleep(self._poll_interval_seconds())

    def _apply_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._apply_once()
            except Exception as e:
                self._set_error(f"apply: {e}")
            time.sleep(self._poll_interval_seconds())

    def _watch_once(self) -> None:
        pids = set(self._process_ids_provider("kakaotalk.exe"))
        windows = self._collect_windows(pids)
        main_handles: Set[int] = set()
        candidates: Set[int] = set()
        main_classes = set(self.rules.main_window_classes)

        for item in windows:
            if item.class_name not in main_classes:
                continue
            if item.parent_hwnd != 0 or not item.text:
                continue
            if item.class_name == "EVA_Window" and not self._is_main_title(item.text):
                continue
            main_handles.add(item.hwnd)

        for item in windows:
            if item.class_name not in main_classes or item.text != "":
                continue
            if item.parent_hwnd in main_handles or item.parent_hwnd == 0:
                candidates.add(item.hwnd)

        with self._data_lock:
            self._kakao_pids = pids
            self._main_window_handles = main_handles
            self._ad_subwindow_candidates = candidates

        with self._state_lock:
            self._state.kakao_pid_count = len(pids)
            self._state.main_window_count = len(main_handles)
            self._state.last_tick = time.time()

        self._cleanup_caches()

    def _apply_once(self) -> None:
        if not self.state.enabled:
            return

        with self._data_lock:
            main_handles = list(self._main_window_handles)
            candidates = list(self._ad_subwindow_candidates)
            kakao_pids = set(self._kakao_pids)

        resized = 0
        hidden = 0
        closed = 0

        for wnd in main_handles:
            if not self.api.is_window(wnd):
                continue
            pid = self.api.get_window_thread_process_id(wnd)
            if pid not in kakao_pids:
                continue
            parent_rect = self.api.get_window_rect(wnd)
            if not parent_rect:
                continue
            children = self._enum_children(wnd)
            if not self._is_main_window(children):
                continue
            for child in children:
                if not self.api.is_window(child):
                    continue
                if self.api.get_parent(child) != wnd:
                    continue
                class_name = self._get_class(child)
                window_text = self._get_text(child)
                parent_text = self._get_text(wnd)

                if class_name == self.rules.eva_child_class and window_text == "" and parent_text != "":
                    has_custom_scroll = self._custom_scroll_cache.get(wnd)
                    if has_custom_scroll is None:
                        has_custom_scroll = self._class_name_starts_with(wnd, self.rules.custom_scroll_prefix)
                        self._custom_scroll_cache[wnd] = has_custom_scroll
                    if self._layout.should_close_empty_eva_child(class_name, window_text, parent_text, has_custom_scroll):
                        self.api.send_message(child, WM_CLOSE, 0, 0)
                        closed += 1

                if self._layout.apply_view_resize(child, window_text, parent_rect):
                    resized += 1

                if not self.settings.aggressive_mode:
                    continue
                child_rect = self.api.get_window_rect(child)
                if child_rect and self._layout.should_hide_aggressive(class_name, window_text, child_rect, parent_rect):
                    if self._hide_window(child):
                        hidden += 1

        for wnd in candidates:
            if not self.api.is_window(wnd):
                continue
            pid = self.api.get_window_thread_process_id(wnd)
            if pid not in kakao_pids:
                continue
            if self._has_window_text(wnd, self.rules.chrome_legacy_title):
                if self._hide_window(wnd):
                    hidden += 1

        with self._state_lock:
            self._state.resized_windows += resized
            self._state.hidden_windows += hidden
            self._state.closed_windows += closed
            self._state.last_tick = time.time()

        self._cleanup_caches()

    def _collect_windows(self, pids: Set[int]) -> List[WindowInfo]:
        if not pids:
            return []
        result: List[WindowInfo] = []

        def cb(hwnd: int) -> bool:
            pid = self.api.get_window_thread_process_id(hwnd)
            if pid not in pids:
                return True
            result.append(
                WindowInfo(
                    hwnd=hwnd,
                    pid=pid,
                    class_name=self._get_class(hwnd),
                    text=self._get_text(hwnd),
                    parent_hwnd=self.api.get_parent(hwnd),
                    rect=self.api.get_window_rect(hwnd),
                    visible=self.api.is_window_visible(hwnd),
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
            if self._get_class(hwnd) != self.rules.eva_child_class:
                continue
            txt = self._get_text(hwnd)
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

    def _has_window_text(self, hwnd: int, target: str, max_depth: int = 8) -> bool:
        if max_depth < 0 or not self.api.is_window(hwnd):
            return False
        if self._get_text(hwnd) == target:
            return True
        for child in self._enum_children(hwnd):
            if self._has_window_text(child, target, max_depth - 1):
                return True
        return False

    def _hide_window(self, hwnd: int) -> bool:
        self.api.show_window(hwnd, SW_HIDE)
        if not self.api.is_window_visible(hwnd):
            self._hidden_hwnds.add(hwnd)
            return True
        return bool(
            self.api.set_window_pos(
                hwnd,
                -32000,
                -32000,
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
        )

    def _is_main_title(self, title: str) -> bool:
        title_lc = (title or "").lower()
        for token in self.rules.main_window_titles:
            if token and token.lower() in title_lc:
                return True
        return False

    def _get_cached(self, cache: Dict[int, Tuple[float, str]], hwnd: int, loader: Callable[[], str]) -> str:
        now = time.time()
        hit = cache.get(hwnd)
        if hit and (now - hit[0]) <= self.rules.cache_ttl_seconds:
            return hit[1]
        value = loader() or ""
        cache[hwnd] = (now, value)
        return value

    def _get_text(self, hwnd: int) -> str:
        return self._get_cached(self._text_cache, hwnd, lambda: self.api.get_window_text(hwnd))

    def _get_class(self, hwnd: int) -> str:
        return self._get_cached(self._class_cache, hwnd, lambda: self.api.get_class_name(hwnd))

    def _cleanup_caches(self) -> None:
        now = time.time()
        max_age = self.rules.cache_ttl_seconds
        for cache in (self._text_cache, self._class_cache):
            stale = [hwnd for hwnd, (ts, _value) in cache.items() if now - ts > max_age or not self.api.is_window(hwnd)]
            for hwnd in stale:
                cache.pop(hwnd, None)

        self._hidden_hwnds = {hwnd for hwnd in self._hidden_hwnds if self.api.is_window(hwnd)}
        self._custom_scroll_cache = {hwnd: val for hwnd, val in self._custom_scroll_cache.items() if self.api.is_window(hwnd)}

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

        roots = self._collect_windows(pids)
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
        node: Dict[str, object] = {
            "hwnd": hwnd,
            "class": self._get_class(hwnd),
            "text": self._get_text(hwnd),
            "pid": self.api.get_window_thread_process_id(hwnd),
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


__all__ = ["LayoutOnlyEngine", "EngineState", "WindowInfo"]
