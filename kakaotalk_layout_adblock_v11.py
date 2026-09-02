# -*- coding: utf-8 -*-
"""Deprecated Python entrypoint. The default implementation is the Rust native EXE."""

from __future__ import annotations

import sys

def main() -> int:
    print(
        "KakaoTalk Layout AdBlocker v11 is now the Rust native build.\n"
        "Run dist/KakaoTalkLayoutAdBlocker_v11.exe or: cargo run -p kakao-app --release\n"
        "The Python reference implementation is in legacy/python-v11/.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
