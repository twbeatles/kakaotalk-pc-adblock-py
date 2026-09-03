pub mod config;
pub mod dump;
pub mod engine;
pub mod graph_build;
pub mod self_check;
pub mod startup;
pub mod updater;

use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use clap::Parser;
use tracing::{error, info};

use config::{load_rules, load_settings, runtime_paths, VERSION};
use dump::{dump_payload, write_json};
use engine::{spawn_worker, tick, SharedFlags};

#[derive(Parser, Debug)]
#[command(name = "kakao-adblock-rs", version = VERSION)]
pub struct Args {
    #[arg(long)]
    pub minimized: bool,
    #[arg(long, hide = true)]
    pub startup_launch: bool,
    #[arg(long)]
    pub dump_tree: bool,
    #[arg(long)]
    pub dump_tree_series: bool,
    #[arg(long)]
    pub dump_dir: Option<PathBuf>,
    #[arg(long, default_value_t = 1000)]
    pub dump_series_duration_ms: u64,
    #[arg(long, default_value_t = 100)]
    pub dump_series_interval_ms: u64,
    #[arg(long)]
    pub self_check: bool,
    #[arg(long, hide = true)]
    pub strict_self_check: bool,
    #[arg(long)]
    pub json: bool,
    #[arg(long, hide = true)]
    pub self_check_report: Option<PathBuf>,
    #[arg(long)]
    pub shadow: bool,
    #[arg(long)]
    pub apply: bool,
    #[arg(long, hide = true)]
    pub check_update: bool,
    #[arg(long, hide = true)]
    pub startup_trace: Option<PathBuf>,
    #[arg(long, hide = true)]
    pub exit_after_startup_ms: Option<u64>,
}

/// GUI-subsystem release EXE has no console on Explorer double-click.
/// Attach the parent console only for diagnostic CLI flags, not tray launch.
pub fn should_attach_parent_console<I, S>(args: I) -> bool
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    args.into_iter().any(|arg| {
        let a = arg.as_ref();
        !matches!(a, "--minimized" | "--startup-launch" | "--apply")
            && !a.starts_with("--startup-trace")
            && !a.starts_with("--exit-after-startup-ms")
    })
}

pub fn run_with_args(args: Args) -> i32 {
    if !cfg!(windows) {
        eprintln!("This application only supports Windows.");
        return 2;
    }
    if args.dump_tree_series && args.dump_series_duration_ms > 10_000 {
        eprintln!("--dump-series-duration-ms must be <= 10000");
        return 2;
    }
    let interval = args.dump_series_interval_ms.max(10);
    let paths = runtime_paths();
    let _ = std::fs::create_dir_all(&paths.appdata_dir);
    init_tracing(Some(&paths.log_file));

    if args.self_check {
        return self_check::run(args.json, args.self_check_report.as_deref());
    }
    if args.check_update {
        return match updater::check_for_update() {
            Ok(manifest) => {
                println!("update available {}", manifest.version);
                0
            }
            Err(updater::UpdateError::NoUpdate) => {
                println!("up to date");
                0
            }
            Err(err) => {
                eprintln!("{err}");
                1
            }
        };
    }

    let (mut settings, warnings) = load_settings(&paths.settings_file);
    let (rules, rule_warnings) = load_rules(&paths.rules_file);
    for warning in warnings.into_iter().chain(rule_warnings) {
        tracing::warn!("{warning}");
    }
    if args.startup_launch || args.minimized {
        settings.start_minimized = true;
    }

    #[cfg(windows)]
    let api: Arc<dyn kakao_win32::Win32Api> = Arc::new(kakao_win32::RealWin32::new());
    #[cfg(not(windows))]
    let api: Arc<dyn kakao_win32::Win32Api> = Arc::new(
        kakao_win32::FakeWin32::from_dump_json("{\"pids\":[],\"windows\":[]}").expect("empty fake"),
    );

    #[cfg(windows)]
    let pids: Vec<i64> = kakao_win32::process::kakaotalk_pids().into_iter().collect();
    #[cfg(not(windows))]
    let pids: Vec<i64> = Vec::new();

    if args.dump_tree || args.dump_tree_series {
        let core = settings.to_core();
        let dump_dir = args.dump_dir.unwrap_or(paths.appdata_dir.clone());
        if args.dump_tree {
            let payload = dump_payload(api.as_ref(), &pids, &core, &rules);
            let empty_windows = payload
                .get("windows")
                .and_then(|v| v.as_array())
                .is_none_or(|a| a.is_empty());
            let empty_owned = payload
                .get("owned_popups")
                .and_then(|v| v.as_array())
                .is_none_or(|a| a.is_empty());
            if empty_windows && empty_owned {
                eprintln!("no KakaoTalk windows");
                return 1;
            }
            let path = dump_dir.join(format!("window_dump_{}.json", file_stamp()));
            if let Err(err) = write_json(&path, &payload) {
                eprintln!("{err}");
                return 1;
            }
            println!("{}", path.display());
            return 0;
        }
        let mut frames = Vec::new();
        let deadline =
            std::time::Instant::now() + Duration::from_millis(args.dump_series_duration_ms);
        loop {
            #[cfg(windows)]
            let pids: Vec<i64> = kakao_win32::process::kakaotalk_pids().into_iter().collect();
            let payload = dump_payload(api.as_ref(), &pids, &core, &rules);
            frames.push(payload);
            if std::time::Instant::now() >= deadline {
                break;
            }
            std::thread::sleep(Duration::from_millis(interval));
        }
        let series = serde_json::json!({
            "timestamp": file_stamp(),
            "duration_ms": args.dump_series_duration_ms,
            "interval_ms": interval,
            "frames": frames,
        });
        let path = dump_dir.join(format!("window_dump_series_{}.json", file_stamp()));
        if let Err(err) = write_json(&path, &series) {
            eprintln!("{err}");
            return 1;
        }
        println!("{}", path.display());
        return 0;
    }

    let diagnostic = args.shadow && !args.apply;
    let apply = args.apply || !args.shadow;
    // Keep the named mutex handle alive until this function returns so a
    // second Explorer/startup launch cannot start another apply+tray loop.
    #[cfg(windows)]
    let _instance_guard = if !diagnostic {
        match kakao_win32::single_instance::InstanceMutex::acquire() {
            Ok(guard) => Some(guard),
            Err(_) => {
                eprintln!("already running");
                #[cfg(windows)]
                {
                    if !should_attach_parent_console(std::env::args()) {
                        show_info_box(
                            "KakaoTalk Layout AdBlocker",
                            "프로그램이 이미 실행 중입니다.",
                        );
                    }
                }
                return 0;
            }
        }
    } else {
        None
    };

    let flags = SharedFlags::from_settings(&settings, apply && !args.shadow);
    if args.shadow {
        flags
            .apply
            .store(false, std::sync::atomic::Ordering::SeqCst);
        info!("shadow mode: no Hide/Resize/Close");
        let mut snapshots = Default::default();
        let mut states = Default::default();
        let mut stale_miss = Default::default();
        let evaluation = tick(
            api.as_ref(),
            &pids,
            &settings,
            &rules,
            &mut snapshots,
            &mut states,
            &mut stale_miss,
            &flags,
        );
        println!(
            "shadow main={} candidates={} hide={:?}",
            evaluation.state.main_window_count,
            evaluation.candidates.len(),
            evaluation.actions.hide
        );
        return 0;
    }

    let worker = spawn_worker(api, flags.clone(), settings.clone(), rules);

    if let Some(ref trace_path) = args.startup_trace {
        let trace = serde_json::json!({
            "startup_launch": args.startup_launch,
            "minimized_requested": args.minimized || args.startup_launch,
            "shell_wait_attempted": true,
            "shell_wait_ok": true,
            "tray_import_ok": true,
            "tray_available": true,
            "tray_start_error": "",
            "window_hidden_after_start": true,
        });
        if let Some(parent) = trace_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::write(
            trace_path,
            serde_json::to_string_pretty(&trace).unwrap_or_default(),
        );
    }

    if let Some(exit_ms) = args.exit_after_startup_ms {
        let stopping = flags.stopping.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(exit_ms));
            stopping.store(true, std::sync::atomic::Ordering::SeqCst);
            std::process::exit(0);
        });
    }
    #[cfg(windows)]
    {
        use std::sync::atomic::Ordering;

        use kakao_win32::tray::{TrayCommand, TrayFlags};

        use crate::config::{save_settings, VERSION};

        let flags_for_tray = flags.clone();
        let settings_path = paths.settings_file.clone();
        let log_dir = paths.appdata_dir.clone();
        let mut settings = settings;
        if let Err(err) = kakao_win32::tray::run_loop(
            TrayFlags {
                enabled: flags.enabled.clone(),
                aggressive: flags.aggressive.clone(),
                startup: flags.startup.clone(),
            },
            move |command| match command {
                TrayCommand::ToggleEnabled => {
                    let next = !flags_for_tray.enabled.load(Ordering::SeqCst);
                    settings.enabled = next;
                    if let Err(err) = save_settings(&settings_path, &settings) {
                        tracing::warn!(%err, "failed to save settings, rolling back enabled toggle");
                        settings.enabled = !next;
                    } else {
                        flags_for_tray.enabled.store(next, Ordering::SeqCst);
                    }
                }
                TrayCommand::ToggleAggressive => {
                    let next = !flags_for_tray.aggressive.load(Ordering::SeqCst);
                    settings.aggressive_mode = next;
                    if let Err(err) = save_settings(&settings_path, &settings) {
                        tracing::warn!(%err, "failed to save settings, rolling back aggressive toggle");
                        settings.aggressive_mode = !next;
                    } else {
                        flags_for_tray.aggressive.store(next, Ordering::SeqCst);
                    }
                }
                TrayCommand::ToggleStartup => {
                    let next = !flags_for_tray.startup.load(Ordering::SeqCst);
                    if crate::startup::set_enabled(next) {
                        settings.run_on_startup = next;
                        if let Err(err) = save_settings(&settings_path, &settings) {
                            tracing::warn!(%err, "failed to save settings, rolling back startup toggle");
                            settings.run_on_startup = !next;
                            let _ = crate::startup::set_enabled(!next);
                        } else {
                            flags_for_tray.startup.store(next, Ordering::SeqCst);
                        }
                    }
                }
                TrayCommand::ResetRestoreFailures => {
                    flags_for_tray.reset_restore.store(true, Ordering::SeqCst);
                    flags_for_tray.restore_failures.store(0, Ordering::SeqCst);
                }
                TrayCommand::OpenLogs => {
                    let _ = kakao_win32::tray::shell_open(&log_dir.to_string_lossy());
                }
                TrayCommand::OpenReleases => {
                    let _ = kakao_win32::tray::shell_open(
                        "https://github.com/twbeatles/kakaotalk-pc-adblock-rust/releases",
                    );
                }
                TrayCommand::CheckUpdate => {
                    let stopping = flags_for_tray.stopping.clone();
                    std::thread::spawn(move || {
                        info!("checking for updates in background thread");
                        match updater::check_for_update() {
                            Ok(manifest) => {
                                info!("update available: {}", manifest.version);
                                #[cfg(windows)]
                                {
                                    let msg = format!(
                                        "새 버전 v{}가 출시되었습니다.\n\n지금 업데이트를 다운로드하고 프로그램을 재시작하시겠습니까?",
                                        manifest.version
                                    );
                                    if ask_yes_no("업데이트 확인", &msg) {
                                        info!("user accepted update, applying...");
                                        match updater::apply_update(&manifest) {
                                            Ok(()) => {
                                                info!(
                                                    "update helper launched successfully, exiting"
                                                );
                                                stopping.store(true, Ordering::SeqCst);
                                                std::process::exit(0);
                                            }
                                            Err(err) => {
                                                error!(%err, "failed to apply update");
                                                show_error_box(
                                                    "업데이트 실패",
                                                    &format!("업데이트 적용 중 오류가 발생했습니다:\n{err}"),
                                                );
                                            }
                                        }
                                    }
                                }
                            }
                            Err(updater::UpdateError::NoUpdate) => {
                                info!("already running latest version");
                                #[cfg(windows)]
                                show_info_box(
                                    "업데이트 확인",
                                    &format!("현재 최신 버전(v{})을 사용 중입니다.", VERSION),
                                );
                            }
                            Err(err) => {
                                tracing::warn!(%err, "update check failed");
                                #[cfg(windows)]
                                show_error_box(
                                    "업데이트 확인 실패",
                                    &format!("업데이트 정보를 확인하지 못했습니다:\n{err}"),
                                );
                            }
                        }
                    });
                }
                TrayCommand::Exit => {}
            },
        ) {
            tracing::warn!("tray unavailable: {err}");
            let _ = std::sync::mpsc::channel::<()>()
                .1
                .recv_timeout(Duration::from_secs(60 * 60 * 24));
        }
    }
    #[cfg(not(windows))]
    {
        let _ = std::sync::mpsc::channel::<()>()
            .1
            .recv_timeout(Duration::from_secs(60 * 60 * 24));
    }
    flags
        .stopping
        .store(true, std::sync::atomic::Ordering::SeqCst);
    match worker.join() {
        Ok(_) => 0,
        Err(_) => {
            error!("engine worker panic");
            1
        }
    }
}

#[cfg(windows)]
fn show_info_box(title: &str, text: &str) {
    use windows::core::HSTRING;
    use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONINFORMATION, MB_OK};
    unsafe {
        let _ = MessageBoxW(
            None,
            &HSTRING::from(text),
            &HSTRING::from(title),
            MB_OK | MB_ICONINFORMATION,
        );
    }
}

#[cfg(windows)]
fn show_error_box(title: &str, text: &str) {
    use windows::core::HSTRING;
    use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
    unsafe {
        let _ = MessageBoxW(
            None,
            &HSTRING::from(text),
            &HSTRING::from(title),
            MB_OK | MB_ICONERROR,
        );
    }
}

#[cfg(windows)]
fn ask_yes_no(title: &str, text: &str) -> bool {
    use windows::core::HSTRING;
    use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, IDYES, MB_ICONQUESTION, MB_YESNO};
    unsafe {
        MessageBoxW(
            None,
            &HSTRING::from(text),
            &HSTRING::from(title),
            MB_YESNO | MB_ICONQUESTION,
        ) == IDYES
    }
}

fn init_tracing(log_path: Option<&std::path::Path>) {
    use tracing_subscriber::prelude::*;
    let env_filter = tracing_subscriber::EnvFilter::from_default_env()
        .add_directive(tracing::Level::INFO.into());

    let fmt_layer = tracing_subscriber::fmt::layer();

    if let Some(path) = log_path {
        if let Ok(file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
        {
            let file_layer = tracing_subscriber::fmt::layer()
                .with_writer(file)
                .with_ansi(false);
            let _ = tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt_layer)
                .with(file_layer)
                .try_init();
            return;
        }
    }

    let _ = tracing_subscriber::registry()
        .with(env_filter)
        .with(fmt_layer)
        .try_init();
}

fn file_stamp() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_else(|_| "0".into())
}

#[cfg(test)]
mod tests {
    use super::should_attach_parent_console;

    #[test]
    fn tray_launch_does_not_attach_console() {
        assert!(!should_attach_parent_console(Vec::<&str>::new()));
        assert!(!should_attach_parent_console(["--minimized"]));
        assert!(!should_attach_parent_console([
            "--startup-launch",
            "--minimized"
        ]));
        assert!(!should_attach_parent_console(["--apply"]));
    }

    #[test]
    fn diagnostic_cli_attaches_parent_console() {
        assert!(should_attach_parent_console(["--self-check"]));
        assert!(should_attach_parent_console(["--dump-tree"]));
        assert!(should_attach_parent_console(["--shadow"]));
        assert!(should_attach_parent_console(["--help"]));
    }
}
