fn main() {
    let icon = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
        .join("packaging")
        .join("app_icon.ico");
    println!("cargo:rerun-if-changed={}", icon.display());
    if std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default() != "windows" {
        return;
    }
    if !icon.is_file() {
        panic!("missing application icon: {}", icon.display());
    }

    let version = env!("CARGO_PKG_VERSION");
    let mut parts = version.split('.');
    let major: u64 = parts.next().and_then(|p| p.parse().ok()).unwrap_or(0);
    let minor: u64 = parts.next().and_then(|p| p.parse().ok()).unwrap_or(0);
    let patch: u64 = parts.next().and_then(|p| p.parse().ok()).unwrap_or(0);
    let packed = (major << 48) | (minor << 32) | (patch << 16);
    let version_quad = format!("{version}.0");

    let mut res = winresource::WindowsResource::new();
    res.set_icon(icon.to_str().expect("icon path must be valid UTF-8"));
    res.set("ProductName", "KakaoTalk Layout AdBlocker");
    res.set("FileDescription", "KakaoTalk Layout AdBlocker");
    res.set("CompanyName", "twbeatles");
    res.set("InternalName", "KakaoTalkLayoutAdBlocker_v11");
    res.set("OriginalFilename", "KakaoTalkLayoutAdBlocker_v11.exe");
    res.set("LegalCopyright", "Copyright (c) 2026 twbeatles");
    res.set("FileVersion", &version_quad);
    res.set("ProductVersion", &version_quad);
    res.set_version_info(winresource::VersionInfo::FILEVERSION, packed);
    res.set_version_info(winresource::VersionInfo::PRODUCTVERSION, packed);
    res.compile()
        .unwrap_or_else(|err| panic!("failed to embed Windows resources: {err}"));
}
