from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any, Callable, Optional, cast

from .config import (
    LayoutRulesV11,
    LayoutSettingsV11,
    VERSION,
    consume_load_warnings,
    ensure_runtime_files,
    get_runtime_paths,
    resolve_app_data_dir,
)
from .logging_setup import _build_formatter, _reset_logger_handlers, _resolve_level, probe_logging_setup, setup_logging
from .services import ProcessInspector, StartupManager

# Lazy-loaded UI dependencies for faster non-UI startup paths.
tk: Any = SimpleNamespace(Tk=None)
TrayController: Any = None
LayoutOnlyEngine: Any = None


@dataclass(frozen=True)
class SelfCheckRecord:
    name: str
    ok: bool
    severity: str
    detail: str


def _load_ui_dependencies() -> None:
    global tk, TrayController
    if getattr(tk, "Tk", None) is None:
        import tkinter as _tk

        tk = _tk
    if TrayController is None:
        from .ui import TrayController as _TrayController

        TrayController = _TrayController


def _load_engine_dependencies() -> None:
    global LayoutOnlyEngine
    if LayoutOnlyEngine is None:
        from .event_engine import LayoutOnlyEngine as _LayoutOnlyEngine

        LayoutOnlyEngine = _LayoutOnlyEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KakaoTalk Layout AdBlocker v11")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to tray")
    parser.add_argument("--startup-launch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dump-tree", action="store_true", help="Dump KakaoTalk window tree and exit")
    parser.add_argument("--dump-dir", type=str, default=None, help="Dump directory for --dump-tree")
    parser.add_argument("--self-check", action="store_true", help="Run environment self-check and exit")
    parser.add_argument("--json", action="store_true", help="Emit JSON for supported diagnostics paths")
    parser.add_argument("--self-check-report", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--startup-trace", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--exit-after-startup-ms", type=int, default=None, help=argparse.SUPPRESS)
    return parser


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
        ("Tk UI 부팅", "core", _check_tk_boot),
        ("트레이 모듈 import", "core", _check_tray_import),
    ]


def _collect_self_check_records() -> list[SelfCheckRecord]:
    records: list[SelfCheckRecord] = []
    for label, severity, fn in _self_check_specs():
        ok, detail = fn()
        records.append(SelfCheckRecord(name=label, ok=ok, severity=severity, detail=detail))
    return records


def _self_check_exit_code(records: list[SelfCheckRecord]) -> int:
    return 1 if any((not record.ok) and record.severity == "core" for record in records) else 0


def _self_check_payload(records: list[SelfCheckRecord], completed: bool = True) -> dict[str, object]:
    passed = sum(1 for record in records if record.ok)
    core_total = sum(1 for record in records if record.severity == "core")
    core_failed = sum(1 for record in records if (not record.ok) and record.severity == "core")
    optional_failed = sum(1 for record in records if (not record.ok) and record.severity == "optional")
    exit_code = _self_check_exit_code(records)
    return {
        "ok": exit_code == 0,
        "completed": completed,
        "summary": {
            "passed": passed,
            "total": len(records),
            "core_total": core_total,
            "core_failed": core_failed,
            "optional_failed": optional_failed,
            "exit_code": exit_code,
        },
        "checks": [asdict(record) for record in records],
    }

def _emit_self_check_text(records: list[SelfCheckRecord]) -> None:
    for record in records:
        status = "OK" if record.ok else "FAIL"
        severity_suffix = "" if record.severity == "core" else " [optional]"
        print(f"[{status}] {record.name}{severity_suffix}: {record.detail}")
    summary = cast(dict[str, int], _self_check_payload(records)["summary"])
    print(
        f"Summary: {summary['passed']}/{summary['total']} checks passed "
        f"(core_failed={summary['core_failed']}, optional_failed={summary['optional_failed']})"
    )


def _emit_self_check_json(records: list[SelfCheckRecord], report_path: str | None = None) -> None:
    payload = json.dumps(_self_check_payload(records, completed=True), ensure_ascii=False, indent=2)
    if report_path:
        _write_text_report(report_path, payload)
    if report_path and getattr(sys, "frozen", False):
        return
    _write_stdout_text(payload)


def _run_self_check(as_json: bool = False, report_path: str | None = None) -> int:
    records: list[SelfCheckRecord] = []
    if report_path:
        _write_self_check_report(records, report_path, completed=False)
    for label, severity, fn in _self_check_specs():
        ok, detail = fn()
        records.append(SelfCheckRecord(name=label, ok=ok, severity=severity, detail=detail))
        if report_path:
            _write_self_check_report(records, report_path, completed=False)
    if as_json:
        _emit_self_check_json(records, report_path=report_path)
    else:
        if report_path:
            _write_self_check_report(records, report_path, completed=True)
        _emit_self_check_text(records)
    return _self_check_exit_code(records)


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


def _initial_startup_trace(startup_launch: bool, minimized_requested: bool) -> dict[str, object]:
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


def _is_root_visible(root: Any) -> bool:
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


def _finalize_startup_trace(trace: dict[str, object], controller: Any, root: Any) -> None:
    tray_import_ok, _detail = _check_tray_import()
    trace["tray_import_ok"] = tray_import_ok
    if controller is not None and hasattr(controller, "is_tray_available"):
        try:
            trace["tray_available"] = bool(controller.is_tray_available())
        except Exception:
            trace["tray_available"] = False
    trace["tray_start_error"] = str(getattr(controller, "_tray_start_error", "") or "")
    trace["window_hidden_after_start"] = not _is_root_visible(root)


def _write_startup_trace(path: str, trace: dict[str, object]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
        f.write("\n")


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


def _write_self_check_report(records: list[SelfCheckRecord], report_path: str, completed: bool) -> None:
    payload = json.dumps(_self_check_payload(records, completed=completed), ensure_ascii=False, indent=2)
    _write_text_report(report_path, payload)


def _schedule_startup_exit(root: Any, controller: Any, delay_ms: Optional[int]) -> None:
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
    startup_trace = _initial_startup_trace(args.startup_launch, requested_minimized)
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
            if args.startup_launch and controller.is_tray_available():
                controller.schedule_startup_tray_refresh()
        else:
            controller.show_window()

        _finalize_startup_trace(startup_trace, controller, root)
        if args.startup_trace:
            _write_startup_trace(args.startup_trace, startup_trace)
        _schedule_startup_exit(root, controller, args.exit_after_startup_ms)

        root.mainloop()
        return 0
    finally:
        if args.startup_trace and not os.path.exists(args.startup_trace):
            _finalize_startup_trace(startup_trace, controller, root)
            try:
                _write_startup_trace(args.startup_trace, startup_trace)
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
