use std::collections::HashSet;

use kakao_core::{Hwnd, WindowGraph, WindowNode};
use kakao_win32::Win32Api;

pub fn build_graph(api: &dyn Win32Api, pids: &[i64]) -> WindowGraph {
    let pid_set: HashSet<i64> = pids.iter().copied().collect();
    let mut top_level = Vec::new();
    api.enum_windows(&mut |hwnd| {
        let pid = api.get_window_thread_process_id(hwnd);
        if pid_set.contains(&pid) {
            top_level.push(hwnd);
        }
        true
    });
    top_level.sort_unstable();
    let mut graph = WindowGraph::empty(pids.to_vec());
    let mut visited = HashSet::new();
    for hwnd in top_level {
        load_tree(api, &mut graph, hwnd, None, &mut visited);
    }
    graph
}

fn load_tree(
    api: &dyn Win32Api,
    graph: &mut WindowGraph,
    hwnd: Hwnd,
    structural_parent: Option<Hwnd>,
    visited: &mut HashSet<Hwnd>,
) {
    if !visited.insert(hwnd) || !api.is_window(hwnd) {
        return;
    }
    let pid = api.get_window_thread_process_id(hwnd);
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
    let mut children = Vec::new();
    api.enum_child_windows(hwnd, &mut |child| {
        children.push(child);
        true
    });
    graph.set_children(hwnd, children.clone());
    for child in children {
        load_tree(api, graph, child, Some(hwnd), visited);
    }
}
