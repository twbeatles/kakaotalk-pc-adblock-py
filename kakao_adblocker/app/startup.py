from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional


def initial_startup_trace(startup_launch: bool, minimized_requested: bool) -> dict[str, object]:
    return {
        "startup_launch": bool(startup_launch),
        "minimized_requested": bool(minimized_requested),
        "shell_wait_attempted": False,
        "shell_wait_ok": False,
        "tray_import_ok": False,
        "tray_available": False,
        "tray_start_error": "",
        "window_hidden_after_start": False,
    }


def is_root_visible(root: Any) -> bool:
    if root is None:
        return False
    if hasattr(root, "winfo_viewable"):
        try:
            return bool(root.winfo_viewable())
        except Exception:
            pass
    if hasattr(root, "state"):
        try:
            state = str(root.state()).lower()
            return state not in {"withdrawn", "iconic"}
        except Exception:
            pass
    return True


def finalize_startup_trace(
    trace: dict[str, object],
    controller: Any,
    root: Any,
    *,
    check_tray_import: Callable[[], tuple[bool, str]],
) -> None:
    tray_import_ok, _detail = check_tray_import()
    trace["tray_import_ok"] = tray_import_ok
    if controller is not None and hasattr(controller, "is_tray_available"):
        try:
            trace["tray_available"] = bool(controller.is_tray_available())
        except Exception:
            trace["tray_available"] = False
    trace["tray_start_error"] = str(getattr(controller, "_tray_start_error", "") or "")
    trace["window_hidden_after_start"] = not is_root_visible(root)


def write_startup_trace(path: str, trace: dict[str, object]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
        f.write("\n")


def schedule_startup_exit(root: Any, controller: Any, delay_ms: Optional[int]) -> None:
    if delay_ms is None:
        return
    shutdown = getattr(controller, "shutdown", None)
    if not callable(shutdown):
        return
    if hasattr(root, "after"):
        try:
            root.after(max(int(delay_ms), 0), shutdown)
            return
        except Exception:
            pass
    shutdown()
