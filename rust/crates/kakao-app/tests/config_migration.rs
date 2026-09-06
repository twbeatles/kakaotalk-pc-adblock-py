use std::fs;
use std::path::PathBuf;

use kakao_app::config::{load_rules, load_settings, save_settings, AppSettings};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repo root")
}

#[test]
fn legacy_settings_v11_loads_and_preserves_fields() {
    let fixture_path = repo_root().join("tests/fixtures/config/legacy_python_settings.json");
    let (settings, warnings) = load_settings(&fixture_path);
    assert!(warnings.is_empty(), "unexpected warnings: {:?}", warnings);

    assert!(!settings.enabled);
    assert!(settings.run_on_startup);
    assert!(!settings.start_minimized);
    assert_eq!(settings.poll_interval_ms, 75);
    assert_eq!(settings.idle_poll_interval_ms, 300);
    assert_eq!(settings.pid_scan_interval_ms, 500);
    assert_eq!(settings.cache_cleanup_interval_ms, 2000);
    assert_eq!(settings.burst_scan_iterations, 5);
    assert_eq!(settings.burst_scan_interval_ms, 30);
    assert!(!settings.aggressive_mode);
    assert_eq!(settings.log_level, "DEBUG");

    // Test round-trip save and reload in temp dir
    let temp_dir = std::env::temp_dir().join("kakao_config_migration_test");
    let _ = fs::remove_dir_all(&temp_dir);
    fs::create_dir_all(&temp_dir).unwrap();

    let save_path = temp_dir.join("layout_settings_v11.json");
    save_settings(&save_path, &settings).expect("save_settings failed");

    let (reloaded, reloaded_warnings) = load_settings(&save_path);
    assert!(reloaded_warnings.is_empty());
    assert_eq!(settings, reloaded);

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn legacy_rules_v11_overlay_and_bounds_correction() {
    let fixture_path = repo_root().join("tests/fixtures/config/legacy_python_rules.json");
    let (rules, warnings) = load_rules(&fixture_path);
    assert!(warnings.is_empty());
    assert_eq!(rules.banner_min_height_px, 50);
    assert_eq!(rules.banner_max_height_px, 200);
    assert_eq!(rules.popup_search_depth, 1);
    assert_eq!(rules.popup_host_text_contains, vec!["특별할인".to_string()]);

    // Test inverted min/max bounds auto-correction
    let inverted_path = repo_root().join("tests/fixtures/config/inverted_banner_rules.json");
    let (corrected_rules, corr_warnings) = load_rules(&inverted_path);
    assert_eq!(corrected_rules.banner_min_height_px, 50);
    assert_eq!(corrected_rules.banner_max_height_px, 300);
    assert!(corr_warnings
        .iter()
        .any(|w| w.contains("역전되어 자동 교정")));
}

#[test]
fn malformed_json_creates_broken_backup_and_heals() {
    let temp_dir = std::env::temp_dir().join("kakao_config_heal_test");
    let _ = fs::remove_dir_all(&temp_dir);
    fs::create_dir_all(&temp_dir).unwrap();

    let broken_file = temp_dir.join("layout_settings_v11.json");
    fs::write(&broken_file, "{ not valid json !!!").unwrap();

    let (healed_settings, warnings) = load_settings(&broken_file);
    assert!(!warnings.is_empty(), "expected warnings for broken file");
    assert!(warnings.iter().any(|w| w.contains("손상 감지")));
    assert!(warnings.iter().any(|w| w.contains("자동 복구 성공")));

    // Safe default returned
    assert_eq!(healed_settings, AppSettings::default());

    // Verify .broken- backup was created
    let backup_exists = fs::read_dir(&temp_dir)
        .unwrap()
        .flatten()
        .any(|entry| entry.file_name().to_string_lossy().contains(".broken-"));
    assert!(backup_exists, "expected .broken- backup file to exist");

    // The original file is now valid JSON
    let content = fs::read_to_string(&broken_file).unwrap();
    assert!(serde_json::from_str::<serde_json::Value>(&content).is_ok());

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn typed_rules_field_error_does_not_panic_and_warns() {
    let temp_dir = std::env::temp_dir().join(format!(
        "kakao_rules_typed_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&temp_dir).unwrap();
    let path = temp_dir.join("layout_rules_v11.json");
    fs::write(
        &path,
        r#"{"popup_search_depth":"2","banner_min_height_px":77}"#,
    )
    .unwrap();

    let (rules, warnings) = load_rules(&path);
    assert!(
        warnings.iter().any(|w| w.contains("popup_search_depth")),
        "expected type warning, got {warnings:?}"
    );
    assert_eq!(
        rules.popup_search_depth, 2,
        "invalid field uses default then clamp"
    );
    assert_eq!(rules.banner_min_height_px, 77);
    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn typed_settings_preserves_valid_fields() {
    let temp_dir = std::env::temp_dir().join(format!(
        "kakao_settings_typed_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&temp_dir).unwrap();
    let path = temp_dir.join("layout_settings_v11.json");
    fs::write(
        &path,
        r#"{"enabled":false,"poll_interval_ms":"bad","aggressive_mode":false}"#,
    )
    .unwrap();

    let (settings, warnings) = load_settings(&path);
    assert!(
        warnings.iter().any(|w| w.contains("poll_interval_ms")),
        "expected type warning, got {warnings:?}"
    );
    assert!(
        !settings.enabled,
        "valid enabled=false must be preserved instead of resetting all defaults"
    );
    assert!(!settings.aggressive_mode);
    assert_eq!(settings.poll_interval_ms, 50);
    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn typed_rules_null_and_bad_array_keep_defaults() {
    let temp_dir = std::env::temp_dir().join(format!(
        "kakao_rules_null_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&temp_dir).unwrap();
    let path = temp_dir.join("layout_rules_v11.json");
    fs::write(
        &path,
        r#"{"popup_ad_classes":"AdFitWebView","popup_host_text_contains":null,"weak_signal_confirm_ticks":-1}"#,
    )
    .unwrap();
    let (rules, warnings) = load_rules(&path);
    assert!(warnings.iter().any(|w| w.contains("popup_ad_classes")));
    assert!(warnings
        .iter()
        .any(|w| w.contains("popup_host_text_contains")));
    assert_eq!(rules.popup_ad_classes, vec!["AdFitWebView".to_string()]);
    assert!(rules.popup_host_text_contains.is_empty());
    assert_eq!(rules.weak_signal_confirm_ticks, -1);
    let _ = fs::remove_dir_all(&temp_dir);
}
