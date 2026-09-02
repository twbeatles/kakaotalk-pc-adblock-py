from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, cast


def _config_module():
    import kakao_adblocker.config as config_module

    return config_module


@dataclass
class LayoutSettingsV11:
    enabled: bool = True
    run_on_startup: bool = False
    start_minimized: bool = True
    poll_interval_ms: int = 50
    idle_poll_interval_ms: int = 200
    pid_scan_interval_ms: int = 200
    cache_cleanup_interval_ms: int = 1000
    burst_scan_iterations: int = 3
    burst_scan_interval_ms: int = 20
    aggressive_mode: bool = True
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: str | None = None) -> "LayoutSettingsV11":
        config_module = _config_module()
        resolved_path = path or config_module.get_runtime_paths().settings_file
        defaults = cls()
        label = "layout_settings_v11.json"
        config_module._cleanup_broken_backups(resolved_path, label)
        raw = config_module._load_json_object(resolved_path, label, default_text=defaults.default_json())
        if raw is None:
            return defaults
        return cls(
            enabled=config_module._coerce_bool(raw.get("enabled"), defaults.enabled),
            run_on_startup=config_module._coerce_bool(raw.get("run_on_startup"), defaults.run_on_startup),
            start_minimized=config_module._coerce_bool(raw.get("start_minimized"), defaults.start_minimized),
            poll_interval_ms=config_module._coerce_int(
                raw.get("poll_interval_ms"),
                defaults.poll_interval_ms,
                minimum=50,
                maximum=5000,
            ),
            idle_poll_interval_ms=config_module._coerce_int(
                raw.get("idle_poll_interval_ms"),
                defaults.idle_poll_interval_ms,
                minimum=200,
                maximum=5000,
            ),
            pid_scan_interval_ms=config_module._coerce_int(
                raw.get("pid_scan_interval_ms"),
                defaults.pid_scan_interval_ms,
                minimum=100,
                maximum=5000,
            ),
            cache_cleanup_interval_ms=config_module._coerce_int(
                raw.get("cache_cleanup_interval_ms"),
                defaults.cache_cleanup_interval_ms,
                minimum=250,
                maximum=10000,
            ),
            burst_scan_iterations=config_module._coerce_int(
                raw.get("burst_scan_iterations"),
                defaults.burst_scan_iterations,
                minimum=0,
                maximum=20,
            ),
            burst_scan_interval_ms=config_module._coerce_int(
                raw.get("burst_scan_interval_ms"),
                defaults.burst_scan_interval_ms,
                minimum=10,
                maximum=1000,
            ),
            aggressive_mode=config_module._coerce_bool(raw.get("aggressive_mode"), defaults.aggressive_mode),
            log_level=config_module._coerce_str(raw.get("log_level"), defaults.log_level).upper(),
        )

    def save(self, path: str | None = None) -> None:
        config_module = _config_module()
        payload = json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"
        config_module._atomic_write_text(path or config_module.get_runtime_paths().settings_file, payload)

    @classmethod
    def default_json(cls) -> str:
        return json.dumps(asdict(cls()), indent=2, ensure_ascii=False)


@dataclass
class LayoutRulesV11:
    main_window_classes: List[str] = field(default_factory=lambda: ["EVA_Window_Dblclk", "EVA_Window"])
    ad_candidate_classes: List[str] = field(default_factory=lambda: ["EVA_Window_Dblclk", "EVA_Window"])
    main_window_titles: List[str] = field(default_factory=lambda: ["카카오톡", "KakaoTalk"])
    main_view_prefix: str = "OnlineMainView"
    lock_view_prefix: str = "LockModeView"
    eva_child_class: str = "EVA_ChildWindow"
    custom_scroll_prefix: str = "_EVA_"
    chrome_legacy_title: str = "Chrome Legacy Window"
    chrome_legacy_title_contains: List[str] = field(default_factory=lambda: ["Chrome Legacy Window"])
    chrome_widget_prefixes: List[str] = field(default_factory=lambda: ["Chrome_WidgetWin_"])
    popup_ad_classes: List[str] = field(default_factory=lambda: ["AdFitWebView"])
    popup_search_depth: int = 2
    popup_host_text_contains: List[str] = field(default_factory=list)
    popup_host_require_empty_text: bool = True
    aggressive_ad_tokens: List[str] = field(default_factory=lambda: ["Ad", "AdFit", "Advertisement", "광고"])
    banner_min_height_px: int = 40
    banner_max_height_px: int = 260
    banner_min_width_ratio: float = 0.75
    banner_bottom_margin_px: int = 40
    hide_bottom_banner_without_token: bool = False
    close_empty_eva_child_requires_ad_signal: bool = True
    layout_shadow_padding_px: int = 2
    main_view_padding_px: int = 31
    weak_signal_confirm_ticks: int = 2
    hidden_restore_grace_ms: int = 250
    cache_ttl_seconds: float = 8.0
    log_rate_limit_seconds: float = 8.0

    @property
    def aggressive_ad_tokens_lc(self) -> List[str]:
        return [t.lower() for t in self.aggressive_ad_tokens]

    @classmethod
    def load(cls, path: str | None = None) -> "LayoutRulesV11":
        config_module = _config_module()
        resolved_path = path or config_module.get_runtime_paths().rules_file
        defaults = cls()
        label = "layout_rules_v11.json"
        config_module._cleanup_broken_backups(resolved_path, label)
        raw = config_module._load_json_object(resolved_path, label, default_text=defaults.default_json())
        if raw is None:
            config_module._warn_if_rules_text_corrupted(defaults, label)
            return defaults
        main_window_classes = config_module._coerce_str_list(raw.get("main_window_classes"), defaults.main_window_classes)
        raw_ad_candidate_classes = raw.get("ad_candidate_classes")
        if isinstance(raw_ad_candidate_classes, list):
            ad_candidate_classes = config_module._coerce_str_list(raw_ad_candidate_classes, main_window_classes)
        else:
            ad_candidate_classes = list(main_window_classes)

        banner_min_height_px = config_module._coerce_int(
            raw.get("banner_min_height_px"),
            defaults.banner_min_height_px,
            minimum=1,
        )
        banner_max_height_px = config_module._coerce_int(
            raw.get("banner_max_height_px"),
            defaults.banner_max_height_px,
            minimum=1,
        )
        if banner_min_height_px > banner_max_height_px:
            banner_min_height_px, banner_max_height_px = banner_max_height_px, banner_min_height_px
            config_module._push_load_warning(
                "layout_rules_v11.json banner 높이 범위(min/max)가 역전되어 자동 교정했습니다."
            )

        rules = cls(
            main_window_classes=main_window_classes,
            ad_candidate_classes=ad_candidate_classes,
            main_window_titles=config_module._coerce_str_list(raw.get("main_window_titles"), defaults.main_window_titles),
            main_view_prefix=config_module._coerce_str(raw.get("main_view_prefix"), defaults.main_view_prefix),
            lock_view_prefix=config_module._coerce_str(raw.get("lock_view_prefix"), defaults.lock_view_prefix),
            eva_child_class=config_module._coerce_str(raw.get("eva_child_class"), defaults.eva_child_class),
            custom_scroll_prefix=config_module._coerce_str(raw.get("custom_scroll_prefix"), defaults.custom_scroll_prefix),
            chrome_legacy_title=config_module._coerce_str(raw.get("chrome_legacy_title"), defaults.chrome_legacy_title),
            chrome_legacy_title_contains=config_module._coerce_str_list(
                raw.get("chrome_legacy_title_contains"),
                defaults.chrome_legacy_title_contains,
            ),
            chrome_widget_prefixes=config_module._coerce_str_list(
                raw.get("chrome_widget_prefixes"),
                defaults.chrome_widget_prefixes,
            ),
            popup_ad_classes=config_module._coerce_str_list(raw.get("popup_ad_classes"), defaults.popup_ad_classes),
            popup_search_depth=config_module._coerce_int(
                raw.get("popup_search_depth"),
                defaults.popup_search_depth,
                minimum=1,
                maximum=2,
            ),
            popup_host_text_contains=config_module._coerce_str_list(
                raw.get("popup_host_text_contains"),
                defaults.popup_host_text_contains,
            ),
            popup_host_require_empty_text=config_module._coerce_bool(
                raw.get("popup_host_require_empty_text"),
                defaults.popup_host_require_empty_text,
            ),
            aggressive_ad_tokens=config_module._coerce_str_list(
                raw.get("aggressive_ad_tokens"),
                defaults.aggressive_ad_tokens,
            ),
            banner_min_height_px=banner_min_height_px,
            banner_max_height_px=banner_max_height_px,
            banner_min_width_ratio=config_module._coerce_float(
                raw.get("banner_min_width_ratio"),
                defaults.banner_min_width_ratio,
                minimum=0.1,
                maximum=1.0,
            ),
            banner_bottom_margin_px=config_module._coerce_int(
                raw.get("banner_bottom_margin_px"),
                defaults.banner_bottom_margin_px,
                minimum=0,
            ),
            hide_bottom_banner_without_token=config_module._coerce_bool(
                raw.get("hide_bottom_banner_without_token"),
                defaults.hide_bottom_banner_without_token,
            ),
            close_empty_eva_child_requires_ad_signal=config_module._coerce_bool(
                raw.get("close_empty_eva_child_requires_ad_signal"),
                defaults.close_empty_eva_child_requires_ad_signal,
            ),
            layout_shadow_padding_px=config_module._coerce_int(
                raw.get("layout_shadow_padding_px"),
                defaults.layout_shadow_padding_px,
                minimum=0,
            ),
            main_view_padding_px=config_module._coerce_int(
                raw.get("main_view_padding_px"),
                defaults.main_view_padding_px,
                minimum=0,
            ),
            weak_signal_confirm_ticks=config_module._coerce_int(
                raw.get("weak_signal_confirm_ticks"),
                defaults.weak_signal_confirm_ticks,
                minimum=1,
                maximum=10,
            ),
            hidden_restore_grace_ms=config_module._coerce_int(
                raw.get("hidden_restore_grace_ms"),
                defaults.hidden_restore_grace_ms,
                minimum=0,
                maximum=5000,
            ),
            cache_ttl_seconds=config_module._coerce_float(
                raw.get("cache_ttl_seconds"),
                defaults.cache_ttl_seconds,
                minimum=0.1,
            ),
            log_rate_limit_seconds=config_module._coerce_float(
                raw.get("log_rate_limit_seconds"),
                defaults.log_rate_limit_seconds,
                minimum=0.1,
            ),
        )
        config_module._warn_if_rules_text_corrupted(rules, "layout_rules_v11.json")
        return rules

    def save(self, path: str | None = None) -> None:
        config_module = _config_module()
        payload = json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"
        config_module._atomic_write_text(path or config_module.get_runtime_paths().rules_file, payload)

    @classmethod
    def default_json(cls) -> str:
        return json.dumps(asdict(cls()), indent=2, ensure_ascii=False)
