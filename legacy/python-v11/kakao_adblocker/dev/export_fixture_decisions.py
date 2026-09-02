from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kakao_adblocker.dev.fixture_runner import (
    FIXTURE_CASES,
    GOLDEN_DIR,
    build_golden_payload,
    dumps_golden,
    golden_path,
)


def write_golden_files() -> list[Path]:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for case in FIXTURE_CASES:
        path = golden_path(case.fixture)
        path.write_text(dumps_golden(build_golden_payload(case.fixture)), encoding="utf-8")
        written.append(path)
    return written


def check_golden_files() -> list[str]:
    mismatches: list[str] = []
    for case in FIXTURE_CASES:
        path = golden_path(case.fixture)
        actual = dumps_golden(build_golden_payload(case.fixture))
        if not path.is_file():
            mismatches.append(f"missing {path.as_posix()}")
            continue
        committed = path.read_text(encoding="utf-8")
        if committed != actual:
            try:
                committed_obj = json.loads(committed)
                actual_obj = json.loads(actual)
            except json.JSONDecodeError:
                mismatches.append(f"changed {path.as_posix()} (invalid JSON)")
                continue
            if committed_obj != actual_obj:
                mismatches.append(f"changed {path.as_posix()}")
            else:
                mismatches.append(f"changed {path.as_posix()} (whitespace)")
    return mismatches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export deterministic golden decisions from window dump fixtures")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Write tests/fixtures/golden/*.json")
    group.add_argument("--check", action="store_true", help="Check committed goldens match current Python engine")
    args = parser.parse_args(argv)
    if args.write:
        for path in write_golden_files():
            print(path)
        return 0
    mismatches = check_golden_files()
    if mismatches:
        print("golden mismatch:", file=sys.stderr)
        for item in mismatches:
            print(f"  {item}", file=sys.stderr)
        return 1
    print("golden files match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
