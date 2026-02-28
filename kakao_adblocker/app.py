from __future__ import annotations

import argparse
import importlib
import os
import sys
from types import SimpleNamespace
from typing import Any, Callable, Optional, Tuple

from .config import APPDATA_DIR, LayoutRulesV11, LayoutSettingsV11, VERSION, consume_load_warnings, ensure_runtime_files
from .event_engine import LayoutOnlyEngine
from .logging_setup import setup_logging
from .services import ProcessInspector, StartupManager

# Lazy-loaded UI dependencies for faster non-UI startup paths.
tk: Any = SimpleNamespace(Tk=None)
TrayController: Any = None


def _load_ui_dependencies() -> None:
    global tk, TrayController
    if getattr(tk, "Tk", None) is None:
        import tkinter as _tk

        tk = _tk
    if TrayController is None:
        from .ui import TrayController as _TrayController

        TrayController = _TrayController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KakaoTalk Layout AdBlocker v11")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to tray")
    parser.add_argument("--dump-tree", action="store_true", help="Dump KakaoTalk window tree and exit")
    parser.add_argument("--dump-dir", type=str, default=None, help="Dump directory for --dump-tree")
    parser.add_argument("--self-check", action="store_true", help="Run environment self-check and exit")
    return parser


def _check_appdata_writable() -> Tuple[bool, str]:
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        probe_path = os.path.join(APPDATA_DIR, ".selfcheck-write.tmp")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe_path)
        return True, f"쓰기 가능 ({APPDATA_DIR})"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def _check_tray_import() -> Tuple[bool, str]:
    try:
        importlib.import_module("pystray")
        importlib.import_module("PIL.Image")
        importlib.import_module("PIL.ImageDraw")
        return True, "pystray/Pillow import 가능"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def _run_self_check() -> int:
    checks: list[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
        ("APPDATA 접근/쓰기", _check_appdata_writable),
        ("tasklist 실행", ProcessInspector.probe_tasklist),
        ("Run 레지스트리 읽기/쓰기 접근", StartupManager.probe_access),
        ("트레이 모듈 import", _check_tray_import),
    ]
    passed = 0
    for label, fn in checks:
        ok, detail = fn()
        if ok:
            passed += 1
        print(f"[{'OK' if ok else 'FAIL'}] {label}: {detail}")
    print(f"Summary: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


def main(argv: Optional[list[str]] = None) -> int:
    if os.name != "nt":
        print("This application only supports Windows.", file=sys.stderr)
        return 2

    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_check:
        return _run_self_check()

    ensure_runtime_files()
    settings = LayoutSettingsV11.load()
    rules = LayoutRulesV11.load()
    logger = setup_logging(settings.log_level)
    load_warnings = consume_load_warnings()

    engine = LayoutOnlyEngine(logger, settings, rules)
    for warning in load_warnings:
        logger.warning(warning)
    if load_warnings:
        engine.report_warning(load_warnings[0])

    if args.dump_tree:
        path = engine.dump_window_tree(out_dir=args.dump_dir)
        if path:
            print(path)
            return 0
        print("KakaoTalk not running (or root not found)")
        return 1

    _load_ui_dependencies()
    root = tk.Tk()
    controller = TrayController(root, engine, settings, logger)
    engine_started = False
    try:
        engine.start()
        engine_started = True
        controller.start()
        requested_minimized = bool(args.minimized or settings.start_minimized)
        should_start_minimized = requested_minimized
        if requested_minimized and not controller.is_tray_available():
            warning = "tray unavailable, minimized ignored"
            logger.warning(warning)
            engine.report_warning(warning)
            should_start_minimized = False

        if not requested_minimized:
            controller.show_startup_notice()

        if should_start_minimized:
            controller.hide_window()
        else:
            controller.show_window()

        root.mainloop()
        return 0
    finally:
        try:
            controller.stop_tray()
        except Exception as exc:
            logger.warning("cleanup: stop_tray failed (%s)", exc.__class__.__name__)
        if engine_started:
            try:
                engine.stop()
            except Exception as exc:
                logger.warning("cleanup: engine.stop failed (%s)", exc.__class__.__name__)


__all__ = ["main", "build_parser", "VERSION"]
