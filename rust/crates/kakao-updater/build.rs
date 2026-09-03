fn main() {
    if std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default() != "windows" {
        return;
    }

    let manifest = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>"#;

    let mut res = winresource::WindowsResource::new();
    res.set_manifest(manifest);
    res.set("ProductName", "KakaoTalk Layout AdBlocker Updater");
    res.set(
        "FileDescription",
        "Self-update helper for KakaoTalk Layout AdBlocker",
    );
    res.set("OriginalFilename", "kakao-updater.exe");
    res.compile()
        .unwrap_or_else(|err| panic!("failed to compile updater resources: {err}"));
}
