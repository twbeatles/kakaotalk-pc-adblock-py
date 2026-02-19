from .app import main
from .config import (
    APPDATA_DIR,
    SETTINGS_FILE,
    DOMAINS_FILE,
    PATTERNS_FILE,
    LOG_FILE,
    AppSettings,
    PatternConfig,
    resource_base_dir,
    get_app_data_dir,
    migrate_legacy_user_files,
    ensure_user_file,
)
from .patterns import PatternType, AdPattern, PatternMatcher
from .layout_engine import LayoutEngine
from .event_engine import EventDrivenAdBlocker, WindowEvent, WindowInfo
from .window_graph import WindowGraph, WindowNode
from .services import HostsManager, AdFitBlocker, SystemManager, StartupManager
from .logging_setup import setup_logging, QueueHandler
from .win32_api import User32
from .legacy import EVENT_OBJECT_SHOW, EVENT_OBJECT_LOCATIONCHANGE, SmartOptimizeResult, run_smart_optimize

__all__ = [
    "main",
    "APPDATA_DIR",
    "SETTINGS_FILE",
    "DOMAINS_FILE",
    "PATTERNS_FILE",
    "LOG_FILE",
    "AppSettings",
    "PatternConfig",
    "PatternType",
    "AdPattern",
    "PatternMatcher",
    "LayoutEngine",
    "EventDrivenAdBlocker",
    "WindowEvent",
    "WindowInfo",
    "WindowGraph",
    "WindowNode",
    "HostsManager",
    "AdFitBlocker",
    "SystemManager",
    "StartupManager",
    "setup_logging",
    "QueueHandler",
    "User32",
    "EVENT_OBJECT_SHOW",
    "EVENT_OBJECT_LOCATIONCHANGE",
    "SmartOptimizeResult",
    "run_smart_optimize",
    "resource_base_dir",
    "get_app_data_dir",
    "migrate_legacy_user_files",
    "ensure_user_file",
]
