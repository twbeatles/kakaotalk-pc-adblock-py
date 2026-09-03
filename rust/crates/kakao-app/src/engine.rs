use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use kakao_core::{
    evaluate_graph_with_states, CandidateState, Evaluation, LayoutRules, WindowGraph,
    WindowIdentity,
};
use kakao_win32::api::{
    Win32Api, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOZORDER, SW_HIDE, SW_SHOW, WM_CLOSE,
};
use tracing::{info, warn};

use crate::config::AppSettings;
use crate::graph_build::build_graph;

const RESTORE_MISS_THRESHOLD: u32 = 2;

#[derive(Clone, Debug)]
pub struct RestoreSnapshot {
    pub identity: WindowIdentity,
    pub was_visible: bool,
    pub rect: Option<kakao_core::Rect>,
    pub top_level: bool,
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
        top_level: node.structural_parent.is_none(),
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
        // View resize is size-only (Python SWP_NOMOVE). Zero-size popup
        // fallback must still be allowed to move to 0,0.
        let width = pos[3];
        let height = pos[4];
        let is_view_resize = width > 0 && height > 0;
        // Python stop() restores hidden/zero-sized windows only. Snapshotting
        // OnlineMainView resize and replaying GetWindowRect through
        // SetWindowPos treats screen coordinates as parent-relative, which
        // shoves the main view off-canvas and blacks out KakaoTalk.
        if !is_view_resize {
            if let Some(snap) = capture_snapshot(api, graph, hwnd) {
                snapshots.entry(snap.identity.clone()).or_insert(snap);
            }
        }
        let mut flags = SWP_NOZORDER | SWP_NOACTIVATE;
        if is_view_resize {
            flags |= SWP_NOMOVE;
        }
        let _ = api.set_window_pos(
            hwnd,
            pos[1] as i32,
            pos[2] as i32,
            width as i32,
            height as i32,
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
        if !restore_snapshot(api, &snap, &mut last_error) {
            failures += 1;
        }
    }
    (failures, last_error)
}

fn restore_snapshot(api: &dyn Win32Api, snap: &RestoreSnapshot, last_error: &mut String) -> bool {
    let mut ok = true;
    if let Some(rect) = snap.rect {
        if rect.width() > 0 && rect.height() > 0 {
            let mut flags = SWP_NOZORDER | SWP_NOACTIVATE;
            if !snap.top_level {
                flags |= SWP_NOMOVE;
            }
            if !api.set_window_pos(
                snap.identity.hwnd,
                rect.left,
                rect.top,
                rect.width(),
                rect.height(),
                flags,
            ) {
                ok = false;
                *last_error = format!("restore pos failed hwnd={}", snap.identity.hwnd);
            }
        }
    }
    if snap.was_visible {
        let _ = api.show_window(snap.identity.hwnd, SW_SHOW);
        if !api.is_window_visible(snap.identity.hwnd) {
            ok = false;
            *last_error = format!("restore show failed hwnd={}", snap.identity.hwnd);
        }
    }
    ok
}

fn restore_stale_hidden(
    api: &dyn Win32Api,
    snapshots: &mut HashMap<WindowIdentity, RestoreSnapshot>,
    matched: &HashSet<WindowIdentity>,
    stale_miss: &mut HashMap<WindowIdentity, u32>,
) -> (u32, String) {
    let mut failures = 0u32;
    let mut last_error = String::new();
    let pending: Vec<WindowIdentity> = snapshots.keys().cloned().collect();
    for identity in pending {
        if matched.contains(&identity) {
            stale_miss.remove(&identity);
            continue;
        }
        let misses = stale_miss.entry(identity.clone()).or_insert(0);
        *misses = misses.saturating_add(1);
        if *misses < RESTORE_MISS_THRESHOLD {
            continue;
        }
        let Some(snap) = snapshots.remove(&identity) else {
            continue;
        };
        stale_miss.remove(&identity);
        if !identity_matches(api, &snap.identity) {
            continue;
        }
        if !restore_snapshot(api, &snap, &mut last_error) {
            failures += 1;
        }
    }
    (failures, last_error)
}

#[allow(clippy::too_many_arguments)]
pub fn tick(
    api: &dyn Win32Api,
    pids: &[i64],
    settings: &AppSettings,
    rules: &LayoutRules,
    snapshots: &mut HashMap<WindowIdentity, RestoreSnapshot>,
    states: &mut HashMap<WindowIdentity, CandidateState>,
    stale_miss: &mut HashMap<WindowIdentity, u32>,
    flags: &SharedFlags,
) -> Evaluation {
    let mut core = settings.to_core();
    core.enabled = flags.enabled.load(Ordering::SeqCst);
    core.aggressive_mode = flags.aggressive.load(Ordering::SeqCst);
    let graph = build_graph(api, pids);
    let evaluation = evaluate_graph_with_states(&graph, &core, rules, states);
    if flags.apply.load(Ordering::SeqCst) && core.enabled {
        let pid_set: HashSet<i64> = pids.iter().copied().collect();
        apply_evaluation(api, &graph, &evaluation, snapshots, &pid_set, flags);
        let matched = matched_identities(&graph, &evaluation);
        let (failures, err) = restore_stale_hidden(api, snapshots, &matched, stale_miss);
        if failures > 0 {
            flags.restore_failures.fetch_add(failures, Ordering::SeqCst);
            warn!(failures, last_error = %err, "stale hide restore had failures");
        }
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

fn matched_identities(graph: &WindowGraph, evaluation: &Evaluation) -> HashSet<WindowIdentity> {
    let mut matched = HashSet::new();
    let mut push = |hwnd: i64| {
        if let Some(node) = graph.get(hwnd) {
            matched.insert(node.identity());
        }
    };
    for hwnd in &evaluation.actions.hide {
        push(*hwnd);
    }
    for hwnd in &evaluation.actions.close {
        push(*hwnd);
    }
    for pos in &evaluation.actions.set_pos {
        if pos.len() >= 5 && (pos[3] <= 0 || pos[4] <= 0) {
            push(pos[0]);
        }
    }
    matched
}

pub fn spawn_worker(
    api: Arc<dyn Win32Api>,
    flags: Arc<SharedFlags>,
    settings: AppSettings,
    rules: LayoutRules,
) -> thread::JoinHandle<HashMap<WindowIdentity, RestoreSnapshot>> {
    thread::spawn(move || {
        let mut snapshots = HashMap::new();
        let mut states = HashMap::new();
        let mut stale_miss = HashMap::new();
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
            if !enabled_now {
                thread::sleep(Duration::from_millis(1000));
                continue;
            }
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
            let idle_ms = u64::from(settings.idle_poll_interval_ms.max(200));
            let active_ms = u64::from(settings.poll_interval_ms.max(50));
            let due_recon = last_full.elapsed() >= Duration::from_millis(idle_ms);
            let due_burst = burst_left > 0;
            if events.is_empty() && !due_recon && !due_burst {
                #[cfg(windows)]
                if let Some(hook) = hook.as_ref() {
                    hook.wait_message(Duration::from_millis(80));
                    continue;
                }
                let wait = if pids.is_empty() { idle_ms } else { active_ms };
                thread::sleep(Duration::from_millis(wait));
                continue;
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
                &mut states,
                &mut stale_miss,
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
