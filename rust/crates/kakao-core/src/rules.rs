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
        if overrides.is_null() {
            return self;
        }
        let Some(over) = overrides.as_object() else {
            return self;
        };
        if over.is_empty() {
            return self;
        }
        let mut base = serde_json::to_value(&self).expect("serialize rules");
        if let Some(map) = base.as_object_mut() {
            for (key, value) in over {
                map.insert(key.clone(), value.clone());
            }
        }
        serde_json::from_value(base).expect("merge rules")
    }

    pub fn aggressive_ad_tokens_lc(&self) -> Vec<String> {
        self.aggressive_ad_tokens
            .iter()
            .map(|token| token.to_lowercase())
            .collect()
    }
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
