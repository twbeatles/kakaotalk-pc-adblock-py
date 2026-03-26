from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KakaoTalk Layout AdBlocker v11")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to tray")
    parser.add_argument("--startup-launch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dump-tree", action="store_true", help="Dump KakaoTalk window tree and exit")
    parser.add_argument("--dump-tree-series", action="store_true", help="Dump a time series of KakaoTalk window trees and exit")
    parser.add_argument("--dump-dir", type=str, default=None, help="Dump directory for --dump-tree")
    parser.add_argument("--dump-series-duration-ms", type=int, default=1000, help="Total duration for --dump-tree-series")
    parser.add_argument("--dump-series-interval-ms", type=int, default=100, help="Interval between frames for --dump-tree-series")
    parser.add_argument("--self-check", action="store_true", help="Run environment self-check and exit")
    parser.add_argument("--json", action="store_true", help="Emit JSON for supported diagnostics paths")
    parser.add_argument("--self-check-report", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--startup-trace", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--exit-after-startup-ms", type=int, default=None, help=argparse.SUPPRESS)
    return parser
