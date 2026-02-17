import importlib.util
import logging
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "카카오톡 광고제거 v10.0.py"
    spec = importlib.util.spec_from_file_location("kakao_adblock", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_pattern_config_migrates_schema_and_keeps_backup(tmp_path: Path):
    m = load_module()

    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    cfg_path = tmp_path / "ad_patterns.json"
    cfg_path.write_text(
        """
{
  "timing": { "scan_interval_active_ms": "oops" },
  "logging": { "log_hidden_ads": "yes" },
  "ad_patterns": { "hide": [ { "type": "text_startswith", "value": "BannerAdView" } ] }
}
""".strip(),
        encoding="utf-8",
    )

    cfg = m.PatternConfig(str(cfg_path), logger)
    assert isinstance(cfg.log_hidden_ads, bool)
    assert cfg.log_hidden_ads is False  # falls back to safe default
    assert cfg.scan_interval_active > 0
    assert cfg.pid_check_idle_seconds >= 1.0

    backups = list(tmp_path.glob("ad_patterns.json.*.bak"))
    assert backups, "Expected migration backup file to be created"

