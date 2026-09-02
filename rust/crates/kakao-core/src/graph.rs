use std::collections::HashMap;

use serde::Deserialize;

use crate::model::{Hwnd, Pid, Rect, WindowNode, WindowText};

#[derive(Debug, Clone)]
pub struct WindowGraph {
    pub pids: Vec<Pid>,
    pub nodes: HashMap<Hwnd, WindowNode>,
    pub children: HashMap<Hwnd, Vec<Hwnd>>,
}

#[derive(Debug, Deserialize)]
struct DumpFile {
    pids: Vec<Pid>,
    windows: Vec<DumpNode>,
}

#[derive(Debug, Deserialize)]
struct DumpNode {
    hwnd: Hwnd,
    class: String,
    text: String,
    pid: Pid,
    visible: bool,
    rect: Option<[i32; 4]>,
    #[serde(default)]
    owner: Option<Hwnd>,
    #[serde(default)]
    children: Vec<DumpNode>,
}

impl WindowGraph {
    pub fn from_dump_json(text: &str) -> Result<Self, serde_json::Error> {
        let dump: DumpFile = serde_json::from_str(text)?;
        let mut graph = Self {
            pids: dump.pids,
            nodes: HashMap::new(),
            children: HashMap::new(),
        };
        for node in dump.windows {
            graph.load_node(node, None);
        }
        Ok(graph)
    }

    fn load_node(&mut self, node: DumpNode, structural_parent: Option<Hwnd>) {
        let hwnd = node.hwnd;
        let children = node.children;
        let child_hwnds: Vec<Hwnd> = children.iter().map(|child| child.hwnd).collect();
        self.nodes.insert(
            hwnd,
            WindowNode {
                hwnd,
                pid: node.pid,
                class_name: node.class,
                title: WindowText::Known(node.text),
                structural_parent,
                owner: node.owner.filter(|owner| *owner != 0),
                rect: node.rect.map(Rect::from_xyxy),
                visible: node.visible,
            },
        );
        self.children.insert(hwnd, child_hwnds);
        for child in children {
            self.load_node(child, Some(hwnd));
        }
    }

    pub fn get(&self, hwnd: Hwnd) -> Option<&WindowNode> {
        self.nodes.get(&hwnd)
    }

    pub fn enum_windows(&self) -> Vec<Hwnd> {
        let mut hwnds: Vec<Hwnd> = self
            .nodes
            .values()
            .filter(|node| node.structural_parent.is_none())
            .map(|node| node.hwnd)
            .collect();
        hwnds.sort_unstable();
        hwnds
    }

    pub fn enum_children(&self, parent: Hwnd) -> Vec<Hwnd> {
        self.children.get(&parent).cloned().unwrap_or_default()
    }

    pub fn enum_descendants(&self, parent: Hwnd, max_depth: i32) -> Vec<(Hwnd, i32)> {
        if max_depth <= 0 || self.get(parent).is_none() {
            return Vec::new();
        }
        let mut descendants = Vec::new();
        let mut queue: Vec<(Hwnd, i32)> = self
            .enum_children(parent)
            .into_iter()
            .map(|hwnd| (hwnd, 1))
            .collect();
        let mut index = 0;
        while index < queue.len() {
            let (hwnd, depth) = queue[index];
            index += 1;
            descendants.push((hwnd, depth));
            if depth >= max_depth {
                continue;
            }
            for child in self.enum_children(hwnd) {
                queue.push((child, depth + 1));
            }
        }
        descendants
    }
}
