use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use kakao_core::{evaluate_graph, Evaluation, LayoutRules, WindowGraph, WindowIdentity};
use kakao_win32::api::{
    Win32Api, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOZORDER, SW_HIDE, SW_SHOW, WM_CLOSE,
};
use tracing::{info, warn};

use crate::config::AppSettings;
use crate::graph_build::build_graph;

#[derive(Clone, Debug)]
pub struct RestoreSnapshot {
    pub identity: WindowIdentity,
    pub was_visible: bool,
    pub rect: Option<kakao_core::Rect>,
}

pub struct SharedFlags {
    pub enabled: Arc<AtomicBool>,
    pub aggressive: Arc<AtomicBool>,
    pub stopping: Arc<AtomicBool>,
    pub apply: Arc<AtomicBool>,
    pub startup: Arc<AtomicBool>,
    pub reset_restore: Arc<AtomicBool>,
    pub restore_failures: Arc<AtomicU32>,
}

impl SharedFlags {
    pub fn from_settings(settings: &AppSettings, apply: bool) -> Arc<Self> {
        Arc::new(Self {
            enabled: Arc::new(AtomicBool::new(settings.enabled)),
            aggressive: Arc::new(AtomicBool::new(settings.aggressive_mode)),
            stopping: Arc::new(AtomicBool::new(false)),
            apply: Arc::new(AtomicBool::new(apply)),
            startup: Arc::new(AtomicBool::new(settings.run_on_startup)),
            reset_restore: Arc::new(AtomicBool::new(false)),
            restore_failures: Arc::new(AtomicU32::new(0)),
        })
    }
}

pub fn capture_snapshot(
    api: &dyn Win32Api,
    graph: &WindowGraph,
    hwnd: i64,
) -> Option<RestoreSnapshot> {
    let node = graph.get(hwnd)?;
    Some(RestoreSnapshot {
        identity: node.identity(),
        was_visible: api.is_window_visible(hwnd),
        rect: api.get_window_rect(hwnd).or(node.rect),
    })
}

fn identity_matches(api: &dyn Win32Api, identity: &WindowIdentity) -> bool {
    api.is_window(identity.hwnd)
        && api.get_window_thread_process_id(identity.hwnd) == identity.pid
        && api.get_class_name(identity.hwnd) == identity.class_name
}

pub fn apply_evaluation(
    api: &dyn Win32Api,
    graph: &WindowGraph,
    evaluation: &Evaluation,
    snapshots: &mut HashMap<WindowIdentity, RestoreSnapshot>,
    pids: &HashSet<i64>,
    flags: &SharedFlags,
) {
    if flags.stopping.load(Ordering::SeqCst)
        || !flags.enabled.load(Ordering::SeqCst)
        || !flags.apply.load(Ordering::SeqCst)
    {
        return;
    }
    let precheck = |hwnd: i64| -> bool {
        if flags.stopping.load(Ordering::SeqCst) {
            return false;
        }
        let Some(node) = graph.get(hwnd) else {
            return false;
        };
        if !pids.contains(&node.pid) {
            return false;
        }
        identity_matches(api, &node.identity())
    };

    for hwnd in &evaluation.actions.close {
        if !precheck(*hwnd) {
            continue;
        }
        let _ = api.send_message_timeout(*hwnd, WM_CLOSE, 0, 0, 500);
    }
    for hwnd in &evaluation.actions.hide {
        if !precheck(*hwnd) {
            continue;
        }
        if let Some(snap) = capture_snapshot(api, graph, *hwnd) {
            snapshots.entry(snap.identity.clone()).or_insert(snap);
        }
        let _ = api.show_window(*hwnd, SW_HIDE);
    }
    for pos in &evaluation.actions.set_pos {
        if pos.len() < 5 {
            continue;
        }
        let hwnd = pos[0];
        if !precheck(hwnd) {
            continue;
        }
        if let Some(snap) = capture_snapshot(api, graph, hwnd) {
            snapshots.entry(snap.identity.clone()).or_insert(snap);
        }
        // View resize is size-only (Python SWP_NOMOVE). Zero-size popup
        // fallback must still be allowed to move to 0,0.
        let mut flags = SWP_NOZORDER | SWP_NOACTIVATE;
        if pos[3] > 0 && pos[4] > 0 {
            flags |= SWP_NOMOVE;
        }
        let _ = api.set_window_pos(
            hwnd,
            pos[1] as i32,
            pos[2] as i32,
            pos[3] as i32,
            pos[4] as i32,
            flags,
        );
    }
}

pub fn restore_all(
    api: &dyn Win32Api,
    snapshots: &mut HashMap<WindowIdentity, RestoreSnapshot>,
) -> (u32, String) {
    let mut failures = 0u32;
    let mut last_error = String::new();
    let pending: Vec<_> = snapshots.drain().map(|(_, snap)| snap).collect();
    for snap in pending {
        if !identity_matches(api, &snap.identity) {
            continue;
        }
        if snap.was_visible && !api.show_window(snap.identity.hwnd, SW_SHOW) {
            failures += 1;
            last_error = format!("restore show failed hwnd={}", snap.identity.hwnd);
        }
        if let Some(rect) = snap.rect {
            if !api.set_window_pos(
                snap.identity.hwnd,
                rect.left,
                rect.top,
                rect.width(),
                rect.height(),
                SWP_NOZORDER | SWP_NOACTIVATE,
            ) {
                failures += 1;
                last_error = format!("restore pos failed hwnd={}", snap.identity.hwnd);
            }
        }
    }
    (failures, last_error)
}

pub fn tick(
    api: &dyn Win32Api,
    pids: &[i64],
    settings: &AppSettings,
    rules: &LayoutRules,
    snapshots: &mut HashMap<WindowIdentity, RestoreSnapshot>,
    flags: &SharedFlags,
) -> Evaluation {
    let mut core = settings.to_core();
    core.enabled = flags.enabled.load(Ordering::SeqCst);
    core.aggressive_mode = flags.aggressive.load(Ordering::SeqCst);
    let graph = build_graph(api, pids);
    let evaluation = evaluate_graph(&graph, &core, rules);
    if flags.apply.load(Ordering::SeqCst) && core.enabled {
        let pid_set: HashSet<i64> = pids.iter().copied().collect();
        apply_evaluation(api, &graph, &evaluation, snapshots, &pid_set, flags);
    } else {
        for candidate in &evaluation.candidates {
            info!(
                hwnd = candidate.hwnd,
                pid = candidate.pid,
                class = %candidate.class,
                decision = %candidate.decision,
                action = %candidate.action,
                "shadow"
            );
        }
    }
    evaluation
}

pub fn spawn_worker(
    api: Arc<dyn Win32Api>,
    flags: Arc<SharedFlags>,
    settings: AppSettings,
    rules: LayoutRules,
) -> thread::JoinHandle<HashMap<WindowIdentity, RestoreSnapshot>> {
    thread::spawn(move || {
        let mut snapshots = HashMap::new();
        let mut last_pids: HashSet<i64> = HashSet::new();
        let mut burst_left = 0u32;
        let mut last_full = Instant::now() - Duration::from_secs(10);
        let mut was_enabled = flags.enabled.load(Ordering::SeqCst);
        #[cfg(windows)]
        let hook = kakao_win32::event_hook::EventHook::install();
        while !flags.stopping.load(Ordering::SeqCst) {
            if flags.reset_restore.swap(false, Ordering::SeqCst) {
                flags.restore_failures.store(0, Ordering::SeqCst);
            }
            let enabled_now = flags.enabled.load(Ordering::SeqCst);
            if was_enabled && !enabled_now && flags.apply.load(Ordering::SeqCst) {
                let (failures, err) = restore_all(api.as_ref(), &mut snapshots);
                if failures > 0 {
                    flags.restore_failures.fetch_add(failures, Ordering::SeqCst);
                    warn!(failures, last_error = %err, "restore on disable had failures");
                }
            }
            was_enabled = enabled_now;
            #[cfg(windows)]
            let pids: Vec<i64> = kakao_win32::process::kakaotalk_pids().into_iter().collect();
            #[cfg(not(windows))]
            let pids: Vec<i64> = Vec::new();
            let pid_set: HashSet<i64> = pids.iter().copied().collect();
            if !pid_set.is_empty() && pid_set != last_pids {
                burst_left = settings.burst_scan_iterations.max(1);
                last_pids = pid_set;
            }
            let mut events = Vec::new();
            #[cfg(windows)]
            if let Some(hook) = hook.as_ref() {
                events = hook.drain();
            }
            let due_recon = last_full.elapsed()
                >= Duration::from_millis(settings.idle_poll_interval_ms.max(2000) as u64);
            let due_burst = burst_left > 0;
            if events.is_empty() && !due_recon && !due_burst {
                #[cfg(windows)]
                if let Some(hook) = hook.as_ref() {
                    hook.wait_message(Duration::from_millis(80));
                    continue;
                }
                #[cfg(not(windows))]
                {
                    thread::sleep(Duration::from_millis(80));
                    continue;
                }
            }
            if !events.is_empty() {
                thread::sleep(Duration::from_millis(80));
                #[cfg(windows)]
                if let Some(hook) = hook.as_ref() {
                    let _ = hook.drain();
                }
            }
            let _ = tick(
                api.as_ref(),
                &pids,
                &settings,
                &rules,
                &mut snapshots,
                &flags,
            );
            last_full = Instant::now();
            if burst_left > 0 {
                burst_left -= 1;
                thread::sleep(Duration::from_millis(
                    settings.burst_scan_interval_ms.max(10) as u64,
                ));
            }
        }
        if flags.apply.load(Ordering::SeqCst) {
            let (failures, err) = restore_all(api.as_ref(), &mut snapshots);
            if failures > 0 {
                flags.restore_failures.fetch_add(failures, Ordering::SeqCst);
                warn!(failures, last_error = %err, "restore on stop had failures");
            }
        }
        snapshots
    })
}
