from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class WindowNode:
    hwnd: int
    parent_hwnd: int
    children: Set[int] = field(default_factory=set)


class WindowGraph:
    """Lightweight compatibility graph helper (v11 does not require full graph traversal)."""

    def __init__(self):
        self.nodes: Dict[int, WindowNode] = {}

    def add_edge(self, parent: int, child: int) -> None:
        if parent not in self.nodes:
            self.nodes[parent] = WindowNode(hwnd=parent, parent_hwnd=0)
        if child not in self.nodes:
            self.nodes[child] = WindowNode(hwnd=child, parent_hwnd=parent)
        self.nodes[parent].children.add(child)
        self.nodes[child].parent_hwnd = parent


__all__ = ["WindowGraph", "WindowNode"]
