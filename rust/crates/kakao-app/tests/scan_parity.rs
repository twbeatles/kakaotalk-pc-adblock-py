use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::Ordering;

use kakao_app::config::AppSettings;
use kakao_app::engine::{restore_all, tick, SharedFlags};
use kakao_app::graph_build::build_graph;
use kakao_core::{evaluate_graph, GoldenFile, LayoutRules};
use kakao_win32::{FakeWin32, Win32Api};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repo root")
}

#[test]
fn fake_graph_matches_dump_and_golden() {
    let golden_dir = repo_root().join("tests/fixtures/golden");
    let dump_dir = repo_root().join("tests/fixtures/window_dumps");
    let mut goldens: Vec<_> = fs::read_dir(golden_dir)
        .unwrap()
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|e| e.to_str()) == Some("json"))
        .collect();
    goldens.sort();
    assert!(!goldens.is_empty());
    for path in goldens {
        let golden: GoldenFile = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        let dump = fs::read_to_string(dump_dir.join(&golden.fixture)).unwrap();
        let api = FakeWin32::from_dump_json(&dump).unwrap();
        let pids = api.pids();
        let graph = build_graph(&api, &pids);
        let rules = LayoutRules::default().overlay(&golden.rules_overrides);
        let actual = evaluate_graph(&graph, &golden.settings, &rules);
        let actual_value = serde_json::to_value(&actual).unwrap();
        let expected_value = serde_json::to_value(&golden.expected).unwrap();
        assert_eq!(actual_value, expected_value, "parity {}", golden.fixture);
    }
}

#[test]
fn owned_popup_hide_and_restore_on_fake_api() {
    let dump = fs::read_to_string(
        repo_root().join("tests/fixtures/window_dumps/owned_popup_legacy_ad.json"),
    )
    .unwrap();
    let api = FakeWin32::from_dump_json(&dump).unwrap();
    let pids = api.pids();
    let settings = AppSettings {
        enabled: true,
        aggressive_mode: true,
        ..AppSettings::default()
    };
    let flags = SharedFlags::from_settings(&settings, true);
    let rules = LayoutRules::default();
    let mut snapshots = HashMap::new();
    let evaluation = tick(&api, &pids, &settings, &rules, &mut snapshots, &flags);
    assert!(evaluation.actions.hide.contains(&527936));
    assert!(!api.is_window_visible(527936));
    flags.enabled.store(false, Ordering::SeqCst);
    let (failures, err) = restore_all(&api, &mut snapshots);
    assert_eq!((failures, err.as_str()), (0, ""), "restore should succeed");
    assert!(api.is_window_visible(527936));
}

#[test]
fn view_resize_keeps_child_top_left_like_python_swp_nomove() {
    // OnlineMainView sits at y=38 under the KakaoTalk chrome. Resize must keep
    // that offset (SWP_NOMOVE). Applying (0,0,w,h) without NOMOVE leaves a
    // blank strip at the bottom that looks like a leftover ad banner.
    let dump = r#"{
        "pids": [42],
        "windows": [{
            "hwnd": 100,
            "class": "EVA_Window_Dblclk",
            "text": "카카오톡",
            "pid": 42,
            "visible": true,
            "rect": [1337, 0, 1920, 1032],
            "children": [{
                "hwnd": 101,
                "class": "EVA_ChildWindow",
                "text": "OnlineMainView_0x1",
                "pid": 42,
                "visible": true,
                "rect": [1338, 38, 1919, 800],
                "children": []
            }]
        }]
    }"#;
    let api = FakeWin32::from_dump_json(dump).unwrap();
    let pids = api.pids();
    let settings = AppSettings {
        enabled: true,
        aggressive_mode: true,
        ..AppSettings::default()
    };
    let flags = SharedFlags::from_settings(&settings, true);
    let rules = LayoutRules::default();
    let mut snapshots = HashMap::new();
    let evaluation = tick(&api, &pids, &settings, &rules, &mut snapshots, &flags);
    assert!(
        evaluation
            .actions
            .set_pos
            .iter()
            .any(|pos| pos.first() == Some(&101)),
        "expected OnlineMainView resize"
    );
    let rect = api.get_window_rect(101).expect("resized child");
    assert_eq!(rect.left, 1338, "SWP_NOMOVE must keep child left");
    assert_eq!(rect.top, 38, "SWP_NOMOVE must keep child top");
    assert_eq!(rect.width(), 581);
    assert_eq!(rect.height(), 1001);
}
