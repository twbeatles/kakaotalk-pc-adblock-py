import json
from pathlib import Path

from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11


def test_settings_load_with_type_coercion(tmp_path: Path):
    path = tmp_path / "layout_settings_v11.json"
    path.write_text(
        json.dumps(
            {
                "enabled": "yes",
                "run_on_startup": 1,
                "start_minimized": False,
                "poll_interval_ms": "oops",
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
    assert cfg.poll_interval_ms == 100
    assert cfg.aggressive_mode is True
    assert cfg.log_level == "INFO"


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
    assert rules.main_window_titles == ["카카오톡"]
    assert rules.banner_min_height_px >= 1
    assert rules.banner_max_height_px >= 1
    assert 0.1 <= rules.banner_min_width_ratio <= 1.0
    assert rules.cache_ttl_seconds >= 0.1
