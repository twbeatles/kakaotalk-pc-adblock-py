from kakao_adblocker.config import LayoutRulesV11, LayoutSettingsV11
from kakao_adblocker.dev.fixture_runner import run_fixture as _run_fixture


def test_window_dump_fixture_normal_main_window():
    _payload, api, engine = _run_fixture(
        "normal_main_window.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
    )

    assert engine.state.main_window_count == 1
    assert engine.state.candidate_main_window_count == 1
    assert api.hide_calls == []


def test_window_dump_fixture_legacy_ad_surface_hides_top_level_candidate():
    _payload, api, engine = _run_fixture(
        "legacy_ad_surface.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
    )

    assert engine.state.main_window_count == 1
    assert 200 in api.hide_calls


def test_window_dump_fixture_bottom_web_panel_without_token_is_not_hidden():
    _payload, api, _engine = _run_fixture(
        "bottom_web_panel_no_token.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
        rules=LayoutRulesV11(hide_bottom_banner_without_token=False),
    )

    assert 102 not in api.hide_calls


def test_window_dump_fixture_empty_eva_child_without_ad_signal_is_not_closed():
    _payload, api, _engine = _run_fixture(
        "empty_eva_child_no_ad_signal.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(close_empty_eva_child_requires_ad_signal=True),
    )

    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    assert 104 not in closed_handles


def test_window_dump_fixture_popup_adfit_webview_is_closed_hidden_and_restored_when_disabled():
    _payload, api, engine = _run_fixture(
        "popup_adfit_webview.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(popup_ad_classes=["AdFitWebView"]),
    )

    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    assert 200 in closed_handles
    assert 201 in closed_handles
    assert 200 in api.hide_calls
    assert 201 in api.hide_calls
    assert (200, 0, 0, 0, 0) in api.set_pos_calls
    assert (201, 0, 0, 0, 0) in api.set_pos_calls
    assert any(identity[0] == 200 for identity in engine._hidden_windows)
    assert any(identity[0] == 201 for identity in engine._hidden_windows)

    engine.set_enabled(False)
    engine.stop()

    assert 200 in api.show_calls
    assert 201 in api.show_calls


def test_window_dump_fixture_popup_non_adfit_viewer_is_ignored_by_default():
    _payload, api, _engine = _run_fixture(
        "popup_non_adfit_viewer.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(popup_ad_classes=["AdFitWebView"]),
    )

    assert api.hide_calls == []
    assert api.send_calls == []


def test_window_dump_fixture_launch_ad_flash_banner_hides_immediately():
    _payload, api, _engine = _run_fixture(
        "launch_ad_flash_banner.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
    )

    assert 102 in api.hide_calls


def test_window_dump_fixture_guarded_popup_adfit_viewer_is_ignored():
    _payload, api, _engine = _run_fixture(
        "guarded_popup_adfit_viewer.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=False),
        rules=LayoutRulesV11(popup_ad_classes=["AdFitWebView"]),
    )

    assert api.hide_calls == []
    assert api.send_calls == []


def test_window_dump_fixture_owned_popup_legacy_ad_is_hidden():
    """Ground-truth regression: KakaoTalk 26.5 renders the banner ad as an
    OWNED WS_POPUP window (owner = main window), so GetParent returns the main
    handle and the engine classifies it via the empty-text child-of-main branch,
    then hides it by legacy signature. If this breaks, ad blocking is broken on
    the current client. See PROJECT_AUDIT.md and owned_popup_legacy_ad.json."""
    _payload, api, engine = _run_fixture(
        "owned_popup_legacy_ad.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
    )

    assert engine.state.main_window_count == 1
    # The owned popup is enumerated top-level but resolves to the main window
    # as its owner, so it is tracked as an ad sub-window candidate.
    assert 527936 in engine._ad_subwindow_candidates
    # The legacy "Chrome Legacy Window" descendant triggers a strong hide.
    assert 527936 in api.hide_calls
    assert any(identity[0] == 527936 for identity in engine._hidden_windows)
    # The non-ad main view child must never be closed.
    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    assert 591132 not in closed_handles


def test_window_dump_fixture_owned_popup_legacy_ad_is_restored_when_disabled():
    """Disabling blocking must restore the previously hidden owned-popup ad."""
    _payload, api, engine = _run_fixture(
        "owned_popup_legacy_ad.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
    )
    assert 527936 in api.hide_calls

    engine.set_enabled(False)
    engine.stop()

    assert 527936 in api.show_calls


def test_window_dump_fixture_non_main_media_viewer_is_ignored():
    _payload, api, _engine = _run_fixture(
        "non_main_media_viewer.json",
        settings=LayoutSettingsV11(enabled=True, aggressive_mode=True),
    )

    closed_handles = [hwnd for hwnd, _msg, _wparam, _lparam in api.send_calls]
    resized_handles = [hwnd for hwnd, _x, _y, _width, _height in api.set_pos_calls]

    assert 200 not in api.hide_calls
    assert 201 not in api.hide_calls
    assert 200 not in closed_handles
    assert 201 not in closed_handles
    assert 201 not in resized_handles
