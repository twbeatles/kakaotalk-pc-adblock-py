use kakao_app::self_check;

fn isolated_appdata() -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "kakao_self_check_appdata_{}_{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    std::env::set_var("APPDATA", &dir);
    dir
}

#[test]
fn report_path_directory_returns_nonzero() {
    let _appdata = isolated_appdata();
    let dir = std::env::temp_dir().join(format!(
        "kakao_self_check_dir_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    let code = self_check::run(false, Some(dir.as_path()), false);
    assert_ne!(code, 0, "writing a report onto a directory must fail");
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn report_write_success_is_zero_when_core_ok() {
    let _appdata = isolated_appdata();
    let dir = std::env::temp_dir().join(format!(
        "kakao_self_check_ok_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    let report = dir.join("report.json");
    let code = self_check::run(false, Some(report.as_path()), false);
    if cfg!(windows) {
        assert_eq!(code, 0);
        assert!(report.is_file());
    }
    let _ = std::fs::remove_dir_all(&dir);
}
