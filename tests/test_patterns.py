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


def test_parse_patterns_and_matchers():
    m = load_module()

    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    cfg = m.PatternConfig(str(Path("nonexistent_patterns.json")), logger)
    matcher = m.PatternMatcher(cfg)

    patterns = cfg._parse_patterns(
        [
            {"type": "text_startswith", "value": "BannerAdView"},
            {"type": "text_contains", "value": "AdFit"},
            {"type": "text_equals", "value": "광고"},
            {"type": "class_equals", "value": "EVA_ChildWindow_D498"},
            {"type": "class_startswith", "value": "EVA_"},
            {"type": "text_regex", "value": r"Ad.*View"},
            {"type": "text_regex", "value": "("},  # invalid regex
        ]
    )

    assert any(p.pattern_type.value == "text_startswith" for p in patterns)
    assert any(p.pattern_type.value == "class_startswith" for p in patterns)

    # Invalid regex should not crash and should never match.
    invalid = [p for p in patterns if p.pattern_type.value == "text_regex" and p.value == "("][0]
    assert invalid.compiled_regex is None
    assert matcher._matches_pattern("Anything", "Anything", invalid) is False

    # Spot-check matching logic.
    assert matcher._matches_pattern("BannerAdView123", "", patterns[0]) is True
    assert matcher._matches_pattern("xxAdFitxx", "", patterns[1]) is True
    assert matcher._matches_pattern("광고", "", patterns[2]) is True
    assert matcher._matches_pattern("", "EVA_ChildWindow_D498", patterns[3]) is True
    assert matcher._matches_pattern("", "EVA_Window", patterns[4]) is True
