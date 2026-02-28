import json
from datetime import datetime, timedelta
from pathlib import Path

import kakao_adblocker.config as config_module
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
    assert rules.chrome_legacy_title_contains == ["Chrome Legacy Window"]


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


def test_rules_load_coerces_chrome_legacy_title_contains(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "chrome_legacy_title_contains": ["Legacy Window", "", 123],
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))

    assert rules.chrome_legacy_title_contains == ["Legacy Window"]


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


def test_rules_default_strings_are_utf8_intact():
    rules = LayoutRulesV11()

    assert "카카오톡" in rules.main_window_titles
    assert "광고" in rules.aggressive_ad_tokens
    assert "Chrome Legacy Window" in rules.chrome_legacy_title_contains


def test_rules_load_warns_when_mojibake_signatures_detected(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "main_window_titles": ["移댁뭅?ㅽ넚"],
                "aggressive_ad_tokens": ["愿묎퀬"],
            }
        ),
        encoding="utf-8",
    )
    consume_load_warnings()

    rules = LayoutRulesV11.load(str(path))

    assert rules.main_window_titles == ["移댁뭅?ㅽ넚"]
    warnings = consume_load_warnings()
    assert any("문자열 무결성 경고" in msg for msg in warnings)


def test_settings_load_cleans_broken_backup_files_by_age_and_count(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text("{ not-json", encoding="utf-8")
    now = datetime.now()

    for days_ago in range(1, 13):
        stamp = (now - timedelta(days=days_ago)).strftime("%Y%m%d-%H%M%S")
        (tmp_path / f"{path.name}.broken-{stamp}").write_text("recent", encoding="utf-8")

    very_old_stamp = (now - timedelta(days=45)).strftime("%Y%m%d-%H%M%S")
    very_old = tmp_path / f"{path.name}.broken-{very_old_stamp}"
    very_old.write_text("old", encoding="utf-8")
    consume_load_warnings()

    LayoutSettingsV11.load(str(path))

    backups = list(tmp_path.glob("layout_settings_v11.json.broken-*"))
    assert len(backups) <= 10
    assert not very_old.exists()


def test_settings_save_writes_json_atomically(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    settings = LayoutSettingsV11(enabled=False, start_minimized=False)

    settings.save(str(path))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["enabled"] is False
    assert saved["start_minimized"] is False


def test_rules_save_writes_json_atomically(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    rules = LayoutRulesV11(main_window_titles=["CustomTitle"])

    rules.save(str(path))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["main_window_titles"] == ["CustomTitle"]


def test_settings_save_preserves_existing_file_on_atomic_replace_failure(tmp_path: Path, monkeypatch):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text('{"enabled": true}', encoding="utf-8")
    settings = LayoutSettingsV11(enabled=False)

    def broken_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(config_module.os, "replace", broken_replace)

    try:
        settings.save(str(path))
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")

    assert path.read_text(encoding="utf-8") == '{"enabled": true}'
    leftovers = list(tmp_path.glob(f".{path.name}*.tmp"))
    assert leftovers == []
