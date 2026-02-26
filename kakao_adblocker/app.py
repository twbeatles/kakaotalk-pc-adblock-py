from __future__ import annotations

import argparse
import sys
import tkinter as tk
from typing import Optional

from .config import LayoutRulesV11, LayoutSettingsV11, VERSION, ensure_runtime_files
from .event_engine import LayoutOnlyEngine
from .logging_setup import setup_logging
from .ui import TrayController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KakaoTalk Layout AdBlocker v11")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to tray")
    parser.add_argument("--dump-tree", action="store_true", help="Dump KakaoTalk window tree and exit")
    parser.add_argument("--dump-dir", type=str, default=None, help="Dump directory for --dump-tree")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    ensure_runtime_files()
    settings = LayoutSettingsV11.load()
    rules = LayoutRulesV11.load()
    logger = setup_logging(settings.log_level)

    engine = LayoutOnlyEngine(logger, settings, rules)

    if args.dump_tree:
        path = engine.dump_window_tree(out_dir=args.dump_dir)
        if path:
            print(path)
            return 0
        print("KakaoTalk not running (or root not found)")
        return 1

    root = tk.Tk()
    controller = TrayController(root, engine, settings, logger)
    engine.start()
    controller.start()
    controller.show_startup_notice()

    if args.minimized or settings.start_minimized:
        controller.hide_window()
    else:
        controller.show_window()

    root.mainloop()
    return 0


__all__ = ["main", "build_parser", "VERSION"]
