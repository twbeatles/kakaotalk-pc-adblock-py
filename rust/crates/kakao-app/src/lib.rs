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
    #[arg(long)]
    pub shadow: bool,
    #[arg(long)]
    pub apply: bool,
    #[arg(long, hide = true)]
    pub check_update: bool,
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
    init_tracing();

    if args.self_check {
        return self_check::run(args.json);
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

    let paths = runtime_paths();
    let _ = std::fs::create_dir_all(&paths.appdata_dir);
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
    if !diagnostic {
        #[cfg(windows)]
        {
            if kakao_win32::single_instance::InstanceMutex::acquire().is_err() {
                eprintln!("already running");
                return 0;
            }
        }
    }

    let flags = SharedFlags::from_settings(&settings, apply && !args.shadow);
    if args.shadow {
        flags
            .apply
            .store(false, std::sync::atomic::Ordering::SeqCst);
        info!("shadow mode: no Hide/Resize/Close");
        let mut snapshots = Default::default();
        let evaluation = tick(
            api.as_ref(),
            &pids,
            &settings,
            &rules,
            &mut snapshots,
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

    let worker = spawn_worker(api, flags.clone(), settings, rules);
    let _ = std::sync::mpsc::channel::<()>()
        .1
        .recv_timeout(Duration::from_secs(60 * 60 * 24));
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

fn init_tracing() {
    let _ = tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .try_init();
}

fn file_stamp() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_else(|_| "0".into())
}
