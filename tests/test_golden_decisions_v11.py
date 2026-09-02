from kakao_adblocker.dev.export_fixture_decisions import check_golden_files
from kakao_adblocker.dev.fixture_runner import FIXTURE_CASES, build_golden_payload


def test_golden_payload_normal_main_window_has_confirmed_main_and_no_hides():
    payload = build_golden_payload("normal_main_window.json")

    assert payload["fixture"] == "normal_main_window.json"
    assert payload["settings"]["aggressive_mode"] is False
    assert payload["expected"]["state"]["main_window_count"] == 1
    assert payload["expected"]["state"]["candidate_main_window_count"] == 1
    assert payload["expected"]["actions"]["hide"] == []
    assert payload["expected"]["actions"]["close"] == []


def test_golden_payload_owned_popup_legacy_ad_hides_owned_host():
    payload = build_golden_payload("owned_popup_legacy_ad.json")

    assert 527936 in payload["expected"]["actions"]["hide"]
    assert 591132 not in payload["expected"]["actions"]["close"]
    assert payload["expected"]["state"]["main_window_count"] == 1


def test_golden_catalog_covers_all_window_dump_fixtures():
    dump_names = {case.fixture for case in FIXTURE_CASES}
    assert dump_names == {
        "bottom_web_panel_no_token.json",
        "empty_eva_child_no_ad_signal.json",
        "guarded_popup_adfit_viewer.json",
        "launch_ad_flash_banner.json",
        "legacy_ad_surface.json",
        "non_main_media_viewer.json",
        "normal_main_window.json",
        "owned_popup_legacy_ad.json",
        "popup_adfit_webview.json",
        "popup_non_adfit_viewer.json",
    }


def test_committed_golden_files_match_exporter():
    mismatches = check_golden_files()
    assert mismatches == []
