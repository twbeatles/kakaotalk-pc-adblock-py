from __future__ import annotations

import importlib
import logging
import os
import sys
from types import SimpleNamespace
from typing import Any, Callable, Optional

from ..config import (
    LayoutRulesV11,
    LayoutSettingsV11,
    VERSION,
    consume_load_warnings,
    ensure_runtime_files,
    resolve_app_data_dir,
)
from ..logging_setup import _build_formatter, _reset_logger_handlers, _resolve_level, probe_logging_setup, setup_logging
from ..services import ProcessInspector, StartupManager
from .cli import build_parser
from .self_check import (
    SelfCheckRecord,
    emit_self_check_json,
    emit_self_check_text,
    self_check_exit_code,
    write_self_check_report,
)
from .startup import (
    finalize_startup_trace,
    initial_startup_trace,
    schedule_startup_exit,
    write_startup_trace,
)

tk: Any = SimpleNamespace(Tk=None)
TrayController: Any = None
LayoutOnlyEngine: Any = None


def _load_ui_dependencies() -> None:
    global tk, TrayController
    if getattr(tk, "Tk", None) is None:
        import tkinter as _tk

        tk = _tk
    if TrayController is None:
        from ..ui import TrayController as _TrayController

        TrayController = _TrayController


def _load_engine_dependencies() -> None:
    global LayoutOnlyEngine
    if LayoutOnlyEngine is None:
        from ..event_engine import LayoutOnlyEngine as _LayoutOnlyEngine

        LayoutOnlyEngine = _LayoutOnlyEngine


def _check_appdata_writable() -> tuple[bool, str]:
    try:
        appdata_dir = resolve_app_data_dir(create=True)
        probe_path = os.path.join(appdata_dir, ".selfcheck-write.tmp")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe_path)
        return True, f"쓰기 가능 ({appdata_dir})"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def _check_tray_import() -> tuple[bool, str]:
    try:
        importlib.import_module("pystray")
        importlib.import_module("PIL.Image")
        importlib.import_module("PIL.ImageDraw")
        return True, "pystray/Pillow import 가능"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def _check_tk_boot() -> tuple[bool, str]:
    root = None
    try:
        tkinter = importlib.import_module("tkinter")
        root = tkinter.Tk()
        root.withdraw()
        root.update_idletasks()
        return True, "tkinter/Tk 초기화 가능"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def _build_fallback_logger(level: str, reason: str) -> tuple[logging.Logger, str]:
    logger = logging.getLogger("KakaoTalkLayoutAdBlocker")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    _reset_logger_handlers(logger)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(_resolve_level(level))
    stream_handler.setFormatter(_build_formatter())
    logger.addHandler(stream_handler)

    warning = f"logging init failed ({reason}); using stderr fallback"
    logger.warning(warning)
    return logger, warning


def _self_check_specs() -> list[tuple[str, str, Callable[[], tuple[bool, str]]]]:
    return [
        ("APPDATA 접근/쓰기", "core", _check_appdata_writable),
        ("로그 초기화", "core", probe_logging_setup),
        ("tasklist 실행", "optional", ProcessInspector.probe_tasklist),
        ("Run 레지스트리 읽기/쓰기 접근", "optional", StartupManager.probe_access),
        ("Run 등록 명령 유효성", "optional", StartupManager.probe_registration_command),
        ("Tk UI 부팅", "core", _check_tk_boot),
        ("트레이 모듈 import", "core", _check_tray_import),
    ]


def _run_self_check(as_json: bool = False, report_path: str | None = None) -> int:
    records: list[SelfCheckRecord] = []
    if report_path:
        write_self_check_report(records, report_path, completed=False, write_text_report=_write_text_report)
    for label, severity, fn in _self_check_specs():
        ok, detail = fn()
        records.append(SelfCheckRecord(name=label, ok=ok, severity=severity, detail=detail))
        if report_path:
            write_self_check_report(records, report_path, completed=False, write_text_report=_write_text_report)
    if as_json:
        emit_self_check_json(
            records,
            report_path=report_path,
            write_text_report=_write_text_report,
            write_stdout_text=_write_stdout_text,
            frozen=bool(getattr(sys, "frozen", False)),
        )
    else:
        if report_path:
            write_self_check_report(records, report_path, completed=True, write_text_report=_write_text_report)
        emit_self_check_text(records)
    return self_check_exit_code(records)


def _pick_priority_warning(warnings: list[str]) -> str | None:
    if not warnings:
        return None
    for message in warnings:
        if "복구 실패" in message:
            return message
    for message in warnings:
        if "자동 복구" in message:
            return message
    return warnings[0]


def _write_text_report(path: str, text: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else f"{text}\n")


def _write_stdout_text(text: str) -> None:
    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    try:
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")
        stream.flush()
    except Exception:
        pass


def main(argv: Optional[list[str]] = None) -> int:
    if os.name != "nt":
        print("This application only supports Windows.", file=sys.stderr)
        return 2

    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_check:
        return _run_self_check(as_json=bool(args.json), report_path=args.self_check_report)

    ensure_runtime_files()
    settings = LayoutSettingsV11.load()
    rules = LayoutRulesV11.load()
    requested_minimized = bool(args.minimized or settings.start_minimized)
    startup_trace = initial_startup_trace(args.startup_launch, requested_minimized)
    logging_warning = ""
    try:
        logger = setup_logging(settings.log_level)
    except Exception as exc:
        logger, logging_warning = _build_fallback_logger(settings.log_level, exc.__class__.__name__)
    load_warnings = consume_load_warnings()
    combined_warnings = list(load_warnings)
    if logging_warning:
        combined_warnings.append(logging_warning)

    _load_engine_dependencies()
    engine = LayoutOnlyEngine(logger, settings, rules)
    for warning in load_warnings:
        logger.warning(warning)
    priority_warning = _pick_priority_warning(combined_warnings)

    if args.dump_tree:
        path = engine.dump_window_tree(out_dir=args.dump_dir)
        if path:
            print(path)
            return 0
        print("KakaoTalk not running (or root not found)")
        return 1
    if args.dump_tree_series:
        path = engine.dump_window_tree_series(
            out_dir=args.dump_dir,
            duration_ms=args.dump_series_duration_ms,
            interval_ms=args.dump_series_interval_ms,
        )
        if path:
            print(path)
            return 0
        print("KakaoTalk not running (or root not found)")
        return 1

    controller: Any = None
    root: Any = None
    engine_started = False
    try:
        if args.startup_launch:
            startup_trace["shell_wait_attempted"] = True
            shell_ready = StartupManager.wait_for_shell_ready()
            startup_trace["shell_wait_ok"] = bool(shell_ready)
            if not shell_ready:
                logger.warning("startup launch: shell readiness wait timed out")

        _load_ui_dependencies()
        root = tk.Tk()
        controller = TrayController(root, engine, settings, logger)

        engine.start()
        engine_started = True
        if priority_warning:
            engine.report_warning(priority_warning)

        controller.start(startup_minimized=requested_minimized)
        should_start_minimized = requested_minimized and controller.is_tray_available()

        if not requested_minimized:
            controller.show_startup_notice()

        if should_start_minimized:
            controller.hide_window()
            if args.startup_launch and controller.is_tray_available():
                controller.schedule_startup_tray_refresh()
        else:
            controller.show_window()

        finalize_startup_trace(startup_trace, controller, root, check_tray_import=_check_tray_import)
        if args.startup_trace:
            write_startup_trace(args.startup_trace, startup_trace)
        schedule_startup_exit(root, controller, args.exit_after_startup_ms)

        root.mainloop()
        return 0
    finally:
        if args.startup_trace and not os.path.exists(args.startup_trace):
            finalize_startup_trace(startup_trace, controller, root, check_tray_import=_check_tray_import)
            try:
                write_startup_trace(args.startup_trace, startup_trace)
            except Exception:
                pass
        if controller is not None:
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
