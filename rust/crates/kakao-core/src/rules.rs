use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LayoutSettings {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_true")]
    pub aggressive_mode: bool,
}

impl Default for LayoutSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            aggressive_mode: true,
        }
    }
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LayoutRules {
    #[serde(default = "default_main_window_classes")]
    pub main_window_classes: Vec<String>,
    #[serde(default = "default_main_window_classes")]
    pub ad_candidate_classes: Vec<String>,
    #[serde(default = "default_main_window_titles")]
    pub main_window_titles: Vec<String>,
    #[serde(default = "default_main_view_prefix")]
    pub main_view_prefix: String,
    #[serde(default = "default_lock_view_prefix")]
    pub lock_view_prefix: String,
    #[serde(default = "default_eva_child_class")]
    pub eva_child_class: String,
    #[serde(default = "default_custom_scroll_prefix")]
    pub custom_scroll_prefix: String,
    #[serde(default = "default_chrome_legacy_title")]
    pub chrome_legacy_title: String,
    #[serde(default = "default_chrome_legacy_title_contains")]
    pub chrome_legacy_title_contains: Vec<String>,
    #[serde(default = "default_chrome_widget_prefixes")]
    pub chrome_widget_prefixes: Vec<String>,
    #[serde(default = "default_popup_ad_classes")]
    pub popup_ad_classes: Vec<String>,
    #[serde(default = "default_popup_search_depth")]
    pub popup_search_depth: i32,
    #[serde(default)]
    pub popup_host_text_contains: Vec<String>,
    #[serde(default = "default_true")]
    pub popup_host_require_empty_text: bool,
    #[serde(default = "default_aggressive_ad_tokens")]
    pub aggressive_ad_tokens: Vec<String>,
    #[serde(default = "default_banner_min_height_px")]
    pub banner_min_height_px: i32,
    #[serde(default = "default_banner_max_height_px")]
    pub banner_max_height_px: i32,
    #[serde(default = "default_banner_min_width_ratio")]
    pub banner_min_width_ratio: f64,
    #[serde(default = "default_banner_bottom_margin_px")]
    pub banner_bottom_margin_px: i32,
    #[serde(default)]
    pub hide_bottom_banner_without_token: bool,
    #[serde(default = "default_true")]
    pub close_empty_eva_child_requires_ad_signal: bool,
    #[serde(default = "default_layout_shadow_padding_px")]
    pub layout_shadow_padding_px: i32,
    #[serde(default = "default_main_view_padding_px")]
    pub main_view_padding_px: i32,
    #[serde(default = "default_weak_signal_confirm_ticks")]
    pub weak_signal_confirm_ticks: i64,
}

impl Default for LayoutRules {
    fn default() -> Self {
        serde_json::from_value(serde_json::json!({})).expect("default rules")
    }
}

impl LayoutRules {
    pub fn overlay(self, overrides: &serde_json::Value) -> Self {
        self.overlay_with_warnings(overrides).0
    }

    pub fn overlay_with_warnings(self, overrides: &serde_json::Value) -> (Self, Vec<String>) {
        merge_typed_overlay(self, overrides, "layout_rules_v11.json")
    }

    pub fn aggressive_ad_tokens_lc(&self) -> Vec<String> {
        self.aggressive_ad_tokens
            .iter()
            .map(|token| token.to_lowercase())
            .collect()
    }
}

fn merge_typed_overlay<T>(base: T, overrides: &serde_json::Value, label: &str) -> (T, Vec<String>)
where
    T: serde::Serialize + for<'de> serde::Deserialize<'de> + Clone,
{
    if overrides.is_null() {
        return (base, Vec::new());
    }
    let Some(over) = overrides.as_object() else {
        return (base, Vec::new());
    };
    if over.is_empty() {
        return (base, Vec::new());
    }
    let Ok(mut current) = serde_json::to_value(&base) else {
        return (
            base,
            vec![format!("{label} 직렬화에 실패해 기본값을 유지합니다.")],
        );
    };
    let mut result = base;
    let mut warnings = Vec::new();
    for (key, value) in over {
        let mut trial = current.clone();
        if let Some(map) = trial.as_object_mut() {
            map.insert(key.clone(), value.clone());
        }
        match serde_json::from_value::<T>(trial.clone()) {
            Ok(parsed) => {
                current = trial;
                result = parsed;
            }
            Err(_) => {
                warnings.push(format!(
                    "{label} 필드 '{key}' 타입이 올바르지 않아 기존/기본값을 유지합니다."
                ));
            }
        }
    }
    (result, warnings)
}

fn default_main_window_classes() -> Vec<String> {
    vec!["EVA_Window_Dblclk".into(), "EVA_Window".into()]
}

fn default_main_window_titles() -> Vec<String> {
    vec!["카카오톡".into(), "KakaoTalk".into()]
}

fn default_main_view_prefix() -> String {
    "OnlineMainView".into()
}

fn default_lock_view_prefix() -> String {
    "LockModeView".into()
}

fn default_eva_child_class() -> String {
    "EVA_ChildWindow".into()
}

fn default_custom_scroll_prefix() -> String {
    "_EVA_".into()
}

fn default_chrome_legacy_title() -> String {
    "Chrome Legacy Window".into()
}

fn default_chrome_legacy_title_contains() -> Vec<String> {
    vec!["Chrome Legacy Window".into()]
}

fn default_chrome_widget_prefixes() -> Vec<String> {
    vec!["Chrome_WidgetWin_".into()]
}

fn default_popup_ad_classes() -> Vec<String> {
    vec!["AdFitWebView".into()]
}

fn default_popup_search_depth() -> i32 {
    2
}

fn default_aggressive_ad_tokens() -> Vec<String> {
    vec![
        "Ad".into(),
        "AdFit".into(),
        "Advertisement".into(),
        "광고".into(),
    ]
}

fn default_banner_min_height_px() -> i32 {
    40
}

fn default_banner_max_height_px() -> i32 {
    260
}

fn default_banner_min_width_ratio() -> f64 {
    0.75
}

fn default_banner_bottom_margin_px() -> i32 {
    40
}

fn default_layout_shadow_padding_px() -> i32 {
    2
}

fn default_main_view_padding_px() -> i32 {
    31
}

fn default_weak_signal_confirm_ticks() -> i64 {
    2
}
