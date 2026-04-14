import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import kakao_adblocker.config as config_module
from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11, consume_load_warnings

MOJIBAKE_KAKAOTALK = "\u79fb\ub301\ubb45?\u317d\ub11a"
MOJIBAKE_AD = "\u613f\ubb0e\ud02c"


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
    assert cfg.burst_scan_iterations == 3
    assert cfg.burst_scan_interval_ms == 20
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
                "burst_scan_iterations": 99,
                "burst_scan_interval_ms": 1,
            }
        ),
        encoding="utf-8",
    )

    cfg = LayoutSettingsV11.load(str(path))
    assert cfg.idle_poll_interval_ms == 200
    assert cfg.pid_scan_interval_ms == 5000
    assert cfg.cache_cleanup_interval_ms == 250
    assert cfg.burst_scan_iterations == 20
    assert cfg.burst_scan_interval_ms == 10


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
    assert rules.popup_ad_classes == ["AdFitWebView"]
    assert rules.popup_search_depth == 2
    assert rules.popup_host_text_contains == []
    assert rules.popup_host_require_empty_text is True
    assert rules.hide_bottom_banner_without_token is False
    assert rules.close_empty_eva_child_requires_ad_signal is True
    assert rules.weak_signal_confirm_ticks == 2
    assert rules.hidden_restore_grace_ms == 250


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


def test_rules_load_coerces_popup_ad_classes(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "popup_ad_classes": ["AdFitWebView", "", 123, "PopupWebView"],
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))

    assert rules.popup_ad_classes == ["AdFitWebView", "PopupWebView"]


def test_rules_load_coerces_popup_search_depth(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "popup_search_depth": 99,
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))

    assert rules.popup_search_depth == 2


def test_rules_load_coerces_popup_host_text_contains(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "popup_host_text_contains": ["광고", "", 123, "Ad"],
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))

    assert rules.popup_host_text_contains == ["광고", "Ad"]


def test_rules_load_with_new_boolean_flags(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "hide_bottom_banner_without_token": True,
                "close_empty_eva_child_requires_ad_signal": False,
                "popup_host_require_empty_text": False,
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))

    assert rules.hide_bottom_banner_without_token is True
    assert rules.close_empty_eva_child_requires_ad_signal is False
    assert rules.popup_host_require_empty_text is False


def test_rules_load_with_signal_tuning_fields(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "weak_signal_confirm_ticks": 99,
                "hidden_restore_grace_ms": -1,
            }
        ),
        encoding="utf-8",
    )

    rules = LayoutRulesV11.load(str(path))

    assert rules.weak_signal_confirm_ticks == 10
    assert rules.hidden_restore_grace_ms == 0


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


def test_settings_load_self_heals_malformed_json_file(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text("{ malformed", encoding="utf-8")
    consume_load_warnings()

    cfg = LayoutSettingsV11.load(str(path))

    assert cfg == LayoutSettingsV11()
    healed = json.loads(path.read_text(encoding="utf-8"))
    assert healed["enabled"] is True
    warnings = consume_load_warnings()
    assert any("손상 감지" in msg for msg in warnings)
    assert any("자동 복구 성공" in msg for msg in warnings)


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


def test_rules_load_self_heals_invalid_top_level_file(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text("[]", encoding="utf-8")
    consume_load_warnings()

    rules = LayoutRulesV11.load(str(path))

    assert rules == LayoutRulesV11()
    healed = json.loads(path.read_text(encoding="utf-8"))
    assert healed["chrome_legacy_title_contains"] == ["Chrome Legacy Window"]
    warnings = consume_load_warnings()
    assert any("손상 감지" in msg for msg in warnings)
    assert any("자동 복구 성공" in msg for msg in warnings)


def test_settings_load_reports_self_heal_failure_and_keeps_defaults(tmp_path: Path, monkeypatch):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text("{ malformed", encoding="utf-8")
    consume_load_warnings()
    monkeypatch.setattr(config_module, "_atomic_write_text", lambda _path, _text: (_ for _ in ()).throw(OSError("disk full")))

    cfg = LayoutSettingsV11.load(str(path))

    assert cfg == LayoutSettingsV11()
    warnings = consume_load_warnings()
    assert any("자동 복구 실패" in msg for msg in warnings)


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
    assert "AdFitWebView" in rules.popup_ad_classes
    assert rules.popup_search_depth == 2
    assert rules.popup_host_text_contains == []
    assert rules.popup_host_require_empty_text is True
    assert rules.weak_signal_confirm_ticks == 2
    assert rules.hidden_restore_grace_ms == 250


def test_rules_load_warns_when_mojibake_signatures_detected(tmp_path: Path):
    path = tmp_path / "layout_rules_v11.json"
    path.write_text(
        json.dumps(
            {
                "main_window_titles": [MOJIBAKE_KAKAOTALK],
                "aggressive_ad_tokens": [MOJIBAKE_AD],
            }
        ),
        encoding="utf-8",
    )
    consume_load_warnings()

    rules = LayoutRulesV11.load(str(path))

    assert rules.main_window_titles == [MOJIBAKE_KAKAOTALK]
    assert rules.aggressive_ad_tokens == [MOJIBAKE_AD]
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


def test_settings_load_cleans_broken_backups_even_without_new_corruption(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text(LayoutSettingsV11.default_json(), encoding="utf-8")
    now = datetime.now()

    for days_ago in range(1, 14):
        stamp = (now - timedelta(days=days_ago)).strftime("%Y%m%d-%H%M%S")
        (tmp_path / f"{path.name}.broken-{stamp}").write_text("recent", encoding="utf-8")

    very_old_stamp = (now - timedelta(days=60)).strftime("%Y%m%d-%H%M%S")
    very_old = tmp_path / f"{path.name}.broken-{very_old_stamp}"
    very_old.write_text("old", encoding="utf-8")

    cfg = LayoutSettingsV11.load(str(path))

    assert cfg.enabled is True
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
    rules = LayoutRulesV11(
        main_window_titles=["CustomTitle"],
        hide_bottom_banner_without_token=True,
        close_empty_eva_child_requires_ad_signal=False,
    )

    rules.save(str(path))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["main_window_titles"] == ["CustomTitle"]
    assert saved["popup_ad_classes"] == ["AdFitWebView"]
    assert saved["popup_search_depth"] == 2
    assert saved["hide_bottom_banner_without_token"] is True
    assert saved["close_empty_eva_child_requires_ad_signal"] is False
    assert saved["weak_signal_confirm_ticks"] == 2
    assert saved["hidden_restore_grace_ms"] == 250


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


def test_ensure_runtime_files_creates_missing_runtime_files(tmp_path: Path, monkeypatch):
    appdata_dir = tmp_path / "appdata"
    resource_dir = tmp_path / "resource"
    resource_dir.mkdir()
    (resource_dir / "layout_settings_v11.json").write_text('{"enabled": false}\n', encoding="utf-8")
    (resource_dir / "layout_rules_v11.json").write_text('{"popup_host_require_empty_text": false}\n', encoding="utf-8")

    monkeypatch.setattr(config_module, "APPDATA_DIR", str(appdata_dir))
    monkeypatch.setattr(config_module, "SETTINGS_FILE", str(appdata_dir / "layout_settings_v11.json"))
    monkeypatch.setattr(config_module, "RULES_FILE", str(appdata_dir / "layout_rules_v11.json"))
    monkeypatch.setattr(config_module, "LOG_FILE", str(appdata_dir / "layout_adblock.log"))
    monkeypatch.setattr(config_module, "resource_base_dir", lambda: str(resource_dir))

    config_module.ensure_runtime_files()

    assert json.loads((appdata_dir / "layout_settings_v11.json").read_text(encoding="utf-8"))["enabled"] is False
    assert json.loads((appdata_dir / "layout_rules_v11.json").read_text(encoding="utf-8"))["popup_host_require_empty_text"] is False
    assert (appdata_dir / "layout_adblock.log").exists()


def test_ensure_runtime_files_preserves_existing_runtime_files(tmp_path: Path, monkeypatch):
    appdata_dir = tmp_path / "appdata"
    appdata_dir.mkdir()
    settings_path = appdata_dir / "layout_settings_v11.json"
    rules_path = appdata_dir / "layout_rules_v11.json"
    log_path = appdata_dir / "layout_adblock.log"
    settings_path.write_text('{"enabled": true}\n', encoding="utf-8")
    rules_path.write_text('{"popup_host_require_empty_text": true}\n', encoding="utf-8")
    log_path.write_text("existing-log", encoding="utf-8")

    resource_dir = tmp_path / "resource"
    resource_dir.mkdir()
    (resource_dir / "layout_settings_v11.json").write_text('{"enabled": false}\n', encoding="utf-8")
    (resource_dir / "layout_rules_v11.json").write_text('{"popup_host_require_empty_text": false}\n', encoding="utf-8")

    monkeypatch.setattr(config_module, "APPDATA_DIR", str(appdata_dir))
    monkeypatch.setattr(config_module, "SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(config_module, "RULES_FILE", str(rules_path))
    monkeypatch.setattr(config_module, "LOG_FILE", str(log_path))
    monkeypatch.setattr(config_module, "resource_base_dir", lambda: str(resource_dir))

    config_module.ensure_runtime_files()

    assert settings_path.read_text(encoding="utf-8") == '{"enabled": true}\n'
    assert rules_path.read_text(encoding="utf-8") == '{"popup_host_require_empty_text": true}\n'
    assert log_path.read_text(encoding="utf-8") == "existing-log"


def test_config_import_does_not_create_appdata_dir(monkeypatch, tmp_path: Path):
    appdata_root = tmp_path / "Roaming"
    expected_dir = appdata_root / config_module.APPDATA_DIRNAME
    module_path = Path(config_module.__file__).resolve()
    mkdir_calls: list[str] = []
    original_mkdir = Path.mkdir

    def tracking_mkdir(self: Path, *args, **kwargs):
        mkdir_calls.append(str(self))
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setenv("APPDATA", str(appdata_root))
    monkeypatch.setattr(Path, "mkdir", tracking_mkdir)

    spec = importlib.util.spec_from_file_location("tests_config_import_probe", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    assert module.APPDATA_DIR == str(expected_dir)
    assert mkdir_calls == []
    assert not expected_dir.exists()


def test_runtime_path_helpers_are_lazy_until_create(monkeypatch, tmp_path: Path):
    appdata_root = tmp_path / "Roaming"
    expected_dir = appdata_root / config_module.APPDATA_DIRNAME

    monkeypatch.setenv("APPDATA", str(appdata_root))

    paths = config_module.get_runtime_paths()

    assert paths.appdata_dir == str(expected_dir)
    assert paths.settings_file == str(expected_dir / "layout_settings_v11.json")
    assert paths.rules_file == str(expected_dir / "layout_rules_v11.json")
    assert paths.log_file == str(expected_dir / "layout_adblock.log")
    assert not expected_dir.exists()
    assert config_module.resolve_app_data_dir() == str(expected_dir)
    assert not expected_dir.exists()

    created = config_module.get_runtime_paths(create=True)

    assert created.appdata_dir == str(expected_dir)
    assert expected_dir.exists()


def test_default_runtime_save_uses_lazy_runtime_paths(monkeypatch, tmp_path: Path):
    appdata_root = tmp_path / "Roaming"
    expected_dir = appdata_root / config_module.APPDATA_DIRNAME

    monkeypatch.setenv("APPDATA", str(appdata_root))

    settings = LayoutSettingsV11(enabled=False, aggressive_mode=False)
    settings.save()

    assert expected_dir.exists()
    assert json.loads((expected_dir / "layout_settings_v11.json").read_text(encoding="utf-8"))["enabled"] is False
    saved = json.loads((expected_dir / "layout_settings_v11.json").read_text(encoding="utf-8"))
    assert saved["burst_scan_iterations"] == 3
    assert saved["burst_scan_interval_ms"] == 20

    loaded = LayoutSettingsV11.load()

    assert loaded.enabled is False
    assert loaded.aggressive_mode is False
