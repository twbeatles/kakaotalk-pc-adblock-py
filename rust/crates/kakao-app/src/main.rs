#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

use clap::Parser;
use kakao_app::{run_with_args, should_attach_parent_console, Args};

fn main() {
    #[cfg(windows)]
    if should_attach_parent_console(std::env::args().skip(1)) {
        kakao_win32::attach_parent_console();
    }
    std::process::exit(run_with_args(Args::parse()));
}
