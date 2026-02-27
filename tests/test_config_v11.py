import json
from pathlib import Path

from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11, consume_load_warnings


def test_settings_load_with_type_coercion(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text(
        json.dumps(
            {
                "enabled": "yes",
                "run_on_startup": 1,
                "start_minimized": False,
                "poll_interval_ms": "oops",
                "idle_poll_interval_ms": "bad",
                "pid_scan_interval_ms": "bad",
                "cache_cleanup_interval_ms": "bad",
                "aggressive_mode": True,
                "log_level": 100,
            }
        ),
        encoding="utf-8",
    )

    cfg = LayoutSettingsV11.load(str(path))
    assert cfg.enabled is True
    assert cfg.run_on_startup is False
    assert cfg.start_minimized is False
    assert cfg.poll_interval_ms == 50
    assert cfg.idle_poll_interval_ms == 200
    assert cfg.pid_scan_interval_ms == 200
    assert cfg.cache_cleanup_interval_ms == 1000
    assert cfg.aggressive_mode is True
    assert cfg.log_level == "INFO"


def test_settings_load_with_perf_bounds(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text(
        json.dumps(
            {
                "idle_poll_interval_ms": 1,
                "pid_scan_interval_ms": 99999,
                "cache_cleanup_interval_ms": 10,
            }
        ),
        encoding="utf-8",
    )

    cfg = LayoutSettingsV11.load(str(path))
    assert cfg.idle_poll_interval_ms == 200
    assert cfg.pid_scan_interval_ms == 5000
    assert cfg.cache_cleanup_interval_ms == 250


def test_rules_load_with_bounds(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "main_window_classes": ["EVA_Window_Dblclk"],
                "main_window_titles": ["카카오톡"],
                "banner_min_height_px": -1,
                "banner_max_height_px": 0,
                "banner_min_width_ratio": 99,
                "cache_ttl_seconds": 0,
            }
        ),
        encoding="utf-8",
    )
    rules = LayoutRulesV11.load(str(path))
    assert rules.main_window_classes == ["EVA_Window_Dblclk"]
    assert rules.ad_candidate_classes == ["EVA_Window_Dblclk"]
    assert rules.main_window_titles == ["카카오톡"]
    assert rules.banner_min_height_px >= 1
    assert rules.banner_max_height_px >= 1
    assert 0.1 <= rules.banner_min_width_ratio <= 1.0
    assert rules.cache_ttl_seconds >= 0.1


def test_rules_load_falls_back_ad_candidate_classes_to_main_window_classes(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "main_window_classes": ["MainA", "MainB"],
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))
    assert rules.main_window_classes == ["MainA", "MainB"]
    assert rules.ad_candidate_classes == ["MainA", "MainB"]


def test_rules_load_falls_back_ad_candidate_classes_when_invalid_type(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "main_window_classes": ["MainOnly"],
                "ad_candidate_classes": "EVA_Window_Dblclk",
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))
    assert rules.main_window_classes == ["MainOnly"]
    assert rules.ad_candidate_classes == ["MainOnly"]


def test_rules_load_coerces_ad_candidate_classes(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "ad_candidate_classes": ["AdCandidateWin", "", 123, "PopupCandidate"],
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))
    assert rules.ad_candidate_classes == ["AdCandidateWin", "PopupCandidate"]


def test_settings_load_backs_up_malformed_json_and_records_warning(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text("{ not-json", encoding="utf-8")
    consume_load_warnings()

    cfg = LayoutSettingsV11.load(str(path))

    assert cfg == LayoutSettingsV11()
    backups = list(tmp_path.glob("layout_settings_v11.json.broken-*"))
    assert len(backups) == 1
    warnings = consume_load_warnings()
    assert any("layout_settings_v11.json" in msg for msg in warnings)


def test_rules_load_backs_up_non_object_top_level_and_records_warning(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text("[]", encoding="utf-8")
    consume_load_warnings()

    rules = LayoutRulesV11.load(str(path))

    assert rules == LayoutRulesV11()
    backups = list(tmp_path.glob("layout_rules_v11.json.broken-*"))
    assert len(backups) == 1
    warnings = consume_load_warnings()
    assert any("layout_rules_v11.json" in msg for msg in warnings)


def test_rules_load_swaps_banner_bounds_and_records_warning(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "banner_min_height_px": 300,
                "banner_max_height_px": 100,
            }
        ),
        encoding="utf-8",
    )
    consume_load_warnings()

    rules = LayoutRulesV11.load(str(path))

    assert rules.banner_min_height_px == 100
    assert rules.banner_max_height_px == 300
    warnings = consume_load_warnings()
    assert any("자동 교정" in msg for msg in warnings)
