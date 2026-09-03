#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use clap::Parser;
use kakao_updater::update_executable;
use std::path::PathBuf;
use std::time::Duration;
use tracing::{error, info};

#[derive(Parser, Debug)]
#[command(
    name = "kakao-updater",
    about = "KakaoTalk Layout AdBlocker updater helper"
)]
struct Cli {
    #[arg(long, default_value_t = 0)]
    pid: u32,

    #[arg(long)]
    current: PathBuf,

    #[arg(long)]
    replacement: PathBuf,

    #[arg(long, default_value_t = 30)]
    timeout_secs: u64,

    #[arg(long, default_value_t = false)]
    no_relaunch: bool,
}

fn show_error_dialog(message: &str) {
    #[cfg(windows)]
    {
        use windows::core::HSTRING;
        use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
        let text = HSTRING::from(message);
        let title = HSTRING::from("업데이트 실패");
        unsafe {
            let _ = MessageBoxW(None, &text, &title, MB_OK | MB_ICONERROR);
        }
    }
    #[cfg(not(windows))]
    {
        eprintln!("Update Error: {message}");
    }
}

fn main() {
    let _ = tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .try_init();

    let args = Cli::parse();
    let relaunch = !args.no_relaunch;

    match update_executable(
        &args.current,
        &args.replacement,
        args.pid,
        Duration::from_secs(args.timeout_secs),
        relaunch,
    ) {
        Ok(()) => {
            info!("update helper finished successfully");
            std::process::exit(0);
        }
        Err(err) => {
            error!(%err, "update helper failed");
            show_error_dialog(&err.to_string());
            std::process::exit(1);
        }
    }
}
