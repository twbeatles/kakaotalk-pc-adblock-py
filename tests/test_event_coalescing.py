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


def test_event_queue_coalesces_same_hwnd():
    m = load_module()

    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    cfg = m.PatternConfig(str(Path("nonexistent_patterns.json")), logger)
    engine = m.EventDrivenAdBlocker(logger, cfg)

    engine._queue_window_event(1001, m.EVENT_OBJECT_SHOW)
    for _ in range(50):
        engine._queue_window_event(1001, m.EVENT_OBJECT_LOCATIONCHANGE)

    stats = engine.stats
    assert engine._event_queue.qsize() == 1
    assert stats["events_received"] == 1
    assert stats["events_coalesced"] >= 50


def test_event_queue_tracks_drop_when_full():
    m = load_module()

    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    cfg = m.PatternConfig(str(Path("nonexistent_patterns.json")), logger)
    engine = m.EventDrivenAdBlocker(logger, cfg)

    for hwnd in range(1, 1201):
        engine._queue_window_event(hwnd, m.EVENT_OBJECT_SHOW)

    stats = engine.stats
    assert engine._event_queue.qsize() <= 1000
    assert stats["events_dropped"] >= 1

