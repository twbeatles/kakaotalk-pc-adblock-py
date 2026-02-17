import importlib.util
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "카카오톡 광고제거 v10.0.py"
    spec = importlib.util.spec_from_file_location("kakao_adblock", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_layout_engine_score_candidate_bannerish():
    m = load_module()

    root_rect = (0, 0, 500, 700)
    cand_rect = (0, 587, 500, 700)  # height 113, bottom aligned
    weights = {
        "is_chrome_widget": 3,
        "title_contains_ad_token": 4,
        "height_in_band": 2,
        "overlap_ratio_high": 2,
        "bottom_aligned_strong": 2,
        "is_content_view": -5,
        "is_eva_child": 1,
    }

    score = m.LayoutEngine.score_candidate(
        "Chrome_WidgetWin_1",
        "AdFit NAS Advertisement",
        cand_rect,
        root_rect,
        is_content_view=False,
        bottom_margin_px=25,
        weights=weights,
    )
    assert score >= 6


def test_layout_engine_score_candidate_content_view_penalty():
    m = load_module()

    root_rect = (0, 0, 500, 700)
    cand_rect = (0, 100, 500, 700)  # large view, not a banner
    weights = {
        "is_chrome_widget": 3,
        "title_contains_ad_token": 4,
        "height_in_band": 2,
        "overlap_ratio_high": 2,
        "bottom_aligned_strong": 2,
        "is_content_view": -5,
        "is_eva_child": 1,
    }

    score = m.LayoutEngine.score_candidate(
        "EVA_ChildWindow",
        "OnlineMainView_0x123",
        cand_rect,
        root_rect,
        is_content_view=True,
        bottom_margin_px=25,
        weights=weights,
    )
    assert score < 6

