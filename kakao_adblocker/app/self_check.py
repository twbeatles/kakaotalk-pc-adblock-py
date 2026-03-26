from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable, Optional, cast


@dataclass(frozen=True)
class SelfCheckRecord:
    name: str
    ok: bool
    severity: str
    detail: str


def self_check_exit_code(records: list[SelfCheckRecord]) -> int:
    return 1 if any((not record.ok) and record.severity == "core" for record in records) else 0


def self_check_payload(records: list[SelfCheckRecord], completed: bool = True) -> dict[str, object]:
    passed = sum(1 for record in records if record.ok)
    core_total = sum(1 for record in records if record.severity == "core")
    core_failed = sum(1 for record in records if (not record.ok) and record.severity == "core")
    optional_failed = sum(1 for record in records if (not record.ok) and record.severity == "optional")
    exit_code = self_check_exit_code(records)
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


def emit_self_check_text(records: list[SelfCheckRecord]) -> None:
    for record in records:
        status = "OK" if record.ok else "FAIL"
        severity_suffix = "" if record.severity == "core" else " [optional]"
        print(f"[{status}] {record.name}{severity_suffix}: {record.detail}")
    summary = cast(dict[str, int], self_check_payload(records)["summary"])
    print(
        f"Summary: {summary['passed']}/{summary['total']} checks passed "
        f"(core_failed={summary['core_failed']}, optional_failed={summary['optional_failed']})"
    )


def emit_self_check_json(
    records: list[SelfCheckRecord],
    *,
    report_path: str | None,
    write_text_report: Callable[[str, str], None],
    write_stdout_text: Callable[[str], None],
    frozen: bool,
) -> None:
    payload = json.dumps(self_check_payload(records, completed=True), ensure_ascii=False, indent=2)
    if report_path:
        write_text_report(report_path, payload)
    if report_path and frozen:
        return
    write_stdout_text(payload)


def write_self_check_report(
    records: list[SelfCheckRecord],
    report_path: str,
    *,
    completed: bool,
    write_text_report: Callable[[str, str], None],
) -> None:
    payload = json.dumps(self_check_payload(records, completed=completed), ensure_ascii=False, indent=2)
    write_text_report(report_path, payload)
