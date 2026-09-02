use serde_json::{json, Value};

use crate::config::{load_rules, load_settings, runtime_paths, VERSION};

pub fn run(as_json: bool) -> i32 {
    let paths = runtime_paths();
    let _ = std::fs::create_dir_all(&paths.appdata_dir);
    let (settings, settings_warnings) = load_settings(&paths.settings_file);
    let (_rules, rules_warnings) = load_rules(&paths.rules_file);
    let appdata_ok = paths.appdata_dir.is_dir();
    let win32_ok = cfg!(windows);
    let mut warnings = settings_warnings;
    warnings.extend(rules_warnings);
    let payload = json!({
        "version": VERSION,
        "windows": win32_ok,
        "appdata_ok": appdata_ok,
        "settings_enabled": settings.enabled,
        "warnings": warnings,
        "core": "ok",
    });
    if as_json {
        println!(
            "{}",
            serde_json::to_string_pretty(&payload).unwrap_or_else(|_| "{}".into())
        );
    } else {
        println!("self-check version={VERSION} windows={win32_ok} appdata_ok={appdata_ok}");
        for warning in &warnings {
            println!("warning: {warning}");
        }
    }
    if win32_ok && appdata_ok {
        0
    } else {
        1
    }
}

pub fn as_value() -> Value {
    json!({"version": VERSION})
}
