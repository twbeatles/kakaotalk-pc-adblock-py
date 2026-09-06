use std::path::Path;

use serde_json::{json, Value};

use crate::config::{ensure_runtime_files, load_rules, load_settings, runtime_paths, VERSION};

pub fn run(as_json: bool, report_path: Option<&Path>, strict: bool) -> i32 {
    let paths = runtime_paths();
    let _ = std::fs::create_dir_all(&paths.appdata_dir);
    let bootstrap_warnings = ensure_runtime_files(&paths);
    let (settings, settings_warnings) = load_settings(&paths.settings_file);
    let (_rules, rules_warnings) = load_rules(&paths.rules_file);
    let appdata_ok = paths.appdata_dir.is_dir();
    let appdata_writable = probe_writable(&paths.appdata_dir);
    let win32_ok = cfg!(windows);
    let mut warnings = bootstrap_warnings;
    warnings.extend(settings_warnings);
    warnings.extend(rules_warnings);
    let mut core_ok = win32_ok && appdata_ok;
    if !appdata_writable {
        warnings.push("APPDATA 디렉터리에 쓸 수 없습니다.".into());
        if strict {
            core_ok = false;
        }
    }
    if strict && !warnings.is_empty() {
        core_ok = false;
    }
    let mut exit_code = if core_ok { 0 } else { 1 };
    let core_label = if core_ok { "ok" } else { "fail" };
    let mut payload = json!({
        "version": VERSION,
        "windows": win32_ok,
        "appdata_ok": appdata_ok,
        "appdata_writable": appdata_writable,
        "settings_enabled": settings.enabled,
        "warnings": warnings,
        "strict": strict,
        "core": core_label,
        "summary": {
            "exit_code": exit_code,
            "core": core_label
        },
    });
    if let Some(path) = report_path {
        if path.is_dir() {
            eprintln!("self-check report path is a directory: {}", path.display());
            exit_code = 1;
            payload["core"] = json!("fail");
            payload["summary"]["exit_code"] = json!(exit_code);
            payload["summary"]["core"] = json!("fail");
            if let Some(warnings) = payload["warnings"].as_array_mut() {
                warnings.push(json!("self-check 보고서 경로가 디렉터리입니다."));
            }
        } else {
            if let Some(parent) = path.parent() {
                if !parent.as_os_str().is_empty() {
                    if let Err(err) = std::fs::create_dir_all(parent) {
                        eprintln!("self-check report directory create failed: {err}");
                        exit_code = 1;
                    }
                }
            }
            if exit_code == 0 || path.is_file() || !path.exists() {
                match serde_json::to_vec_pretty(&payload) {
                    Ok(body) => {
                        if let Err(err) = std::fs::write(path, body) {
                            eprintln!("self-check report write failed: {err}");
                            exit_code = 1;
                        }
                    }
                    Err(err) => {
                        eprintln!("self-check report serialize failed: {err}");
                        exit_code = 1;
                    }
                }
            }
        }
        if exit_code != 0 {
            payload["core"] = json!("fail");
            payload["summary"]["exit_code"] = json!(exit_code);
            payload["summary"]["core"] = json!("fail");
        }
    }
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
    exit_code
}

fn probe_writable(dir: &Path) -> bool {
    let probe = dir.join(".self-check-write");
    match std::fs::write(&probe, b"ok") {
        Ok(()) => {
            let _ = std::fs::remove_file(&probe);
            true
        }
        Err(_) => false,
    }
}

pub fn as_value() -> Value {
    json!({"version": VERSION})
}
