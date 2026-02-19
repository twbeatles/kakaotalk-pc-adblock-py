# -*- coding: utf-8 -*-
"""Bootstrap entrypoint kept for CLI/backward compatibility."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from kakao_adblocker import (
    main,
    # Re-export legacy public API for tests and external scripts.
    PatternType,
    AdPattern,
    PatternConfig,
    PatternMatcher,
    LayoutEngine,
    EventDrivenAdBlocker,
    WindowEvent,
    WindowInfo,
    WindowGraph,
    WindowNode,
    HostsManager,
    AppSettings,
    AdFitBlocker,
    SystemManager,
    StartupManager,
    QueueHandler,
    setup_logging,
    User32,
    EVENT_OBJECT_SHOW,
    EVENT_OBJECT_LOCATIONCHANGE,
    SmartOptimizeResult,
    run_smart_optimize,
    APPDATA_DIR,
    SETTINGS_FILE,
    DOMAINS_FILE,
    PATTERNS_FILE,
    LOG_FILE,
    resource_base_dir,
    get_app_data_dir,
    migrate_legacy_user_files,
    ensure_user_file,
)

if __name__ == "__main__":
    main()
