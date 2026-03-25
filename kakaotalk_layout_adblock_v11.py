# -*- coding: utf-8 -*-
"""KakaoTalk Layout AdBlocker v11 entrypoint."""

from __future__ import annotations

import json
import os
import sys


def _write_bootstrap_report(argv: list[str]) -> int | None:
    if "--bootstrap-argv-report" not in argv:
        return None
    index = argv.index("--bootstrap-argv-report")
    if index + 1 >= len(argv):
        return 2
    path = argv[index + 1]
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"argv": argv}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    bootstrap_rc = _write_bootstrap_report(sys.argv[1:])
    if bootstrap_rc is not None:
        raise SystemExit(bootstrap_rc)

    from kakao_adblocker.app import main

    raise SystemExit(main())
