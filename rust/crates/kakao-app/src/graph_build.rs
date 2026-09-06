use std::collections::HashSet;

use kakao_core::{Hwnd, WindowGraph, WindowNode};
use kakao_win32::Win32Api;

pub fn build_graph(api: &dyn Win32Api, pids: &[i64]) -> WindowGraph {
    if pids.is_empty() {
        return WindowGraph::empty(Vec::new());
    }
    let pid_set: HashSet<i64> = pids.iter().copied().collect();
    let mut top_level = Vec::new();
    api.enum_windows(&mut |hwnd| {
        let pid = api.get_window_thread_process_id(hwnd);
        if pid_set.contains(&pid) {
            top_level.push((hwnd, pid));
        }
        true
    });
    top_level.sort_unstable_by_key(|&(hwnd, _)| hwnd);
    let mut graph = WindowGraph::empty(pids.to_vec());
    let mut visited = HashSet::new();
    for (hwnd, pid) in top_level {
        load_tree(api, &mut graph, hwnd, None, pid, &mut visited);
    }
    graph
}

fn load_tree(
    api: &dyn Win32Api,
    graph: &mut WindowGraph,
    hwnd: Hwnd,
    structural_parent: Option<Hwnd>,
    pid: i64,
    visited: &mut HashSet<Hwnd>,
) {
    if !visited.insert(hwnd) || !api.is_window(hwnd) {
        return;
    }
    let class_name = api.get_class_name(hwnd);
    let title = api.get_window_text_result(hwnd);
    let win32_parent = api.get_parent(hwnd);
    let owner = if structural_parent.is_none() && win32_parent != 0 {
        Some(win32_parent)
    } else {
        None
    };
    graph.insert_node(WindowNode {
        hwnd,
        pid,
        class_name,
        title,
        structural_parent,
        owner,
        rect: api.get_window_rect(hwnd),
        visible: api.is_window_visible(hwnd),
    });
    // EnumChildWindows returns every descendant. Keep only windows whose
    // GetParent is this hwnd so graph edges match the real child tree.
    // Owned popups are top-level (not child windows); their owner is recorded
    // on the node above and is not a structural parent edge.
    let mut enumerated = Vec::new();
    api.enum_child_windows(hwnd, &mut |child| {
        enumerated.push(child);
        true
    });
    let mut children = Vec::new();
    for child in enumerated {
        if api.get_parent(child) == hwnd {
            children.push(child);
        }
    }
    for &child in &children {
        load_tree(api, graph, child, Some(hwnd), pid, visited);
    }
    graph.set_children(hwnd, children);
}
