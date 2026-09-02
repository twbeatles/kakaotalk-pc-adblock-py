from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

from .warnings import _push_load_warning

BROKEN_BACKUP_KEEP_COUNT = 10
BROKEN_BACKUP_MAX_AGE_DAYS = 30
_BROKEN_SUFFIX_RE = re.compile(r"\.broken-(\d{8}-\d{6})$")


def _coerce_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        out = default
    else:
        out = value
    if minimum is not None:
        out = max(out, minimum)
    if maximum is not None:
        out = min(out, maximum)
    return out


def _coerce_float(value: Any, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        out = float(default)
    else:
        out = float(value)
    if minimum is not None:
        out = max(out, minimum)
    if maximum is not None:
        out = min(out, maximum)
    return out


def _coerce_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _coerce_str_list(value: Any, default: List[str]) -> List[str]:
    if not isinstance(value, list):
        return list(default)
    out = [x for x in value if isinstance(x, str) and x.strip()]
    return out if out else list(default)


def _atomic_write_text(path: str, text: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    prefix = f".{os.path.basename(path)}."
    fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise


def _write_text_if_missing(path: str, text: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except FileExistsError:
        return


def _json_with_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _backup_broken_json(path: str, label: str, reason: str) -> bool:
    if not os.path.exists(path):
        _push_load_warning(f"{label} 손상 감지: {reason}. 원본 파일이 없어 백업을 건너뜁니다.")
        return False
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.broken-{timestamp}"
    try:
        shutil.copy2(path, backup_path)
        _push_load_warning(f"{label} 손상 감지: {reason}. 백업 생성: {backup_path}.")
        _cleanup_broken_backups(path, label)
        return True
    except Exception as exc:
        _push_load_warning(f"{label} 손상 감지: {reason}. 백업 실패({exc.__class__.__name__}).")
        _cleanup_broken_backups(path, label)
        return False


def _self_heal_broken_json(path: str, label: str, default_text: str) -> None:
    import kakao_adblocker.config as config_module

    try:
        config_module._atomic_write_text(path, _json_with_trailing_newline(default_text))
        _push_load_warning(f"{label} 자동 복구 성공: 기본값 JSON으로 재생성했습니다.")
    except Exception as exc:
        _push_load_warning(f"{label} 자동 복구 실패({exc.__class__.__name__}). 기본값으로 동작합니다.")


def _backup_timestamp(path: Path) -> datetime:
    match = _BROKEN_SUFFIX_RE.search(path.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
        except Exception:
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        return datetime.min


def _cleanup_broken_backups(path: str, label: str) -> None:
    base_path = Path(path)
    parent = base_path.parent
    pattern = f"{base_path.name}.broken-*"
    now = datetime.now()
    max_age = timedelta(days=BROKEN_BACKUP_MAX_AGE_DAYS)

    try:
        backups = list(parent.glob(pattern))
    except Exception as exc:
        _push_load_warning(f"{label} 백업 정리 실패({exc.__class__.__name__}).")
        return

    for backup in backups:
        backup_time = _backup_timestamp(backup)
        if now - backup_time <= max_age:
            continue
        try:
            backup.unlink()
        except Exception as exc:
            _push_load_warning(f"{label} 백업 정리 실패: {backup.name} ({exc.__class__.__name__})")

    keep = sorted(
        [p for p in parent.glob(pattern) if p.exists()],
        key=_backup_timestamp,
        reverse=True,
    )
    for old in keep[BROKEN_BACKUP_KEEP_COUNT:]:
        try:
            old.unlink()
        except Exception as exc:
            _push_load_warning(f"{label} 백업 정리 실패: {old.name} ({exc.__class__.__name__})")


def _load_json_object(path: str, label: str, default_text: str | None = None) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as exc:
        _backup_broken_json(path, label, f"JSON 파싱 실패({exc.__class__.__name__})")
        if default_text is not None:
            _self_heal_broken_json(path, label, default_text)
        return None
    if not isinstance(raw, dict):
        _backup_broken_json(path, label, "최상위 타입이 object(dict)가 아님")
        if default_text is not None:
            _self_heal_broken_json(path, label, default_text)
        return None
    return raw
