use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use kakao_core::{LayoutRules, LayoutSettings};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const VERSION: &str = "11.1.1";
pub const APPDATA_DIRNAME: &str = "KakaoTalkAdBlockerLayout";
pub const SETTINGS_FILE: &str = "layout_settings_v11.json";
pub const RULES_FILE: &str = "layout_rules_v11.json";
pub const LOG_FILE: &str = "layout_adblock.log";
pub const UPDATE_PUBLIC_KEY_B64: &str = "Cix9d2r5UZxpDL4Bp9CWNrjMDRTQHF5Y1snTMYnMQ2U=";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AppSettings {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub run_on_startup: bool,
    #[serde(default = "default_true")]
    pub start_minimized: bool,
    #[serde(default = "default_poll")]
    pub poll_interval_ms: u32,
    #[serde(default = "default_idle_poll")]
    pub idle_poll_interval_ms: u32,
    #[serde(default = "default_pid_scan")]
    pub pid_scan_interval_ms: u32,
    #[serde(default = "default_cache_cleanup")]
    pub cache_cleanup_interval_ms: u32,
    #[serde(default = "default_burst_iter")]
    pub burst_scan_iterations: u32,
    #[serde(default = "default_burst_interval")]
    pub burst_scan_interval_ms: u32,
    #[serde(default = "default_true")]
    pub aggressive_mode: bool,
    #[serde(default = "default_log_level")]
    pub log_level: String,
}

impl Default for AppSettings {
    fn default() -> Self {
        serde_json::from_value(serde_json::json!({})).expect("default settings")
    }
}

impl AppSettings {
    pub fn to_core(&self) -> LayoutSettings {
        LayoutSettings {
            enabled: self.enabled,
            aggressive_mode: self.aggressive_mode,
        }
    }
}

fn default_true() -> bool {
    true
}
fn default_poll() -> u32 {
    50
}
fn default_idle_poll() -> u32 {
    200
}
fn default_pid_scan() -> u32 {
    200
}
fn default_cache_cleanup() -> u32 {
    1000
}
fn default_burst_iter() -> u32 {
    3
}
fn default_burst_interval() -> u32 {
    20
}
fn default_log_level() -> String {
    "INFO".into()
}

#[derive(Debug, Clone)]
pub struct RuntimePaths {
    pub appdata_dir: PathBuf,
    pub settings_file: PathBuf,
    pub rules_file: PathBuf,
    pub log_file: PathBuf,
}

pub fn runtime_paths() -> RuntimePaths {
    let appdata = std::env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(".").join("AppData").join("Roaming"));
    let appdata_dir = appdata.join(APPDATA_DIRNAME);
    RuntimePaths {
        settings_file: appdata_dir.join(SETTINGS_FILE),
        rules_file: appdata_dir.join(RULES_FILE),
        log_file: appdata_dir.join(LOG_FILE),
        appdata_dir,
    }
}

pub fn load_settings(path: &Path) -> (AppSettings, Vec<String>) {
    load_json(path, "layout_settings_v11.json", AppSettings::default())
}

pub fn load_rules(path: &Path) -> (LayoutRules, Vec<String>) {
    let (value, mut warnings) = load_json_value(path, "layout_rules_v11.json");
    let mut rules = LayoutRules::default().overlay(&value);
    if rules.banner_min_height_px > rules.banner_max_height_px {
        std::mem::swap(
            &mut rules.banner_min_height_px,
            &mut rules.banner_max_height_px,
        );
        warnings.push(
            "layout_rules_v11.json banner 높이 범위(min/max)가 역전되어 자동 교정했습니다.".into(),
        );
    }
    rules.popup_search_depth = rules.popup_search_depth.clamp(1, 2);
    if value.get("ad_candidate_classes").is_none() {
        rules.ad_candidate_classes = rules.main_window_classes.clone();
    }
    (rules, warnings)
}

fn load_json<T: for<'de> Deserialize<'de> + Serialize + Default>(
    path: &Path,
    label: &str,
    default: T,
) -> (T, Vec<String>) {
    let (value, warnings) = load_json_value(path, label);
    if value.is_null()
        || value.as_object().map(|o| o.is_empty()).unwrap_or(false) && !path.is_file()
    {
        return (default, warnings);
    }
    match serde_json::from_value::<T>(value) {
        Ok(parsed) => (parsed, warnings),
        Err(_) => (default, warnings),
    }
}

fn load_json_value(path: &Path, label: &str) -> (Value, Vec<String>) {
    let mut warnings = Vec::new();
    cleanup_broken_backups(path);
    if !path.is_file() {
        return (Value::Object(Default::default()), warnings);
    }
    match fs::read_to_string(path) {
        Ok(text) => match serde_json::from_str::<Value>(&text) {
            Ok(Value::Object(map)) => (Value::Object(map), warnings),
            Ok(_) => {
                backup_broken(path, label, "최상위 타입이 object가 아님", &mut warnings);
                heal_default(path, label, &mut warnings);
                (Value::Object(Default::default()), warnings)
            }
            Err(_) => {
                backup_broken(path, label, "JSON 파싱 실패", &mut warnings);
                heal_default(path, label, &mut warnings);
                (Value::Object(Default::default()), warnings)
            }
        },
        Err(err) => {
            warnings.push(format!("{label} 읽기 실패: {err}"));
            (Value::Object(Default::default()), warnings)
        }
    }
}

fn backup_broken(path: &Path, label: &str, reason: &str, warnings: &mut Vec<String>) {
    let stamp = timestamp();
    let backup = path.with_file_name(format!(
        "{}.broken-{stamp}",
        path.file_name().and_then(|n| n.to_str()).unwrap_or("file")
    ));
    match fs::copy(path, &backup) {
        Ok(_) => warnings.push(format!(
            "{label} 손상 감지: {reason}. 백업 생성: {}.",
            backup.display()
        )),
        Err(err) => warnings.push(format!("{label} 손상 감지: {reason}. 백업 실패({err}).")),
    }
}

fn heal_default(path: &Path, label: &str, warnings: &mut Vec<String>) {
    let default = if label.contains("settings") {
        serde_json::to_string_pretty(&AppSettings::default()).unwrap_or_else(|_| "{}".into())
    } else {
        serde_json::to_string_pretty(&LayoutRules::default()).unwrap_or_else(|_| "{}".into())
    };
    match atomic_write(path, &format!("{default}\n")) {
        Ok(()) => warnings.push(format!(
            "{label} 자동 복구 성공: 기본값 JSON으로 재생성했습니다."
        )),
        Err(err) => warnings.push(format!(
            "{label} 자동 복구 실패({err}). 기본값으로 동작합니다."
        )),
    }
}

pub fn atomic_write(path: &Path, text: &str) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("tmp");
    {
        let mut file = fs::File::create(&tmp)?;
        file.write_all(text.as_bytes())?;
        file.flush()?;
    }
    fs::rename(&tmp, path)
}

fn cleanup_broken_backups(path: &Path) {
    let Some(parent) = path.parent() else {
        return;
    };
    let prefix = format!(
        "{}.broken-",
        path.file_name().and_then(|n| n.to_str()).unwrap_or("")
    );
    let mut backups: Vec<PathBuf> = fs::read_dir(parent)
        .ok()
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            p.file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.starts_with(&prefix))
        })
        .collect();
    backups.sort();
    let keep = 10usize;
    if backups.len() > keep {
        for old in backups.iter().take(backups.len() - keep) {
            let _ = fs::remove_file(old);
        }
    }
}

fn timestamp() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{secs}")
}

pub fn save_settings(path: &Path, settings: &AppSettings) -> io::Result<()> {
    let body = serde_json::to_string_pretty(settings).unwrap_or_else(|_| "{}".into());
    atomic_write(path, &format!("{body}\n"))
}
