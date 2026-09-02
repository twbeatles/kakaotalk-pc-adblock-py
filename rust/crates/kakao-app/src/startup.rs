use std::env;
use std::path::PathBuf;

pub const STARTUP_NAME: &str = "KakaoTalkAdBlockerLayout";
pub const PACKAGED_EXE_NAME: &str = "KakaoTalkLayoutAdBlocker_v11.exe";

pub fn build_command() -> String {
    let exe = env::current_exe().unwrap_or_else(|_| PathBuf::from(PACKAGED_EXE_NAME));
    format!("\"{}\" --startup-launch --minimized", exe.display())
}

pub fn registration_health(current: Option<&str>, expected: &str) -> &'static str {
    match current {
        None => "missing",
        Some(cmd) if cmd == expected => "healthy",
        Some(cmd)
            if cmd
                .to_ascii_lowercase()
                .contains(&PACKAGED_EXE_NAME.to_ascii_lowercase()) =>
        {
            "source-compatible"
        }
        Some(_) => "custom",
    }
}

pub fn set_enabled(enabled: bool) -> bool {
    #[cfg(windows)]
    {
        if enabled {
            kakao_win32::startup::set_run_command(&build_command())
        } else {
            kakao_win32::startup::delete_run_command()
        }
    }
    #[cfg(not(windows))]
    {
        let _ = enabled;
        false
    }
}

pub fn current_command() -> Option<String> {
    #[cfg(windows)]
    {
        kakao_win32::startup::get_run_command()
    }
    #[cfg(not(windows))]
    {
        None
    }
}
