import importlib.util
import logging
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "카카오톡 광고제거 v10.0.py"
    spec = importlib.util.spec_from_file_location("kakao_adblock", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_window_graph_snapshot_root_collects_tree(monkeypatch):
    m = load_module()
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    graph = m.WindowGraph(logger)

    tree = {1: [2, 3], 2: [4], 3: [], 4: []}
    info = {
        1: {"pid": 100, "cls": "EVA_Window", "title": "카카오톡", "rect": (0, 0, 600, 800), "visible": True, "parent": 0},
        2: {"pid": 100, "cls": "EVA_ChildWindow", "title": "OnlineMainView", "rect": (0, 0, 600, 700), "visible": True, "parent": 1},
        3: {"pid": 100, "cls": "Chrome_WidgetWin_1", "title": "AdFit", "rect": (0, 700, 600, 800), "visible": True, "parent": 1},
        4: {"pid": 100, "cls": "EVA_ChildWindow", "title": "Nested", "rect": (0, 0, 600, 600), "visible": True, "parent": 2},
    }

    monkeypatch.setattr(m.User32, "is_window", staticmethod(lambda hwnd: hwnd in info))
    monkeypatch.setattr(m.User32, "get_pid", staticmethod(lambda hwnd: info[hwnd]["pid"]))
    monkeypatch.setattr(m.User32, "get_class", staticmethod(lambda hwnd: info[hwnd]["cls"]))
    monkeypatch.setattr(m.User32, "get_text", staticmethod(lambda hwnd: info[hwnd]["title"]))
    monkeypatch.setattr(m.User32, "get_window_rect", staticmethod(lambda hwnd: info[hwnd]["rect"]))
    monkeypatch.setattr(m.User32, "is_visible", staticmethod(lambda hwnd: info[hwnd]["visible"]))
    monkeypatch.setattr(m.User32, "get_parent", staticmethod(lambda hwnd: info[hwnd]["parent"]))

    def fake_enum(parent_hwnd, cb):
        for child in tree.get(parent_hwnd, []):
            cb(child, 0)

    monkeypatch.setattr(graph, "_enum_child_windows", fake_enum)

    snap = graph.snapshot_root(1, max_depth=8)
    assert set(snap.keys()) == {1, 2, 3, 4}
    assert snap[1].children == {2, 3}
    assert snap[2].children == {4}

