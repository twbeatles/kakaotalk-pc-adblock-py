from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Set, Tuple, cast

from ..protocols import Rect, WindowIdentity
from .models import AdDecision, CandidateState

if TYPE_CHECKING:
    from .controller import LayoutOnlyEngine


class WindowDumpBuilder:
    def __init__(self, engine: "LayoutOnlyEngine") -> None:
        self.engine = engine

    def dump_window_tree(self, out_dir: str | None = None) -> str | None:
        pids = set(self.engine._process_ids_provider("kakaotalk.exe"))
        if not pids:
            return None

        data = self.build_window_dump_payload(pids)
        if not data["windows"]:
            return None
        dump_dir = out_dir or self.engine._runtime_paths().appdata_dir
        os.makedirs(dump_dir, exist_ok=True)
        path = os.path.join(dump_dir, f"window_dump_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def dump_window_tree_series(
        self,
        out_dir: str | None = None,
        duration_ms: int = 1000,
        interval_ms: int = 100,
    ) -> str | None:
        pids = set(self.engine._process_ids_provider("kakaotalk.exe"))
        if not pids:
            return None

        duration_seconds = max(int(duration_ms), 0) / 1000.0
        interval_seconds = max(int(interval_ms), 10) / 1000.0
        deadline = time.time() + duration_seconds
        frames: List[Dict[str, object]] = []
        preview_states: Dict[WindowIdentity, CandidateState] = {}

        while True:
            pids = set(self.engine._process_ids_provider("kakaotalk.exe"))
            if not pids:
                break
            frame_time = datetime.now().isoformat()
            frame_payload = self.build_window_dump_payload(pids)
            frame_payload["timestamp"] = frame_time
            frame_payload["candidates"] = self.inspect_candidates_for_dump(pids, preview_states, time.time())
            frames.append(frame_payload)
            if time.time() >= deadline:
                break
            sleep_seconds = min(interval_seconds, max(deadline - time.time(), 0.0))
            if sleep_seconds <= 0:
                break
            time.sleep(sleep_seconds)

        if not frames:
            return None

        data = {
            "timestamp": datetime.now().isoformat(),
            "duration_ms": max(int(duration_ms), 0),
            "interval_ms": max(int(interval_ms), 10),
            "frames": frames,
        }
        dump_dir = out_dir or self.engine._runtime_paths().appdata_dir
        os.makedirs(dump_dir, exist_ok=True)
        path = os.path.join(dump_dir, f"window_dump_series_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def build_window_dump_payload(self, pids: Set[int]) -> Dict[str, object]:
        roots = self.engine._scanner.collect_windows(pids, include_geometry=True)
        roots = [w for w in roots if w.parent_hwnd == 0]
        return {
            "timestamp": datetime.now().isoformat(),
            "pids": sorted(pids),
            "windows": [self.dump_node(root.hwnd, 0, 6) for root in roots],
        }

    def inspect_candidates_for_dump(
        self,
        pids: Set[int],
        preview_states: Dict[WindowIdentity, CandidateState],
        now: float,
    ) -> List[Dict[str, object]]:
        windows = self.engine._scanner.collect_windows(pids) if pids else []
        main_handles: Set[int] = set()
        candidates: Set[int] = set()
        legacy_text_memo: Dict[Tuple[int, str, int], bool] = {}
        legacy_contains_memo: Dict[Tuple[int, str, int], bool] = {}
        ad_token_memo: Dict[Tuple[int, int], bool] = {}
        payloads: List[Dict[str, object]] = []

        for item in windows:
            if not self.engine._scanner.is_main_window_candidate(item):
                continue
            if self.engine._scanner.is_confirmed_main_window(item.hwnd, item=item):
                main_handles.add(item.hwnd)

        for item in windows:
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

        for wnd in main_handles:
            if not self.engine.api.is_window(wnd):
                continue
            pid = self.engine.api.get_window_thread_process_id(wnd)
            if pid not in pids:
                continue
            parent_rect = self.engine.api.get_window_rect(wnd)
            if not parent_rect or not self.engine._scanner.is_confirmed_main_window(wnd):
                continue
            parent_class_name = self.engine._get_class(wnd)
            children = self.engine._scanner.enum_children(wnd)
            parent_text = self.engine._get_text(wnd, pid, parent_class_name)
            main_window_has_ad_signal = False
            child_contexts: List[Tuple[int, WindowIdentity, str, str, Rect | None, AdDecision]] = []

            for child in children:
                if not self.engine.api.is_window(child) or self.engine.api.get_parent(child) != wnd:
                    continue
                class_name = self.engine._get_class(child)
                window_text = self.engine._get_text(child, pid, class_name)
                child_rect: Rect | None = None
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
                if class_name == self.engine.rules.eva_child_class and window_text == "" and parent_text != "":
                    has_custom_scroll = self.engine._signals.class_name_starts_with(
                        wnd,
                        self.engine.rules.custom_scroll_prefix,
                    )
                    close_decision = self.engine._signals.empty_eva_close_decision(
                        class_name,
                        window_text,
                        parent_text,
                        has_custom_scroll,
                        main_window_has_ad_signal,
                    )
                    if close_decision.matched or identity in preview_states or self.engine._signals.has_relevant_signal(close_decision):
                        close_state, close_confirmed = self.engine._signals.update_candidate_state_store(
                            preview_states,
                            identity,
                            close_decision,
                            now,
                        )
                        payloads.append(
                            self.engine._signals.candidate_payload(
                                identity,
                                close_decision,
                                close_state,
                                confirmed=close_confirmed,
                            )
                        )

                if not self.engine.settings.aggressive_mode or child_rect is None:
                    continue
                if aggressive_decision.matched or identity in preview_states or self.engine._signals.has_relevant_signal(aggressive_decision):
                    aggressive_state, aggressive_confirmed = self.engine._signals.update_candidate_state_store(
                        preview_states,
                        identity,
                        aggressive_decision,
                        now,
                    )
                    payloads.append(
                        self.engine._signals.candidate_payload(
                            identity,
                            aggressive_decision,
                            aggressive_state,
                            confirmed=aggressive_confirmed,
                        )
                    )

        for wnd in candidates:
            if not self.engine.api.is_window(wnd):
                continue
            pid = self.engine.api.get_window_thread_process_id(wnd)
            if pid not in pids:
                continue
            class_name = self.engine._get_class(wnd)
            identity = (wnd, pid, class_name)
            legacy_kind = self.engine._signals.legacy_signature_kind(
                wnd,
                memo_exact=legacy_text_memo,
                memo_contains=legacy_contains_memo,
            )
            legacy_decision = self.engine._signals.legacy_hide_decision(legacy_kind)
            if legacy_decision.matched or identity in preview_states or self.engine._signals.has_relevant_signal(legacy_decision):
                legacy_state, legacy_confirmed = self.engine._signals.update_candidate_state_store(
                    preview_states,
                    identity,
                    legacy_decision,
                    now,
                )
                payloads.append(
                    self.engine._signals.candidate_payload(
                        identity,
                        legacy_decision,
                        legacy_state,
                        confirmed=legacy_confirmed,
                    )
                )

        for item in windows:
            if item.parent_hwnd != 0:
                continue
            if self.engine._scanner.is_confirmed_main_window(item.hwnd, item=item):
                continue
            if not self.engine.api.is_window_visible(item.hwnd):
                continue
            popup_guard = self.engine._signals.popup_host_guard_status(item.text)
            for child in self.engine._scanner.enum_children(item.hwnd):
                if not self.engine.api.is_window(child):
                    continue
                if self.engine.api.get_parent(child) != item.hwnd:
                    continue
                if not self.engine.api.is_window_visible(child):
                    continue
                class_name = self.engine._get_class(child)
                if class_name not in self.engine._popup_ad_class_set:
                    continue
                identity = (child, self.engine.api.get_window_thread_process_id(child), class_name)
                popup_signals = self.engine._signals.blank_signals()
                popup_signals["popup_direct_class"] = True
                popup_signals["popup_host_guard"] = popup_guard
                popup_decision = (
                    self.engine._signals.decision_dismiss_popup(popup_signals)
                    if popup_guard == "allow"
                    else self.engine._signals.decision_none(popup_signals)
                )
                popup_state, popup_confirmed = self.engine._signals.update_candidate_state_store(
                    preview_states,
                    identity,
                    popup_decision,
                    now,
                )
                payloads.append(
                    self.engine._signals.candidate_payload(identity, popup_decision, popup_state, confirmed=popup_confirmed)
                )

        payloads.sort(
            key=lambda item: (
                cast(int, item["hwnd"]),
                cast(str, item["action"]),
                cast(str, item["decision"]),
            )
        )
        return payloads

    def dump_node(self, hwnd: int, depth: int, max_depth: int) -> Dict[str, object]:
        class_name = self.engine._get_class(hwnd)
        pid = self.engine.api.get_window_thread_process_id(hwnd)
        node: Dict[str, object] = {
            "hwnd": hwnd,
            "class": class_name,
            "text": self.engine._get_text(hwnd, pid, class_name),
            "pid": pid,
            "visible": self.engine.api.is_window_visible(hwnd),
            "rect": self.engine.api.get_window_rect(hwnd),
            "depth": depth,
            "children": [],
        }
        if depth >= max_depth:
            return node
        children = self.engine._scanner.enum_children(hwnd)
        node["children"] = [self.dump_node(child, depth + 1, max_depth) for child in children]
        return node
